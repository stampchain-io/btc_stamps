"""decode_address must only accept scriptPubKeys whose shape matches the address
type it reports. Taproot is the hand-rolled branch (python-bitcoinlib 0.12 does
not know witness v1), so its shape check lives in util.py and is pinned here."""

import pytest
from bitcoin.core import CScript

from index_core import util
from index_core.util import decode_address

KEY = bytes.fromhex("9469817f81859de6701b423fcc7b33d811aa14d09c456c4db7c1643e9225d3ff")
P2TR_ADDRESS = "bc1pj35czlupskw7vuqmggluc7enmqg659xsn3zkcndhc9jray3960lsqfq6f7"


@pytest.fixture(autouse=True)
def _mainnet_and_clear_cache(monkeypatch):
    monkeypatch.setattr(util.config, "TESTNET", False, raising=False)
    try:
        util.cache_manager.clear_cache("address")
    except Exception:
        pass
    yield


def test_p2tr_exact_shape_decodes():
    assert decode_address(CScript(b"\x51\x20" + KEY)) == P2TR_ADDRESS


def test_p2tr_shape_is_op1_then_single_32_byte_push():
    # Same 32 bytes, but byte 1 is not a 32-byte push: these are not witness
    # programs (legacy script rules apply) and must never decode to the key's
    # Taproot address, whatever Bitcoin does with them.
    for length_byte in (0x1F, 0x12, 0x06, 0x00, 0x21, 0x51):
        script = CScript(bytes([0x51, length_byte]) + KEY)
        with pytest.raises(ValueError, match="Unsupported scriptPubKey format"):
            decode_address(script)


def test_p2tr_wrong_total_length_rejected():
    with pytest.raises(ValueError):
        decode_address(CScript(b"\x51\x20" + KEY[:31]))
    with pytest.raises(ValueError):
        decode_address(CScript(b"\x51\x20" + KEY + b"\x00"))


def test_rejected_script_is_not_cached_as_an_address():
    script = CScript(b"\x51\x1f" + KEY)
    with pytest.raises(ValueError):
        decode_address(script)
    assert util.cache_manager.get_cache_value("address", bytes(script)) is None


def test_other_script_types_still_decode():
    # P2WPKH (OP_0 <20>) and P2PKH go through python-bitcoinlib unchanged.
    p2wpkh = CScript(bytes.fromhex("0014" + "00" * 20))
    assert decode_address(p2wpkh).startswith("bc1q")
    p2pkh = CScript(bytes.fromhex("76a914" + "00" * 20 + "88ac"))
    assert decode_address(p2pkh).startswith("1")
