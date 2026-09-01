"""Cloudflare R2 image mirror -- content-hash dedup + resolver-KV upsert.

Part of the Bitcoin Stamps image-storage migration: collapse the txid-keyed S3 corpus
(one stored copy per stamp) to one content-addressed object per unique hash, served from
Cloudflare R2 behind a Worker resolver.

This module is a **secondary, flag-gated sink** (``config.R2_MIRROR_ENABLED``, default OFF)
that runs ALONGSIDE the existing S3 write during the migration transition -- a "dual write".
The current serving path is still S3/CloudFront, so new stamps must keep landing in S3; R2 +
the resolver KV are populated in parallel so the Worker can serve from R2 after cutover.
Dropping the S3 write (R2-only) is a later change, gated on a post-cutover soak.

Contract -- MUST match the Worker resolver and the offline backfill byte-for-byte:
  * R2 object : ``content/{file_hash}.{ext}``  (content-addressed -> naturally deduped)
  * KV entry  : ``{tx_hash}.{ext}`` -> ``{"h": file_hash, "e": ext}``  (compact JSON)

Failure policy: this never raises into the indexer. Storing the image to S3 has already
succeeded by the time we run; a mirror hiccup (R2 5xx, a Cloudflare API blip) must not halt
indexing. Failures log a warning and return -- the authoritative reconciliation is the
offline backfill (``tools/r2_image_backfill.py``), which compares KV against the ledger and
fills any drift.
"""

import json
import logging
import time
from typing import Optional, Set

import config
import index_core.log as log

logger = logging.getLogger(__name__)
log.set_logger(logger)

CF_API_BASE = "https://api.cloudflare.com/client/v4"

# In-memory set of content keys this process has already uploaded, so a hot duplicate
# image (some content is stored tens of thousands of times) doesn't issue a HEAD + PUT on
# every occurrence. Content is addressed by hash, so "seen" is permanent for the run.
_seen_content_keys: Set[str] = set()


def _ext_from_filename(filename: str) -> Optional[str]:
    """``{tx_hash}.{ext}`` -> lowercased ext, or None if there is no extension."""
    if not filename or "." not in filename:
        return None
    return filename.rsplit(".", 1)[1].lower()


def _content_key(file_hash: str, ext: str) -> str:
    return f"{config.R2_CONTENT_PREFIX}{file_hash}.{ext}"


def _r2_object_exists(client, key: str) -> bool:
    """True if the content-addressed object is already in R2 (dedup: skip re-upload)."""
    try:
        client.head_object(Bucket=config.R2_BUCKET, Key=key)
        return True
    except Exception:
        # head_object raises ClientError(404) when absent -- treat any miss as "not present".
        return False


def _upload_content(client, file_obj, file_hash: str, ext: str, mime_type: str) -> None:
    key = _content_key(file_hash, ext)
    if key in _seen_content_keys or _r2_object_exists(client, key):
        _seen_content_keys.add(key)
        return
    file_obj.seek(0)
    client.upload_fileobj(
        file_obj,
        config.R2_BUCKET,
        key,
        ExtraArgs={"ContentType": mime_type or "binary/octet-stream"},
    )
    _seen_content_keys.add(key)


def _kv_upsert(kv_key: str, file_hash: str, ext: str, retries: int = 5) -> None:
    """Upsert one resolver KV entry via the Cloudflare API.

    Retries on network-level exceptions (ReadTimeout/ConnectionError) AND transient 429/5xx,
    with exponential backoff -- a single Cloudflare API blip must not drop a KV entry (and it
    only spans one key here, so backoff is cheap).
    """
    import requests  # lazy -- keep import cost off the non-mirror path

    url = (
        f"{CF_API_BASE}/accounts/{config.R2_ACCOUNT_ID}" f"/storage/kv/namespaces/{config.R2_KV_NAMESPACE_ID}/values/{kv_key}"
    )
    headers = {"Authorization": f"Bearer {config.R2_KV_API_TOKEN}"}
    # Value is the raw body the resolver JSON.parse()s; compact separators match the backfill.
    body = json.dumps({"h": file_hash, "e": ext}, separators=(",", ":"))
    for attempt in range(1, retries + 1):
        try:
            resp = requests.put(url, data=body, headers=headers, timeout=30)
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"KV upsert failed after {retries} attempts: {type(e).__name__}: {e}") from e
        if resp.status_code == 200 and resp.json().get("success"):
            return
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            time.sleep(2**attempt)
            continue
        raise RuntimeError(f"KV upsert failed [{resp.status_code}]: {resp.text[:300]}")


def mirror_to_r2(filename: str, mime_type: str, file_obj, file_obj_md5: str) -> None:
    """Mirror one stored image to R2 (content-addressed) + upsert its resolver KV entry.

    ``filename`` is ``{tx_hash}.{ext}`` (the existing public path), ``file_obj_md5`` is the
    md5 of the bytes (== ``file_hash``). No-op unless ``config.R2_MIRROR_ENABLED`` and the R2
    client/KV config are present. Never raises -- see module docstring.
    """
    if not config.R2_MIRROR_ENABLED:
        return
    client = getattr(config, "R2_S3_CLIENT", None)
    if client is None or not config.R2_KV_NAMESPACE_ID or not config.R2_KV_API_TOKEN:
        logger.debug("R2 mirror enabled but not fully configured (client/KV); skipping %s", filename)
        return
    ext = _ext_from_filename(filename)
    if not ext or not file_obj_md5 or file_obj is None:
        logger.debug("R2 mirror skip %s (missing ext/md5/bytes)", filename)
        return
    try:
        _upload_content(client, file_obj, file_obj_md5, ext, mime_type)
        _kv_upsert(filename, file_obj_md5, ext)
    except Exception as e:
        # Secondary sink -- log and continue; the offline backfill reconciles drift.
        logger.warning("R2 mirror failed for %s (md5=%s): %s: %s", filename, file_obj_md5, type(e).__name__, e)
