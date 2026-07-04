"""Structural-validation tests for ``stamp_mime.classify``.

These pin the classifier's libmagic-equivalent behavior. The validators
are intentionally LENIENT — they accept any buffer with a valid magic
prefix + minimum structural header, matching libmagic 5.41 on prod:

    PNG:  signature(8) + IHDR length=13 + 'IHDR' type
    JPEG: SOI(FFD8) + FFD8FF + recognized marker byte (E0/E1/E2/E3/E8/DB/EE/C0/C4)
    GIF:  signature(GIF87a|GIF89a) + 7-byte LSD
    WEBP: 'RIFF' + 4 + 'WEBP' + sub-chunk header (VP8/VP8L/VP8X)
    BMP:  'BM' + known DIB header size (12/40/52/56/64/108/124)
    GZIP: \\x1f\\x8b\\x08 magic
    ISO-BMFF (AVIF/HEIC): ftyp box at offset 4

Earlier stricter implementations (PNG IEND walk, GIF 0x3B trailer, JPEG
EOI walk) over-rejected truncated images that prod accepted as the
proper MIME — those caused fresh consensus divergences. The agreed
design is: classifier matches libmagic exactly (accept anything with
valid magic+minimum-header), and "damaged content should be cursed"
is handled UPSTREAM in `decode_base64` tier-3 (binary inputs that
fail utf-8 decode return (None, None) → handle_unknown_type →
ident=UNKNOWN → cursed). See PR #753 for the e3672c7b… reference case.

Fixtures are drawn from production ``StampTableV4``.

Each fixture tuple is ``(tx_hash_prefix, base64_payload)``.
"""

from __future__ import annotations

import base64

import pytest

from index_core.stamp_mime import classify

# ---------------------------------------------------------------------------
# Positive fixtures from prod — must classify as the indicated MIME.
# ---------------------------------------------------------------------------

PNG_POSITIVE = [
    (
        "1731fe97",
        "iVBORw0KGgoAAAANSUhEUgAAAEIAAABDBAMAAADaJs5+AAAAMFBMVEUPAA8MCTMUD2XwqiPu+vUYLJEeVbgehNcsFg/01FIwteyr4POYVhRjJwx4s9jGhBxYtqbHAAAAAElFTkSuQmCC",
    ),
    # Minimum: signature + IHDR length + 'IHDR' type = 16 bytes
    ("png_min", "iVBORw0KGgoAAAANSUhEUg=="),
]

JPEG_POSITIVE = [
    # SOI + JFIF marker (E0)
    ("jpeg_jfif", "/9j/4AAQ"),
    # SOI + Exif marker (E1)
    ("jpeg_exif", "/9j/4QAQ"),
    # SOI + DQT (raw)
    ("jpeg_dqt", "/9j/2wAQ"),
]

GIF_POSITIVE = [
    # GIF89a + 7-byte Logical Screen Descriptor
    ("gif89a_min", "R0lGODlhAQABAAAAACwAAAAAAQABAAACAkQBADs="),
    ("gif87a_min", "R0lGODdhAQABAIAAAP///wAAACwAAAAAAQABAAACAkQBADs="),
]

BMP_POSITIVE = [
    # BM + 14-byte file header + 40-byte BITMAPINFOHEADER
    ("bmp_v3_min", "Qk1aAAAAAAAAADYAAAAoAAAAAQAAAAEAAAABABgAAAAAACQAAAATCwAAEwsAAAAAAAAAAAAAAAAAAAA="),
]

WEBP_POSITIVE = [
    # RIFF + size + WEBP + VP8L
    ("webp_vp8l", "UklGRiYAAABXRUJQVlA4ICAAAACyAQCdASoBAAEAAAAAJaQAA3AA/uuuAAA="),
    # RIFF + size + WEBP + VP8 (lossy)
    ("webp_vp8", "UklGRiwAAABXRUJQVlA4ICAAAACQAQCdASoBAAEAAUAmJZwAA3AA/v3+UAAA"),
]

GZIP_POSITIVE = [
    # gzip magic + deflate
    ("gzip_min", "H4sIAAAAAAAAA0vJzAUAlR/I8wMAAAA="),
]


def _decode(b64: str) -> bytes:
    return base64.b64decode(b64)


@pytest.mark.parametrize("tx,b64", PNG_POSITIVE, ids=[t[0] for t in PNG_POSITIVE])
def test_png_valid_stays_image_png(tx, b64):
    assert classify(_decode(b64)) == "image/png", tx


@pytest.mark.parametrize("tx,b64", JPEG_POSITIVE, ids=[t[0] for t in JPEG_POSITIVE])
def test_jpeg_valid_stays_image_jpeg(tx, b64):
    assert classify(_decode(b64)) == "image/jpeg", tx


@pytest.mark.parametrize("tx,b64", GIF_POSITIVE, ids=[t[0] for t in GIF_POSITIVE])
def test_gif_valid_stays_image_gif(tx, b64):
    assert classify(_decode(b64)) == "image/gif", tx


@pytest.mark.parametrize("tx,b64", BMP_POSITIVE, ids=[t[0] for t in BMP_POSITIVE])
def test_bmp_valid_stays_image_bmp(tx, b64):
    assert classify(_decode(b64)) == "image/bmp", tx


@pytest.mark.parametrize("tx,b64", WEBP_POSITIVE, ids=[t[0] for t in WEBP_POSITIVE])
def test_webp_valid_stays_image_webp(tx, b64):
    assert classify(_decode(b64)) == "image/webp", tx


@pytest.mark.parametrize("tx,b64", GZIP_POSITIVE, ids=[t[0] for t in GZIP_POSITIVE])
def test_gzip_valid_stays_gzip(tx, b64):
    assert classify(_decode(b64)) == "application/gzip", tx


# ---------------------------------------------------------------------------
# Short-buffer rejection. Buffers TOO SHORT to satisfy the minimum
# libmagic-equivalent gate must fall through to octet-stream.
# ---------------------------------------------------------------------------


def test_png_signature_only_is_octet_stream():
    # 8 bytes < 16 byte minimum (signature + IHDR length + 'IHDR')
    assert classify(b"\x89PNG\r\n\x1a\n") == "application/octet-stream"


def test_jpeg_soi_only_no_marker_is_octet_stream():
    # SOI but no recognized marker after FFD8FF
    assert classify(b"\xff\xd8\xff\x00") == "application/octet-stream"


def test_gif_header_only_no_lsd_is_octet_stream():
    # Just 'GIF89a' without the 7-byte Logical Screen Descriptor
    assert classify(b"GIF89a") == "application/octet-stream"


def test_webp_riff_only_no_subchunk_is_octet_stream():
    # 'RIFF' + size + 'WEBP' but no sub-chunk header
    assert classify(b"RIFF\x00\x00\x00\x00WEBP") == "application/octet-stream"


def test_ftyp_with_short_box_is_octet_stream():
    # ISO-BMFF ftyp box but box size < 16
    assert classify(b"\x00\x00\x00\x04ftypavif") == "application/octet-stream"


# ---------------------------------------------------------------------------
# Empty + unknown buffers.
# ---------------------------------------------------------------------------


def test_empty_buffer():
    assert classify(b"") == "application/x-empty"


def test_random_binary_is_octet_stream():
    assert classify(b"\x00\x01\x02\x03\xff\xfe\xfd\x42" * 10) == "application/octet-stream"


def test_unknown_format_pdf_is_text_plain():
    # PDF starts with '%PDF' which is ASCII — falls through to text/plain
    # detection. text/plain ∈ INVALID_BTC_STAMP_SUFFIX, so still cursed.
    assert classify(b"%PDF-1.5\n%\xc7\xec\x8f\xa2\n3 0 obj") == "text/plain"
