"""Detection test for the Python 3.13 base64/binascii consensus divergence (#871).

Root cause of the 3.13 consensus break found during v1.9.0 certification:
Python 3.13 tightened ``binascii.a2b_base64`` (used by ``base64.b64decode``) to
reject non-canonical base64 that Python 3.10-3.12 (and production, on 3.10)
decode leniently. Stamps whose payload has a non-canonical base64 length
therefore fail to decode on 3.13, get mis-classified as cursed/UNKNOWN, and
diverge ``txlist_hash`` — first observed at block 783775.

This is a fast, DB-free *detection* test. It runs in the unit-test matrix
(python-check.yml) across Python 3.10-3.13 — which is the only CI that runs
3.13 (the Reparse Consensus gate is 3.10-3.12 only). It:
  * PASSES on 3.10/3.11/3.12 (the consensus-correct, prod-matching behavior), and
  * is a strict XFAIL on 3.13 (documented expected failure).
If 3.13 is ever fixed so the payload decodes correctly again, the strict xfail
flips to XPASS (a CI red), signalling that #871 can re-enable 3.13 as a
consensus runtime.

See #871 (make 3.13 a first-class consensus runtime) and #872 (the v1.9.0
walkback of 3.13 consensus claims).
"""

import base64
import os
import sys

import pytest

# Real fixture: the base64 payload of the block-783775 stamp (Counterparty asset
# A13107746912945816000) — a PNG whose base64 has a non-canonical length. This is
# the exact input that diverges: lenient 373-byte PNG on 3.10-3.12, binascii.Error
# on 3.13.
_FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "block_783775_stamp.b64")

# PNG magic (\x89PNG\r\n\x1a\n) — what the payload correctly decodes to on 3.10-3.12.
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_EXPECTED_LEN = 373


def _payload() -> str:
    with open(_FIXTURE, "r") as f:
        return f.read().strip()


@pytest.mark.xfail(
    sys.version_info >= (3, 13),
    reason="Python 3.13 binascii strictness rejects non-canonical base64 -> consensus divergence at block 783775 (#871)",
    strict=True,
)
def test_block_783775_stamp_base64_decodes_like_prod():
    """The 783775 stamp payload must decode to a 373-byte PNG (the 3.10-3.12/prod
    behavior). On 3.13 base64.b64decode raises -> strict xfail (see #871)."""
    raw = base64.b64decode(_payload())
    assert raw[:8] == _PNG_MAGIC, "payload should decode to a PNG (consensus behavior on 3.10-3.12)"
    assert len(raw) == _EXPECTED_LEN


def test_supported_interpreters_are_lenient_and_3_13_is_strict():
    """Characterize the divergence directly so it's visible on every version:
    3.10-3.12 decode the payload; 3.13 raises. Passes on ALL versions (asserts the
    version-appropriate behavior) so it documents the split without going red."""
    payload = _payload()
    if sys.version_info < (3, 13):
        raw = base64.b64decode(payload)
        assert raw[:8] == _PNG_MAGIC and len(raw) == _EXPECTED_LEN
    else:
        with pytest.raises(Exception):  # binascii.Error on 3.13
            base64.b64decode(payload)
