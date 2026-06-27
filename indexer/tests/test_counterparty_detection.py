"""Unit tests for the over-approximating Counterparty (CNTRPRTY) detector (issue #754).

The Rust parser exposes ``TransactionInfo.has_counterparty_data`` — a strict
OVER-approximation of "does this tx carry Counterparty data?". It must NEVER
miss a real CP tx (a false negative would cause permanent consensus divergence
once #756 consumes this signal to skip the CP API for CP-free blocks).

These tests assert:
  * known CP-era multisig stamp txs (classic CNTRPRTY issuances) are flagged True,
  * native ``stamp:`` keyburn / P2WSH-OLGA stamps (NOT CP txs) are flagged False,
  * the plaintext OP_RETURN ``CNTRPRTY`` reveal marker is flagged True,
  * a coinbase / no-key tx does NOT panic and is False,
  * a mundane P2PKH-only tx is False.

DB-free and network-free: only the built ``btc_stamps_parser`` extension and the
committed transaction-cache fixtures are required.
"""

import json
import os

import pytest

FastTransactionParser = pytest.importorskip("btc_stamps_parser").FastTransactionParser

_TRANSACTION_CACHE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "transaction_cache")

# Classic CP-era stamps: the stamp image is a Counterparty asset issuance, so the
# tx genuinely embeds a CNTRPRTY message (decrypts to "CNTRPRTY" at offset 1 of
# the bare-multisig payload). These MUST be detected.
CNTRPRTY_TXIDS = [
    "0321905ca9053a5b8313be9524a2af146196982a479573e9a324e8b929231730",  # 789352
    "2cc3be498d12247c47fc99b60d97c6db7b2f1dfdcaefc3fee3a36729fade6b19",  # 790383
    "3809059d32b51e3c2e680c6ffbd8e15e152daa06554f62fc1b9f2aea3be39e32",  # 792483
    "56bba57e6405e553cfff1b78ab8f7f0f0f419c5056c06b72a81e0e5deae48d15",  # 790606
    "72f9bfb6c6553feabdb7b52428a33172090553fd9441209fb99d4b13455ca71d",  # 790918
]

# Native stamps that do NOT use Counterparty: keyburn-multisig and P2WSH-OLGA
# stamps whose payload decrypts to "stamp:" (not "CNTRPRTY"). These are parsed
# directly from Bitcoin (never via the CP API), so they must NOT be flagged.
NON_CNTRPRTY_TXIDS = [
    "049d1544e94c14deece7a468855ca9bff7c867476b3f4cba8c075000ed93babe",  # 797973 keyburn SRC-20
    "4d89d7f69ee77c3ddda041f94270b4112d002fc67b88008f29710fadfb486da8",  # 853693 keyburn
    "306cf746bbcc063825c95e5cdd47464ede62d4aa6e3d6629e80cd8affb7e71bf",  # 877807 P2WSH OLGA
]


def _load_tx_hex(txid: str) -> str:
    path = os.path.join(_TRANSACTION_CACHE_DIR, f"{txid}.json")
    with open(path) as fh:
        data = json.load(fh)
    tx_hex = data.get("hex")
    assert tx_hex, f"fixture {txid} has no hex"
    return tx_hex


@pytest.mark.parametrize("txid", CNTRPRTY_TXIDS)
def test_cp_era_stamps_are_detected(txid):
    """Classic CP-era multisig stamps are genuine CNTRPRTY txs -> True."""
    parser = FastTransactionParser()
    info = parser.deserialize_transaction(_load_tx_hex(txid))
    assert info.has_counterparty_data is True


@pytest.mark.parametrize("txid", NON_CNTRPRTY_TXIDS)
def test_native_stamps_are_not_flagged(txid):
    """Native stamp:/OLGA stamps are not Counterparty txs -> False (no false positive)."""
    parser = FastTransactionParser()
    info = parser.deserialize_transaction(_load_tx_hex(txid))
    assert info.has_counterparty_data is False


def test_op_return_plaintext_marker_is_detected():
    """A tx with a plaintext OP_RETURN ``CNTRPRTY`` reveal marker is flagged True.

    Crafted tx: 1 normal input (non-coinbase, so a key is derived) + a single
    ``OP_RETURN <push8 "CNTRPRTY">`` output. The plaintext check matches
    regardless of the RC4 key.
    """
    tx_hex = (
        "01000000"  # version
        "01" + "11" * 32 + "00000000"  # 1 input  # prevout txid (non-null)  # prevout vout
        "00"  # empty scriptSig
        "ffffffff"  # sequence
        "01"  # 1 output
        "0000000000000000"  # value 0
        "0a"  # scriptPubKey length (10)
        "6a08434e545250525459"  # OP_RETURN PUSH8 "CNTRPRTY"
        "00000000"  # locktime
    )
    parser = FastTransactionParser()
    info = parser.deserialize_transaction(tx_hex)
    assert info.has_counterparty_data is True


def test_coinbase_does_not_panic_and_is_false():
    """A coinbase tx has no first-input prevout key (RC4 would panic) -> skipped, False."""
    tx_hex = (
        "01000000"  # version
        "01" + "00" * 32 + "ffffffff"  # 1 input  # null prevout txid (coinbase)  # prevout vout 0xffffffff (coinbase)
        "0100"  # scriptSig: len 1, byte 0x00
        "ffffffff"  # sequence
        "01"  # 1 output
        "0000000000000000"  # value 0
        "00"  # empty scriptPubKey
        "00000000"  # locktime
    )
    parser = FastTransactionParser()
    info = parser.deserialize_transaction(tx_hex)
    assert info.has_counterparty_data is False


def test_plain_p2pkh_tx_is_not_flagged():
    """A mundane P2PKH-only tx (exercises the OP_CHECKSIG path) is not CP -> False."""
    tx_hex = (
        "01000000"  # version
        "01" + "22" * 32 + "00000000"  # 1 input  # prevout txid  # prevout vout
        "00"  # empty scriptSig
        "ffffffff"  # sequence
        "01"  # 1 output
        "8038010000000000"  # value
        "19"  # scriptPubKey length (25)
        "76a914" + "33" * 20 + "88ac"  # OP_DUP OP_HASH160 <20> OP_EQUALVERIFY OP_CHECKSIG
        "00000000"  # locktime
    )
    parser = FastTransactionParser()
    info = parser.deserialize_transaction(tx_hex)
    assert info.has_counterparty_data is False
