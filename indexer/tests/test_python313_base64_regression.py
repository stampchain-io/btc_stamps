"""Consensus regression test for the Python 3.13 base64/binascii divergence (#871).

Root cause found during v1.9.0 certification: Python 3.13 tightened
``binascii.a2b_base64`` (used by ``base64.b64decode``) to reject non-canonical
base64 — embedded ``=`` padding, stray non-alphabet chars, "N data characters
cannot be 1 more than a multiple of 4" — that Python 3.10-3.12 (and production,
on 3.10) decode leniently. Stamps whose payload has non-canonical base64 fail to
decode on 3.13, get mis-classified as cursed/UNKNOWN, and diverge
``txlist_hash`` — first observed at block 783775.

The fix (``index_core.base64_utils.lenient_b64decode``) replaces the stdlib
decoder in the stamp decode path with a single deterministic, version-independent
reimplementation of CPython 3.10 non-strict ``a2b_base64``. This test proves:

  1. the block-783775 payload decodes to the exact 373-byte PNG on EVERY
     interpreter (3.10-3.13) — no xfail, no version branching;
  2. golden non-canonical vectors (computed on 3.10) decode byte-identically on
     every interpreter — the version-invariance proof the CI matrix (3.10-3.13)
     runs directly; and
  3. on 3.10-3.12 the new decoder is byte-identical to the stdlib decoder it
     replaces (output-neutrality vs the consensus baseline), while documenting
     that the stdlib decoder is exactly what breaks on 3.13.

See #871 (make 3.13 a first-class consensus runtime).
"""

import base64
import binascii
import os
import sys

import pytest

from index_core.base64_utils import lenient_b64decode

# Real fixture: the base64 payload of the block-783775 stamp (Counterparty asset
# A13107746912945816000) — a PNG whose base64 has 3 EMBEDDED '=' padding chars
# (first at index 498) and 1476 total chars. Lenient decoders stop at the first
# completed pad -> 373-byte PNG (the 3.10-3.12/prod result); Python 3.13's stdlib
# counts all 1473 data chars and raises (1473 % 4 == 1).
_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "block_783775_stamp.b64")

# PNG magic (\x89PNG\r\n\x1a\n) and the exact decoded length/digest on 3.10-3.12.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_EXPECTED_LEN = 373
_EXPECTED_SHA = "747afb56dd7c9fd4"  # sha256(decoded)[:16]

# Golden vectors: (input, expected decoded bytes as hex). Computed on Python 3.10
# ``base64.b64decode`` — the consensus baseline. lenient_b64decode MUST reproduce
# these on every interpreter, including 3.13 where the stdlib decoder diverges.
_GOLDEN = [
    ("aGVsbG8gd29ybGQ=", "68656c6c6f20776f726c64"),  # canonical: "hello world"
    ("aGVsbG8=Zm9vYmFy", "68656c6c6f"),  # embedded pad terminates: "hello"
    ("aG\nVsb G8=", "68656c6c6f"),  # whitespace / non-alphabet skipped: "hello"
    ("aGVsbG8h", "68656c6c6f21"),  # mod-4, no pad: "hello!"
]


def _payload() -> str:
    with open(_FIXTURE, "r") as f:
        return f.read().strip()


def _sha16(b: bytes) -> str:
    import hashlib

    return hashlib.sha256(b).hexdigest()[:16]


def test_block_783775_lenient_decodes_like_prod_on_every_interpreter():
    """The 783775 stamp payload decodes to the exact 373-byte PNG on ALL versions.

    This is the fix: with lenient_b64decode this passes on 3.10, 3.11, 3.12 AND
    3.13 — i.e. the consensus behavior is now interpreter-independent (#871).
    """
    raw = lenient_b64decode(_payload())
    assert raw[:8] == _PNG_MAGIC, "payload must decode to a PNG (consensus 3.10 behavior)"
    assert len(raw) == _EXPECTED_LEN
    assert _sha16(raw) == _EXPECTED_SHA


@pytest.mark.parametrize("payload,expected_hex", _GOLDEN)
def test_lenient_golden_vectors_are_version_invariant(payload, expected_hex):
    """Golden non-canonical vectors decode byte-identically on every interpreter.

    Runs across the 3.10-3.13 unit-test matrix; asserting the SAME expected bytes
    on all of them is the direct version-invariance proof for the fix (#871)."""
    assert lenient_b64decode(payload).hex() == expected_hex


def test_lenient_is_output_neutral_vs_stdlib_on_3_10_to_3_12():
    """On 3.10-3.12 the new decoder is byte-identical to the stdlib it replaces.

    This anchors output-neutrality vs the consensus baseline. On 3.13 the stdlib
    decoder raises on the 783775 payload (documented below), so the equality is
    only asserted where the stdlib itself is still the lenient baseline."""
    if sys.version_info >= (3, 13):
        pytest.skip("stdlib base64 is no longer the lenient baseline on 3.13 (that is the bug)")
    payload = _payload()
    assert lenient_b64decode(payload) == base64.b64decode(payload)
    for payload_str, _ in _GOLDEN:
        assert lenient_b64decode(payload_str) == base64.b64decode(payload_str)


def test_stdlib_base64_is_the_thing_that_breaks_on_3_13():
    """Characterize WHY we cannot use the stdlib decoder: it splits by version.

    Passes on ALL versions (asserts the version-appropriate stdlib behavior) so
    it documents the divergence without going red — 3.10-3.12 decode the 783775
    payload, 3.13 raises binascii.Error. lenient_b64decode (above) fixes this."""
    payload = _payload()
    if sys.version_info < (3, 13):
        assert base64.b64decode(payload)[:8] == _PNG_MAGIC
    else:
        with pytest.raises(binascii.Error):
            base64.b64decode(payload)
