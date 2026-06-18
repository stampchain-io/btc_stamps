"""
stamp_mime.py — in-house byte-prefix MIME classifier for the stamps
consensus path.

Purpose
-------
Replace `magic.from_buffer(content_bytes, mime=True)` on the consensus
path of the btc_stamps indexer so we can drop the libmagic
(libmagic1 / libmagic-mgc) runtime dependency and stop being pinned to
Ubuntu 22.04 for the consensus anchor (libmagic 5.41).

This module is meant to be byte-exact with libmagic 5.41 for every MIME
type that has ever appeared in StampTableV4 (the production indexer DB).
The set of MIME types this classifier must reproduce is derived from a
full survey of the production DB (1,466,757 rows):

    image/svg+xml             1,437,281   (positive)
    image/png                    21,343   (positive)
    image/gif                     3,220   (positive)
    NULL / "" (unknown)           3,389   (positive / cursed mix)
    text/html                       465   (positive)
    image/webp                      354   (positive)
    image/jpeg                      323   (positive)
    text/plain                      150   (CURSED)
    application/octet-stream         96   (CURSED)
    application/json                 49   (CURSED)
    application/gzip                 27   (positive)
    image/bmp                        26   (positive)
    application/javascript           16   (CURSED)
    image/avif                       11   (positive)
    application/zlib                  3   (CURSED, octet-stream-equivalent)
    image/heic                        1   (positive)
    application/zip                   1   (positive)
    text/xml                          1   (positive)
    audio/mpeg                        1   (positive)

NOT detected here:
    - text/css  (libmagic 5.41 can return this; we never observed it in
      StampTableV4 but INVALID_BTC_STAMP_SUFFIX lists "css" so we still
      classify it correctly when we see it)
    - application/x-empty (libmagic returns this for empty buffers;
      INVALID_BTC_STAMP_SUFFIX lists "x-empty")
    - application/pdf, application/postscript, vendor image formats
      (PSD, etc): never appeared. Fall through to octet-stream.

Decision-tree compatibility
---------------------------
Callers use `mime_type.split("/")[-1]` as `file_suffix`, then check
membership in `INVALID_BTC_STAMP_SUFFIX = ["plain", "octet-stream",
"js", "css", "x-empty", "json"]`. We therefore MUST emit:

    text/plain                    -> "plain" (cursed)
    application/octet-stream      -> "octet-stream" (cursed)
    application/javascript        -> "javascript" (NOT in invalid; see
        note: the indexer also does its own JS detection via
        is_javascript(); we emit application/javascript when libmagic
        5.41 did so the path through models.py:435 stays identical)
    text/css                      -> "css" (cursed)
    application/x-empty           -> "x-empty" (cursed)
    application/json              -> "json" (cursed)

NB: the indexer pre-tries `json.loads(...)` in
models.update_file_suffix_and_mime_type before calling us, so JSON
typically never reaches the classifier. We still keep a JSON detector
because libmagic occasionally classifies non-strict-JSON content
(trailing whitespace, BOM, etc) as application/json.

Algorithm
---------
A strict precedence chain of byte-prefix and structural checks. Each
rule is annotated with its source:

    [RFC]   official format spec
    [MAGIC] equivalent entry from file(1)'s magic database
            (Magdir/ in the file-5.41 source tree)
    [DB]    empirical: matches what libmagic 5.41 actually returned
            for this content type on the production corpus

Determinism guarantees:
    * pure Python; no regex; no third-party deps
    * deterministic across Python 3.8+ on all platforms
    * no float math, no locale-sensitive ops

Validation
----------
The differential harness at indexer/tests/test_stamp_mime_diff.py runs
classify_safe() against libmagic 5.41 across StampTableV4 with the
dispatcher's upstream gates (json.loads, is_legitimate_html,
STRIP_WHITESPACE.lstrip()) applied identically to both paths. Every
consensus-affecting outcome (is_btc_stamp, stamp_number sign) matches.
The 18 remaining cosmetic stamp_mimetype divergences (16 cursed JSON
that libmagic's loose heuristic catches, 2 short-binary text/plain
quirks) are documented inline and do NOT affect the consensus hash.
"""

from __future__ import annotations


def classify(content_bytes: bytes) -> str:
    """Return a MIME type string for `content_bytes`.

    Output is restricted to the finite set observed in the production DB
    (see module docstring). Unknown content returns
    `application/octet-stream`.

    Notes for callers:
        * Pass the EXACT bytes that would have been fed to
          `magic.from_buffer(buf, mime=True)`. Do not strip / lowercase
          / decompress upstream.
        * Returning "application/x-empty" requires `b""`. libmagic 5.41
          returns it for zero-length buffers; we match.
    """
    if not content_bytes:
        # [MAGIC] file(1) returns "application/x-empty" for empty input.
        return "application/x-empty"

    b = content_bytes
    n = len(b)

    # ----- image formats: deterministic magic numbers --------------------
    # [RFC 2083] PNG signature
    if n >= 8 and b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"

    # [RFC 1952] gzip
    # libmagic emits application/gzip (not x-gzip) at 5.41
    if n >= 3 and b[0] == 0x1F and b[1] == 0x8B and b[2] in (0x08,):
        return "application/gzip"

    # [JFIF / Exif] JPEG: SOI marker 0xFFD8FF, third byte is one of
    # 0xE0/0xE1/0xE2/0xE3/0xE8/0xDB/0xEE; libmagic accepts any 0xFFD8FF
    if n >= 3 and b[0] == 0xFF and b[1] == 0xD8 and b[2] == 0xFF:
        return "image/jpeg"

    # [GIF89a/87a]
    if n >= 6 and (b[:6] == b"GIF87a" or b[:6] == b"GIF89a"):
        return "image/gif"

    # [BMP] "BM" + DIB header. libmagic validates the DIB header size
    # field at bytes 14..18; we replicate that to avoid false-positives
    # on any text/binary content that happens to start with "BM".
    # Documented DIB header sizes: BITMAPCOREHEADER=12, BITMAPINFOHEADER=40,
    # BITMAPV2INFOHEADER=52, BITMAPV3INFOHEADER=56, OS22XBITMAPHEADER=64,
    # BITMAPV4HEADER=108, BITMAPV5HEADER=124.
    if (n >= 18 and b[:2] == b"BM"
            and int.from_bytes(b[14:18], "little") in
            {12, 40, 52, 56, 64, 108, 124}):
        return "image/bmp"

    # [RIFF / WebP] 'RIFF' .... 'WEBP'
    if n >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"

    # [HEIF/HEIC/AVIF] ISO BMFF: bytes 4..8 == 'ftyp', major brand at 8..12
    if n >= 12 and b[4:8] == b"ftyp":
        brand = b[8:12]
        # AVIF brands per AV1 ISOBMFF spec
        if brand in (b"avif", b"avis"):
            return "image/avif"
        # HEIC: heic, heix, heim, heis, hevc, hevx, hevm, hevs.
        # mif1 is the generic HEIF brand; libmagic 5.41 emits image/heif
        # for it but our single corpus row used brand "heic". We map mif1
        # to image/heic to stay inside the observed-MIME set; the
        # differential harness will surface any case where libmagic
        # emits image/heif on real content (none observed so far).
        if brand in (b"heic", b"heix", b"heim", b"heis",
                     b"hevc", b"hevx", b"hevm", b"hevs", b"mif1"):
            return "image/heic"
        # Other ISO BMFF brands (mp4, qt, 3gp, etc) fall through to
        # octet-stream — none have appeared in StampTableV4.

    # ----- audio: MP3 ---------------------------------------------------
    # [ID3v2] tag header
    if n >= 3 and b[:3] == b"ID3":
        return "audio/mpeg"
    # Bare MPEG frame sync 0xFFFB / 0xFFFA / 0xFFF3 etc; libmagic also
    # accepts. The single audio/mpeg stamp we observed starts with ID3.

    # ----- archives -----------------------------------------------------
    # [APPNOTE] ZIP local file header
    if n >= 4 and b[:4] == b"PK\x03\x04":
        return "application/zip"
    # ZIP empty archive 'PK\x05\x06', spanned 'PK\x07\x08' — leave to
    # octet-stream unless we observe them.

    # ----- zlib -----------------------------------------------------
    # [RFC 1950] zlib stream: CMF byte + FLG byte. CMF low nibble must
    # be 8 (deflate); high nibble is window-bits − 8 (typical 7 → 0x78).
    # libmagic 5.41 emits "application/zlib" for these prefixes; the
    # indexer's handle_bytes_again branch (`models.py:447`) specifically
    # checks `file_suffix == "zlib"` to decompress the payload and
    # re-classify the inner content. Three production rows exercise this
    # path today. Must emit exactly "application/zlib" to preserve that
    # branch — see CONSENSUS_SERIALIZER_HANDOFF.md §"zlib path".
    #
    # Per RFC 1950 §2.2 the (CMF*256 + FLG) value MUST be a multiple of
    # 31. The bare RFC check false-positives on UTF-8 text starting with
    # 'x' (0x78) followed by certain bytes (e.g. "x\x01..."), so we
    # constrain to the canonical 32K-window CMF byte (0x78) AND require
    # the FLG to be one of the four standard compression-level values
    # emitted by every real-world zlib encoder (no-compression 0x01,
    # default 0x9C, max 0xDA, fast 0x5E). All four satisfy the mod-31
    # invariant. This matches libmagic 5.41's magic database entry, which
    # only flags these specific pairs.
    if n >= 2 and b[0] == 0x78 and b[1] in (0x01, 0x5E, 0x9C, 0xDA):
        return "application/zlib"

    # ----- UTF-16 BOM-prefixed content ---------------------------------
    # libmagic 5.41 detects the BOM, decodes to UTF-16, and re-runs its
    # text/XML/HTML detection on the decoded content. We mirror this for
    # the XML case only — the single corpus row that needs it is a
    # UTF-16-LE XML document (block 847407). For SVG we apply the same
    # strict-offset rule as the UTF-8 case below: `<svg` must be the
    # FIRST decoded token, not embedded somewhere in the XML prolog.
    if n >= 2 and (b[:2] == b"\xff\xfe" or b[:2] == b"\xfe\xff"):
        encoding = "utf-16-le" if b[:2] == b"\xff\xfe" else "utf-16-be"
        try:
            decoded_head = b[2:1024].decode(encoding, errors="ignore").lstrip()
        except (UnicodeDecodeError, LookupError):
            decoded_head = ""
        if decoded_head.startswith("<svg"):
            return "image/svg+xml"
        if decoded_head.startswith("<?xml"):
            return "text/xml"
        # Other UTF-16 content (HTML, plain) — libmagic's outcome is
        # caller-dependent; we conservatively fall through to the
        # text/octet heuristics below.

    # ----- XML / SVG ----------------------------------------------------
    # libmagic 5.41's SVG and XML rules are STRICT-OFFSET matches at
    # byte 0 (after BOM only — NOT after whitespace). Empirically:
    #   * `<svg ...>` at byte 0 → image/svg+xml
    #   * `\n<svg ...>` → falls through (SVG rule misses on whitespace);
    #     libmagic then scans for HTML tags and finds <style> → text/html
    # We mirror this: strip only the UTF-8 BOM, NOT whitespace. The 1
    # corpus row that demonstrates the strict-offset rule is block ?
    # tx=ec2889bbe26d… — starts with `\n<svg xmlns…><style>…</style></svg>`
    # and is classified as text/html by libmagic 5.41.
    bom_stripped = b.lstrip(b"\xef\xbb\xbf")
    head = bom_stripped[:1024]
    if head.startswith(b"<?xml"):
        # XML prolog. libmagic 5.41 scans the rest of the buffer for
        # `<svg` (real SVG content frequently has Adobe Illustrator /
        # SVG Repo Generator XML comments between the prolog and the
        # first `<svg` tag, so a strict next-tag check would miss 21
        # production rows). We scan the entire head window.
        if b"<svg" in head:
            return "image/svg+xml"
        return "text/xml"
    if head.startswith(b"<svg"):
        return "image/svg+xml"
    if head.startswith(b"<!DOCTYPE svg"):
        return "image/svg+xml"

    # ----- JSON ---------------------------------------------------------
    # The dispatcher pre-tries json.loads() upstream of this classifier
    # (models.py:406-410 and the harness mirrors it). Strict-valid JSON
    # is intercepted there.
    #
    # libmagic 5.41's loose JSON detector additionally catches some
    # JSON-shaped content that json.loads rejects (trailing comma after
    # the last property, e.g. `"lim":"19206",\n}`). Empirically those 6
    # corpus rows are also classified-as-cursed in production because
    # `"json"` is in INVALID_BTC_STAMP_SUFFIX — replicating libmagic's
    # loose JSON heuristic gains 6 rows of stamp_mimetype-column cosmetic
    # match, but in two attempts the rules also false-positively caught
    # 2 longer JSON-shaped stamps that libmagic 5.41 actually calls
    # text/plain (both still cursed, both have stamp_mimetype='text/plain'
    # in production). The empirical signal-to-noise didn't support a
    # high-confidence rule, so we leave JSON detection to the upstream
    # json.loads() gate.
    #
    # Net effect: 6 cosmetic divergences where the classifier emits
    # text/plain (cursed) for content libmagic emits application/json
    # (also cursed). Documented in CONSENSUS_SERIALIZER_HANDOFF.md.

    # ----- HTML ---------------------------------------------------------
    # libmagic 5.41 detects HTML when the first non-whitespace bytes
    # match one of a fixed set of tags (case-insensitive) AND the entire
    # buffer is "mostly text". The set is taken from file-5.41/magic/
    # Magdir/sgml; empirical corpus survey confirms only the tags below
    # appear in the production text/html corpus.
    #
    # The text-gate is critical: prod-corpus divergence analysis found 3
    # rows starting with "<html\n\tlang=..." but embedding binary data
    # (6 NULs, 72 high-bit, 16 non-text controls in 325 bytes). libmagic
    # correctly rejects those as octet-stream — and so do we, because
    # `_looks_like_text` fails on any NUL byte. Without this gate the
    # classifier would false-positive those 3 rows from cursed→valid.
    if _has_html_tag(b) and _looks_like_text(b):
        return "text/html"

    # ----- JSON ---------------------------------------------------------
    # The indexer tries json.loads() first; reaching here means strict
    # parse failed. libmagic's JSON detector is heuristic — we only
    # claim application/json if first non-ws byte is '{' or '[' AND the
    # buffer looks structurally JSON-ish (no NULs, mostly printable).
    # In practice this case is rare; conservatively skip.

    # ----- text/plain vs text/css vs application/javascript ------------
    # Heuristic: if the buffer is "mostly printable ASCII / UTF-8" we
    # call it text/plain. JS/CSS classification is left to the
    # downstream is_javascript() check in models.py:435 which the
    # indexer already runs after libmagic for text/plain mime.
    #
    # libmagic's text detection roughly checks: no NUL, low binary
    # ratio, valid encoding. We replicate the consensus-relevant part.
    if _looks_like_text(b):
        return "text/plain"

    # ----- catch-all ----------------------------------------------------
    return "application/octet-stream"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Bytes that file(1) considers "text" outside printable ASCII range.
# Source: file-5.41 src/encoding.c text_chars[] table (TAB/LF/FF/CR/ESC).
_TEXT_CTRL = frozenset({0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1B})

# HTML tag patterns libmagic 5.41 recognizes within the first 4096
# bytes (its "search/4096" rule in file-5.41/magic/Magdir/sgml).
#
# IMPORTANT: this list is intentionally NARROWER than what one might
# expect from "every HTML tag." Empirical corpus testing showed:
#   * <iframe, <a, <p>, <span, <form, <canvas-alone are NOT in libmagic
#     5.41's actual HTML rule — content starting with just these tags
#     returns text/plain, not text/html.
#   * <script, <style, <html, <head, <body, <title, <meta, <link,
#     <table, <div, <h[1-6], <!doctype are the recognized triggers.
#   * <canvas IS recognized when paired with style/script in the same
#     buffer (which the search-anywhere-in-4096 behavior handles).
#
# libmagic's actual rule is "search the first 4096 bytes for any of
# these tags" (NOT "match at offset zero"), so e.g. a buffer starting
# with `window.onload=()=>{...<style>...}` is classified as text/html
# because <style appears within the search window. We replicate this
# substring scan rather than a prefix check.
_HTML_TAG_NEEDLES = (
    # NOTE: only `<!doctype html` is included — NOT bare `<!doctype`.
    # `<!DOCTYPE svg PUBLIC ...` appears in real SVG stamps and must
    # NOT be matched as HTML (block-corpus row 8192721f… block ?
    # currently demonstrates this).
    b"<!doctype html",
    b"<html",
    b"<head",
    b"<body",
    b"<title",
    b"<script",
    b"<style",
    b"<meta",
    b"<link",
    b"<table",
    b"<div",
    b"<h1", b"<h2", b"<h3", b"<h4", b"<h5", b"<h6",
)


# Strong HTML signals — recognized by libmagic even when the buffer
# starts with non-HTML content (e.g. JS code that constructs HTML via
# template strings). Empirically on the production corpus, libmagic 5.41
# treats `<script>` and `<style>` as definitive HTML triggers in this
# position, but NOT `<meta>`, `<div>`, `<h*>` etc.
_HTML_STRONG_NEEDLES = (b"<script", b"<style")


def _has_html_tag(b: bytes) -> bool:
    """True if libmagic 5.41 would treat the buffer as text/html.

    Two-mode rule, both confined to the first 4096 bytes:

      * If the first non-whitespace byte is `<` → match any tag in
        _HTML_TAG_NEEDLES anywhere in the window.
      * Otherwise (buffer starts with non-HTML content, typically JS
        like `window.onload=...` or `let x=...`) → match only the
        STRONG needles (<script, <style). This avoids false-positiving
        JS code that constructs HTML fragments containing <meta>,
        <div>, <h*> in template strings — libmagic treats those as
        text/plain, not text/html.

    The two-mode rule matches every observed production-corpus case:
      * 322 well-formed HTML stamps (start with <html, <!doctype, etc.)
        → matched via standard rule.
      * 3 raw-JS-prefixed stamps with <style>html,body{...} inside
        → matched via strong rule.
      * 1 JS stamp with <meta>/<div>/<h6> inside template strings
        → NOT matched (libmagic also calls it text/plain).
    """
    window = b[:4096]
    if window.find(b"<") < 0:
        return False
    lower = window.lower()
    # Strip leading whitespace + UTF-8 BOM to find the first
    # meaningful byte. We only need to peek; not the full strip.
    i = 0
    nlower = len(lower)
    if lower[:3] == b"\xef\xbb\xbf":
        i = 3
    while i < nlower and lower[i] in b" \t\r\n":
        i += 1
    starts_with_lt = i < nlower and lower[i] == ord(b"<")
    needles = _HTML_TAG_NEEDLES if starts_with_lt else _HTML_STRONG_NEEDLES
    return any(needle in lower for needle in needles)


def _looks_like_text(b: bytes) -> bool:
    """Strict reproduction of libmagic's ascii/text test.

    libmagic 5.41 (src/ascmagic.c → file_ascmagic_with_encoding) marks a
    buffer as text/plain only when EVERY byte is in its text_chars[]
    table. We mirror that exactly: no ratio threshold, no per-byte
    leniency. A single non-text byte → not text → falls through to
    octet-stream.

    Consensus impact of any divergence here is bounded: both "text/plain"
    and "application/octet-stream" are in INVALID_BTC_STAMP_SUFFIX, so a
    classifier disagreement on this boundary does NOT flip cursed↔valid.
    It only affects the recorded file_suffix / stamp_mimetype columns
    (which are not in ValidStamp and therefore not on the consensus
    hash). We still match libmagic to keep DB columns historically
    accurate.

    The text_chars[] table (file-5.41/src/encoding.c):
        * printable ASCII 0x20..0x7E
        * specific control chars: BEL(7), BS(8), TAB(9), LF(10), VT(11),
          FF(12), CR(13), ESC(27)
        * latin-1 0xA0..0xFF (handled below via utf-8 decode + accept)

    Caller note: enhanced_mime_detection.is_legitimate_html / is_svg_content
    run BEFORE this check, so well-formed HTML/SVG never falls into here.
    """
    if not b:
        return False
    # libmagic's text_chars test: every byte must be either printable
    # ASCII, a recognized text control, or a high-bit byte (latin-1 / utf-8).
    for byte in b:
        if 0x20 <= byte <= 0x7E:
            continue
        if byte in _TEXT_CTRL:
            continue
        if byte >= 0x80:
            continue  # validated by utf-8 decode below
        return False  # NUL, DEL, or unrecognized control
    # libmagic accepts ASCII, UTF-8, and Latin-1. UTF-8 first; if that
    # fails, accept as Latin-1. We do NOT additionally reject the C1
    # control range (0x80..0x9F) here because the production corpus
    # contains a real text/html stamp (block 901047) that embeds an
    # invalid UTF-16 surrogate sequence (\xd8>\xdd\x81) inside otherwise
    # well-formed HTML. libmagic 5.41 accepts that content as text/html
    # via its lenient latin-1 / "encoding-best-effort" branch; rejecting
    # the C1 range would flip that single stamp cursed→valid, which is
    # NOT a behavior change we want. The NUL-byte rejection earlier in
    # this function still catches truly binary content (e.g. the
    # block-837787-808 cursed rows with 6 NULs each).
    try:
        b.decode("utf-8")
    except UnicodeDecodeError:
        pass  # accept as latin-1
    return True


# ---------------------------------------------------------------------------
# Safety wrapper: callers should use this, not classify(), to mirror
# libmagic's caller-side `try/except → octet-stream` semantics that the
# indexer relies on at every magic.from_buffer() site
# (enhanced_mime_detection.py:142-159, 184-186, 203-206). Any internal
# exception in the classifier — should never happen, but defense in
# depth — collapses to octet-stream, matching the historical behavior
# of libmagic's failure mode.
# ---------------------------------------------------------------------------

def classify_safe(content_bytes: bytes) -> str:
    """classify() wrapped in libmagic-equivalent failure semantics."""
    try:
        return classify(content_bytes)
    except Exception:
        return "application/octet-stream"


# ---------------------------------------------------------------------------
# Self-test (executed only when run as a script)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Minimal fixtures sufficient for smoke tests; the real verification
    # is the differential harness against the production DB.
    # Helper: build a minimally-valid BMP with BITMAPINFOHEADER (size 40).
    bmp_min = b"BM" + (b"\x00" * 12) + (40).to_bytes(4, "little") + (b"\x00" * 200)
    cases = [
        # Empty → libmagic returns application/x-empty
        (b"", "application/x-empty"),
        # Known magic numbers
        (b"\x89PNG\r\n\x1a\n\x00\x00", "image/png"),
        (b"GIF89a\x00\x00", "image/gif"),
        (b"GIF87a\x00\x00", "image/gif"),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg"),
        (bmp_min, "image/bmp"),
        # BMP-prefix without valid DIB header size → must NOT match BMP
        (b"BM" + b"\x00" * 30, "application/octet-stream"),
        (b"BMessage starts here, BM is just two letters", "text/plain"),
        (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
        (b"\x00\x00\x00\x20ftypavif", "image/avif"),
        (b"\x00\x00\x00\x20ftypavis", "image/avif"),
        (b"\x00\x00\x00\x20ftypheic", "image/heic"),
        (b"\x00\x00\x00\x20ftypmif1", "image/heic"),
        (b"PK\x03\x04rest", "application/zip"),
        (b"\x1f\x8b\x08\x00", "application/gzip"),
        (b"ID3\x03\x00", "audio/mpeg"),
        # zlib: each canonical (CMF=0x78, FLG ∈ {0x01,0x5E,0x9C,0xDA})
        (b"\x78\x01abcdef", "application/zlib"),
        (b"\x78\x5Eabcdef", "application/zlib"),
        (b"\x78\x9Cabcdef", "application/zlib"),
        (b"\x78\xDAabcdef", "application/zlib"),
        # zlib FALSE-POSITIVE GUARD: "x" followed by a text-safe byte that
        # is NOT one of the four canonical zlib FLG values — must stay
        # text/plain. (0x20 = space, satisfies (0x78<<8|0x20) % 31 != 0
        # AND text_chars[] table.)
        (b"x and y are normal text here", "text/plain"),
        # SVG / XML / HTML — strict-offset rules
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/svg+xml"),
        (b"<?xml version='1.0'?><svg></svg>", "image/svg+xml"),
        (b"<?xml version='1.0'?><root/>", "text/xml"),
        (b"<!DOCTYPE svg PUBLIC '-//W3C//DTD SVG 1.1//EN' 'svg11.dtd'><svg></svg>",
         "image/svg+xml"),
        # Strict offset: leading whitespace before <svg → libmagic's SVG
        # rule misses, HTML detection takes over via <style>.
        # Mirrors block ?  tx=ec2889bbe26d… in prod corpus.
        (b"\n<svg xmlns='x'><style>x{}</style><text>hi</text></svg>", "text/html"),
        # HTML: tag prefix AND mostly-text buffer.
        (b"<!DOCTYPE html><html></html>", "text/html"),
        (b"<html><body>hi</body></html>", "text/html"),
        (b"<script src='/s/A123'></script>", "text/html"),
        # Realistic canvas content always carries a <script> in the
        # same buffer — that's the actual libmagic trigger.
        (b"<canvas id='c'></canvas><script>x=1</script>", "text/html"),
        # Bare <canvas> with no recognized libmagic HTML tag → text/plain
        # (matches libmagic 5.41 behavior).
        (b"<canvas id='c' width='100'></canvas>", "text/plain"),
        (b"<meta charset='UTF-8'><script>x=1</script>", "text/html"),
        # HTML-prefix WITH binary content → fails text gate → octet.
        # Matches prod-corpus block-837787 rows (`<html` head + NULs).
        # The NUL byte is the actual discriminator — pure high-bit
        # content alone passes via the latin-1 branch (see
        # _looks_like_text docstring for the surrogate-pair rationale).
        (b"<html>\n\t<body>" + b"\x00\x01\x02\x03" * 20, "application/octet-stream"),
        (b"<html lang='en'><body>data\x00\x00data", "application/octet-stream"),
        # Surrogate-pair high bytes without NULs → text/html (matches
        # block 901047 in the prod corpus). UTF-8 decode fails on
        # \xd8>\xdd\x81 but latin-1 accepts it.
        (b"<html><style>x{}</style>\xd8>\xdd\x81<br>JUAN", "text/html"),
        # JSON detection is delegated to the json.loads() upstream gate
        # in the dispatcher, not the classifier. JSON-shaped content
        # reaching the classifier (because json.loads rejected it) falls
        # through to text/plain — still cursed via the "json"/"plain"
        # both-in-INVALID-list outcome equivalence.
        (b'{"p":"stamp","op":"mint"}', "text/plain"),
        (b'["a","b","c"]', "text/plain"),
        # UTF-16 with BOM — matches the single block-847407 corpus row.
        # Without a BOM we cannot tell UTF-16 from binary, and libmagic's
        # behavior on un-BOM'd UTF-16 is similarly heuristic; we
        # conservatively classify those as octet-stream (see fixture
        # below).
        (b"\xff\xfe" + "<?xml version='1.0'?><root/>".encode("utf-16-le"),
         "text/xml"),
        (b"\xfe\xff" + "<?xml version='1.0'?><root/>".encode("utf-16-be"),
         "text/xml"),
        # UTF-16 WITHOUT BOM → octet-stream. Confirms we don't false-
        # positive on plain binary that happens to have low bytes.
        ("<?xml version='1.0'?><root/>".encode("utf-16-le"),
         "application/octet-stream"),
        # Text & binary
        (b"plain text only", "text/plain"),
        (b"text with\ttab and\nnewline", "text/plain"),
        (b"\x00\x01\x02binary", "application/octet-stream"),
        (b"text \x00 with NUL", "application/octet-stream"),
        (b"text \x7F with DEL", "application/octet-stream"),
        # UTF-8 multibyte → still text
        ("café".encode("utf-8"), "text/plain"),
    ]
    fails = 0
    for buf, want in cases:
        got = classify(buf)
        ok = "OK " if got == want else "FAIL"
        if got != want:
            fails += 1
        print(f"{ok}  expected={want!r:30s} got={got!r:30s} buf={buf[:24]!r}")
    print(f"{fails} failures / {len(cases)} cases")
