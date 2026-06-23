"""
Golden tests for the consensus-path MIME detection heuristics.

These three functions are now the PRIMARY classification path after the
libmagic replacement (PR #753): they run in the dispatcher BEFORE the
in-house byte-prefix classifier (stamp_mime.classify_safe), and their
output directly determines whether content is recorded as valid HTML /
SVG / JS-cursed stamps.

Tests cover:
  * is_legitimate_html  (enhanced_mime_detection.py)
  * is_svg_content      (enhanced_mime_detection.py)
  * is_javascript       (models.StampData method)

Every fixture documents WHY it exists. New fixtures should reference
the production-corpus block number / tx_hash that motivated them.

Adding a fixture pins the behavior — a future Python upgrade, regex
engine change, or refactor that breaks the heuristic will fail this
test rather than silently flipping a stamp's classification on a
fresh-from-genesis reparse.
"""

from __future__ import annotations

import os
import sys

import pytest

# Make src/ importable without requiring poetry install.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "src"))

from index_core.enhanced_mime_detection import (  # noqa: E402
    is_gzip,
    is_legitimate_html,
    is_svg_content,
)

# ---------------------------------------------------------------------------
# is_legitimate_html
# ---------------------------------------------------------------------------
# The function requires: utf-8 decodable, <5% binary bytes, no image
# headers, both <html and <body present, and equal open/close counts for
# both <html> and <body>. Anything else → False.

LEGIT_HTML_FIXTURES = [
    # Minimal well-formed HTML — the canonical positive case.
    (b"<html><body>hi</body></html>", True, "minimal balanced HTML"),
    # Well-formed HTML with whitespace and attributes (corpus pattern).
    (
        b"<html lang='en'>\n<body style='m:0'>\n<h1>x</h1>\n</body>\n</html>",
        True,
        "real-world style attribute + nesting",
    ),
    # Doctype-prefixed HTML — common in modern stamps.
    (
        b"<!DOCTYPE html><html><body><div>x</div></body></html>",
        True,
        "DOCTYPE-prefixed (matches bucket #2 prod corpus pattern)",
    ),
    # Negative: HTML opener but no <body> → not legitimate.
    (b"<html><div>no body tag</div></html>", False, "missing <body>"),
    # Negative: <body> but no <html>.
    (b"<body>hi</body>", False, "missing <html>"),
    # Negative: unbalanced — two <html> opens, one </html>.
    (
        b"<html><html><body>x</body></html>",
        False,
        "unbalanced <html> open/close",
    ),
    # Negative: PNG header — fails the image-header check FIRST.
    (
        b"\x89PNG\r\n\x1a\n<html><body>x</body></html>",
        False,
        "PNG signature short-circuits HTML detection",
    ),
    # Negative: JPEG header.
    (b"\xff\xd8\xff\xe0junk", False, "JPEG SOI marker"),
    # Negative: GIF header.
    (b"GIF89a<html><body>nope</body></html>", False, "GIF87/89a magic"),
    # Negative: binary-heavy content (>5% binary ratio).
    (
        b"<html><body>x</body></html>" + b"\x01\x02\x03\x04\x05" * 20,
        False,
        "binary ratio >5% (matches bucket #6 prod corpus pattern)",
    ),
    # Negative: utf-8-undecodable bytes.
    (b"<html><body>" + b"\xff\xfe\xfd" * 20 + b"</body></html>", False, "utf-8 decode failure"),
    # Negative: empty input → can't decode meaningfully.
    (b"", False, "empty buffer"),
    # Negative: HTML in JS template string (the bucket #2 raw-JS-prefixed corpus rows).
    # Even though <html and <body appear in the string, the surrounding
    # JS code doesn't form well-formed HTML at the document root level.
    # is_legitimate_html ONLY checks tag presence and balance, so this
    # actually returns True — that's a known quirk that the downstream
    # classifier in stamp_mime.py handles correctly via the two-mode
    # _has_html_tag rule. We assert True here to PIN the current
    # behavior; any change should be coordinated with the classifier.
    (
        b'window.onload=()=>{const x="<html><body>x</body></html>"}',
        True,
        "JS template string with embedded HTML — pinned-as-True; coordinate with stamp_mime if changed",
    ),
]


@pytest.mark.parametrize("data,expected,why", LEGIT_HTML_FIXTURES)
def test_is_legitimate_html(data, expected, why):
    """Pin is_legitimate_html behavior — see `why` for fixture rationale."""
    assert is_legitimate_html(data) is expected, f"is_legitimate_html({data[:60]!r}...) → expected {expected}: {why}"


# ---------------------------------------------------------------------------
# is_svg_content
# ---------------------------------------------------------------------------
# Function: decode first 512 bytes as utf-8 (with errors='ignore'),
# lowercase, return True if '<svg' present AND ('xmlns' OR 'viewbox').
# Mirrors the upstream SVG gate that runs before the classifier and the
# libmagic call in the legacy dispatcher branch.

SVG_FIXTURES = [
    # Canonical positive: <svg + xmlns.
    (
        b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        True,
        "<svg + xmlns",
    ),
    # Positive: <svg + viewBox (case-insensitive 'viewbox' substring).
    (
        b'<svg viewBox="0 0 100 100"><circle/></svg>',
        True,
        "<svg + viewBox (case-insensitive match)",
    ),
    # Positive: real-world Adobe Illustrator SVG with XML prolog.
    # (matches the 21 corpus rows in svg+xml→text/xml bucket from
    # libmagic differential round 4).
    (
        b'<?xml version="1.0" encoding="utf-8"?>\n<!-- Generator: Adobe Illustrator -->\n<svg xmlns="x"></svg>',
        True,
        "XML prolog + comment + SVG (Adobe Illustrator corpus pattern)",
    ),
    # Positive: leading whitespace before <svg.
    (
        b'\n   <svg xmlns="x"></svg>',
        True,
        "leading whitespace tolerated",
    ),
    # Negative: <svg without xmlns or viewbox.
    (b"<svg></svg>", False, "bare <svg> without xmlns/viewbox"),
    # Negative: only xmlns, no <svg.
    (
        b'<root xmlns="http://www.w3.org/2000/svg"></root>',
        False,
        "xmlns alone is not enough",
    ),
    # Negative: only viewBox, no <svg (would be a different tag).
    (
        b'<canvas viewBox="0 0 1 1"></canvas>',
        False,
        "viewBox alone is not enough",
    ),
    # Negative: PNG bytes.
    (b"\x89PNG\r\n\x1a\nrest", False, "PNG signature"),
    # Negative: empty.
    (b"", False, "empty buffer"),
    # Boundary: SVG marker beyond the 512-byte default check window.
    (
        b" " * 600 + b'<svg xmlns="x"></svg>',
        False,
        "<svg beyond 512-byte default check window",
    ),
    # Boundary: SVG marker beyond a custom check window.
    (
        b" " * 100 + b'<svg xmlns="x"></svg>',
        True,
        "<svg within default 512 window after 100 bytes of leading space",
    ),
]


@pytest.mark.parametrize("data,expected,why", SVG_FIXTURES)
def test_is_svg_content(data, expected, why):
    assert is_svg_content(data) is expected, f"is_svg_content({data[:60]!r}...) → expected {expected}: {why}"


def test_is_svg_content_with_custom_check_size():
    """The optional max_check_size knob must scale the search window."""
    payload = b" " * 600 + b'<svg xmlns="x"></svg>'
    # Default 512 byte window misses the SVG → False.
    assert is_svg_content(payload) is False
    # Custom 1024 byte window finds it → True.
    assert is_svg_content(payload, max_check_size=1024) is True


# ---------------------------------------------------------------------------
# is_gzip
# ---------------------------------------------------------------------------
# Function: 3-byte signature check — \x1f\x8b\x08.
# Trivial but on the consensus path (gates the gzipped-SVG decompression
# branch in detect_and_decompress_svg). Pin for completeness.

GZIP_FIXTURES = [
    (b"\x1f\x8b\x08\x00data", True, "canonical gzip magic"),
    (b"\x1f\x8b\x08", True, "exactly 3 bytes, the minimum"),
    (b"\x1f\x8b", False, "2 bytes — too short"),
    (b"", False, "empty buffer"),
    # Negative: low-bit gzip variants — only deflate (0x08) qualifies
    # per the function's strict signature.
    (b"\x1f\x8b\x09payload", False, "gzip CM=9 — not standard deflate"),
    (b"\x89PNG\r\n\x1a\n", False, "PNG, not gzip"),
]


@pytest.mark.parametrize("data,expected,why", GZIP_FIXTURES)
def test_is_gzip(data, expected, why):
    assert is_gzip(data) is expected, f"is_gzip({data[:30]!r}) → {expected}: {why}"


# ---------------------------------------------------------------------------
# is_javascript (StampData method)
# ---------------------------------------------------------------------------
# Lives on StampData class in models.py. Instantiating StampData
# requires the full constructor; for golden testing we exercise the
# method bound to a minimal instance.

JS_FIXTURES = [
    # Positive: classic var/let/const + function pattern.
    (b"function add(a, b) { return a + b; }", True, "function declaration"),
    (b"var x = 1; var y = 2; function f() { return x + y; }", True, "var + function"),
    (
        b"let zz; window.onload = () => { let t = window.data; }",
        True,
        "let + arrow function (matches bucket #5 raw-JS corpus pattern)",
    ),
    (
        b'const config = {key: "value"}; class Foo { constructor() {} }',
        True,
        "const + class declaration",
    ),
    # Positive: typeof / instanceof / new.
    (
        b"if (typeof x === 'undefined') { x = new Array(); }",
        True,
        "typeof + new",
    ),
    # Negative: pure HTML.
    (b"<html><body>just html</body></html>", False, "HTML, no JS constructs"),
    # Negative: plain text.
    (b"This is a plain English sentence. No JavaScript here.", False, "plain text"),
    # Negative: empty.
    (b"", False, "empty buffer"),
    # Boundary: utf-8 decode tolerance (errors='ignore') for non-text bytes.
    (b"function f() {} \xff\xfe", True, "JS prefix + binary suffix decodes OK"),
]


def _make_stampdata_for_is_javascript():
    """Construct a minimal StampData instance to access is_javascript.

    The method only reads bytestring_data passed in, so we don't need a
    fully populated instance — just one we can call the method on.
    """
    # Late import: the SRC-20 + Counterparty config touches a lot of
    # global state; only pay that cost for the JS golden tests.
    from index_core.models import StampData

    # StampData.__init__ requires several args. Pass placeholder values
    # — the is_javascript method doesn't use any instance state.
    return StampData.__new__(StampData)


@pytest.mark.parametrize("data,expected,why", JS_FIXTURES)
def test_is_javascript(data, expected, why):
    sd = _make_stampdata_for_is_javascript()
    assert sd.is_javascript(data) is expected, f"is_javascript({data[:60]!r}) → expected {expected}: {why}"
