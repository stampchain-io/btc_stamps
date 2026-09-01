"""Tests for the Cloudflare R2 image mirror (index_core/r2_mirror).

Covers the dual-write contract the Worker resolver + offline backfill depend on:
content-addressed R2 key, compact KV value shape, dedup skip-on-exists, the per-run
seen-cache, the flag-gated no-op, non-raising failure policy, and network-retry on KV.
"""

import io
import json
import unittest
from unittest import mock

import config
import index_core.r2_mirror as r2_mirror
from index_core.r2_mirror import _content_key, _ext_from_filename, mirror_to_r2

_MD5 = "0123456789abcdef0123456789abcdef"
_FILENAME = "deadbeef" * 8 + ".png"  # {tx_hash}.png


def _ok_resp():
    resp = mock.Mock()
    resp.status_code = 200
    resp.json.return_value = {"success": True}
    return resp


class TestExtAndKey(unittest.TestCase):
    def test_ext_from_filename(self):
        self.assertEqual(_ext_from_filename("abc.PNG"), "png")
        self.assertEqual(_ext_from_filename("abc.def.svg"), "svg")
        self.assertIsNone(_ext_from_filename("noext"))
        self.assertIsNone(_ext_from_filename(""))

    def test_content_key(self):
        with mock.patch.object(config, "R2_CONTENT_PREFIX", "content/"):
            self.assertEqual(_content_key(_MD5, "png"), f"content/{_MD5}.png")


class TestMirrorToR2(unittest.TestCase):
    def setUp(self):
        r2_mirror._seen_content_keys.clear()
        self._client = mock.MagicMock()
        # head_object raising == object absent (so uploads proceed by default).
        self._client.head_object.side_effect = Exception("404 Not Found")
        self._patches = [
            mock.patch.object(config, "R2_MIRROR_ENABLED", True),
            mock.patch.object(config, "R2_S3_CLIENT", self._client, create=True),
            mock.patch.object(config, "R2_BUCKET", "stampchain-images"),
            mock.patch.object(config, "R2_CONTENT_PREFIX", "content/"),
            mock.patch.object(config, "R2_ACCOUNT_ID", "acct123"),
            mock.patch.object(config, "R2_KV_NAMESPACE_ID", "ns123"),
            mock.patch.object(config, "R2_KV_API_TOKEN", "tok123"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        r2_mirror._seen_content_keys.clear()

    def test_disabled_is_noop(self):
        with mock.patch.object(config, "R2_MIRROR_ENABLED", False), mock.patch("requests.put") as put:
            mirror_to_r2(_FILENAME, "image/png", io.BytesIO(b"x"), _MD5)
            self._client.upload_fileobj.assert_not_called()
            put.assert_not_called()

    def test_uploads_content_and_upserts_kv(self):
        with mock.patch("requests.put", return_value=_ok_resp()) as put:
            mirror_to_r2(_FILENAME, "image/png", io.BytesIO(b"bytes"), _MD5)
        # content-addressed R2 upload to content/{md5}.{ext}
        args, kwargs = self._client.upload_fileobj.call_args
        self.assertEqual(args[1], "stampchain-images")
        self.assertEqual(args[2], f"content/{_MD5}.png")
        self.assertEqual(kwargs["ExtraArgs"]["ContentType"], "image/png")
        # KV upsert keyed by the public path {tx_hash}.{ext}, compact JSON value {h,e}
        put.assert_called_once()
        url = put.call_args.args[0]
        self.assertIn(f"/namespaces/ns123/values/{_FILENAME}", url)
        self.assertEqual(put.call_args.kwargs["data"], json.dumps({"h": _MD5, "e": "png"}, separators=(",", ":")))

    def test_dedup_skip_when_object_exists(self):
        self._client.head_object.side_effect = None  # head succeeds == already present
        self._client.head_object.return_value = {"ETag": "x"}
        with mock.patch("requests.put", return_value=_ok_resp()) as put:
            mirror_to_r2(_FILENAME, "image/png", io.BytesIO(b"bytes"), _MD5)
        self._client.upload_fileobj.assert_not_called()  # dedup: no re-upload
        put.assert_called_once()  # but KV still upserted (txid->hash mapping is per-stamp)

    def test_seen_cache_skips_second_head(self):
        with mock.patch("requests.put", return_value=_ok_resp()):
            mirror_to_r2(_FILENAME, "image/png", io.BytesIO(b"bytes"), _MD5)
            other = "cafebabe" * 8 + ".png"
            mirror_to_r2(other, "image/png", io.BytesIO(b"bytes"), _MD5)  # same content hash
        # First call HEADs (miss) + uploads; second call hits the seen-cache -> no 2nd HEAD/upload.
        self.assertEqual(self._client.head_object.call_count, 1)
        self.assertEqual(self._client.upload_fileobj.call_count, 1)

    def test_failure_is_swallowed(self):
        self._client.upload_fileobj.side_effect = RuntimeError("R2 down")
        with mock.patch("requests.put", return_value=_ok_resp()):
            # Must NOT raise -- mirror is a secondary sink; the backfill reconciles.
            mirror_to_r2(_FILENAME, "image/png", io.BytesIO(b"bytes"), _MD5)

    def test_not_configured_is_noop(self):
        with mock.patch.object(config, "R2_KV_API_TOKEN", None), mock.patch("requests.put") as put:
            mirror_to_r2(_FILENAME, "image/png", io.BytesIO(b"bytes"), _MD5)
            self._client.upload_fileobj.assert_not_called()
            put.assert_not_called()

    def test_missing_ext_is_noop(self):
        with mock.patch("requests.put") as put:
            mirror_to_r2("no_extension_here", "image/png", io.BytesIO(b"bytes"), _MD5)
            self._client.upload_fileobj.assert_not_called()
            put.assert_not_called()


class TestKvRetry(unittest.TestCase):
    def setUp(self):
        r2_mirror._seen_content_keys.clear()
        self._client = mock.MagicMock()
        self._client.head_object.side_effect = None
        self._client.head_object.return_value = {"ETag": "x"}  # exists -> only KV path exercised
        self._patches = [
            mock.patch.object(config, "R2_MIRROR_ENABLED", True),
            mock.patch.object(config, "R2_S3_CLIENT", self._client, create=True),
            mock.patch.object(config, "R2_BUCKET", "b"),
            mock.patch.object(config, "R2_CONTENT_PREFIX", "content/"),
            mock.patch.object(config, "R2_ACCOUNT_ID", "a"),
            mock.patch.object(config, "R2_KV_NAMESPACE_ID", "n"),
            mock.patch.object(config, "R2_KV_API_TOKEN", "t"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_kv_retries_on_network_exception_then_succeeds(self):
        import requests

        seq = [requests.exceptions.ReadTimeout("boom"), _ok_resp()]

        def _put(*a, **k):
            r = seq.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        with mock.patch("requests.put", side_effect=_put) as put, mock.patch("time.sleep"):
            mirror_to_r2(_FILENAME, "image/png", io.BytesIO(b"bytes"), _MD5)
        self.assertEqual(put.call_count, 2)  # retried the ReadTimeout, then succeeded


class TestStoreFilesS3WriteGate(unittest.TestCase):
    """store_files() must honor S3_WRITE_ENABLED so the R2 cutover is a config flip.

    Patches the upload/mirror callables in the index_core.files namespace (they are imported
    there at module load) and asserts which sinks fire under each flag combination.
    """

    def _run(self, s3_write, r2_mirror_on):
        from index_core import files as files_mod

        patches = [
            mock.patch.object(config, "STORE_FILES", True),
            mock.patch.object(config, "AWS_S3_ENABLED", True),
            mock.patch.object(config, "USE_ASYNC_UPLOADS", False),
            mock.patch.object(config, "S3_WRITE_ENABLED", s3_write, create=True),
            mock.patch.object(config, "R2_MIRROR_ENABLED", r2_mirror_on),
        ]
        for p in patches:
            p.start()
        try:
            with mock.patch.object(files_mod, "check_existing_and_upload_to_s3") as s3, mock.patch.object(
                files_mod, "store_files_to_disk"
            ) as disk, mock.patch.object(files_mod, "mirror_to_r2") as mirror:
                files_mod.store_files(db=mock.Mock(), filename=_FILENAME, decoded_base64=b"bytes", mime_type="image/png")
                return s3, disk, mirror
        finally:
            for p in patches:
                p.stop()

    def test_s3_write_disabled_skips_s3_but_mirrors(self):
        s3, disk, mirror = self._run(s3_write=False, r2_mirror_on=True)
        s3.assert_not_called()  # S3 write suppressed
        disk.assert_not_called()  # and no disk fallback either
        mirror.assert_called_once()  # R2 mirror still runs -> R2 becomes the sole sink

    def test_s3_write_enabled_does_both(self):
        s3, disk, mirror = self._run(s3_write=True, r2_mirror_on=True)
        s3.assert_called_once()  # dual-write: S3 ...
        mirror.assert_called_once()  # ... AND R2

    def test_default_s3_only_when_mirror_off(self):
        s3, disk, mirror = self._run(s3_write=True, r2_mirror_on=False)
        s3.assert_called_once()
        mirror.assert_not_called()  # today's behavior unchanged


if __name__ == "__main__":
    unittest.main()
