#!/usr/bin/env python3
"""
Diagnose why transaction daaf764d8caa1108f4c77fae8318b0bed5ab49ba857ad1a468a205bbcd53a412
passes the Rust parser but fails in the Python pipeline.

Theory: The Python code combines pubkeys from ALL multisig outputs into one chunk,
but decode_checkmultisig() length validation fails because the second output's
ARC4-decrypted padding is not null bytes.
"""
import binascii
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4
from cryptography.hazmat.primitives.ciphers import Cipher

import config


def init_arc4(seed):
    if isinstance(seed, str):
        seed = binascii.unhexlify(seed)
    backend = default_backend()
    cipher = Cipher(ARC4(seed), mode=None, backend=backend)
    return cipher


def arc4_decrypt(data, key_cipher):
    decryptor = key_cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()


# Transaction: daaf764d8caa1108f4c77fae8318b0bed5ab49ba857ad1a468a205bbcd53a412
# Raw hex obtained from previous investigation
TX_HEX = None  # We'll fetch from bitcoind

# From the decode_missing_tx.py output, we know:
# - vin[0] spends txid: (the prev txid used as ARC4 key)
# - vout[1]: 1-of-3 multisig with burnkey 020202...02 (data carrier)
# - vout[2]: 1-of-3 multisig with burnkey 020202...02 (padding)

# Let's simulate the Python processing path using the bitcoin RPC


def fetch_and_analyze():
    """Fetch the transaction and trace through the Python pipeline."""
    import bitcoin.rpc

    proxy = bitcoin.rpc.Proxy(
        service_url="http://rpc:rpc@127.0.0.1:8332",
        timeout=30,
    )

    txid_str = "daaf764d8caa1108f4c77fae8318b0bed5ab49ba857ad1a468a205bbcd53a412"
    from bitcoin.core import lx

    txid = lx(txid_str)
    tx = proxy.getrawtransaction(txid)

    print(f"Transaction: {txid}")
    print(f"Inputs: {len(tx.vin)}")
    print(f"Outputs: {len(tx.vout)}")

    # Get the ARC4 key (prev txid in display order = reversed internal order)
    prev_hash_internal = tx.vin[0].prevout.hash
    prev_hash_display = prev_hash_internal[::-1]
    print(f"\nARC4 key (prev txid display order): {prev_hash_display.hex()}")

    # Process each output
    from bitcoin.core.script import CScriptOp

    all_pubkeys = []
    multisig_outputs = []

    for idx, vout in enumerate(tx.vout):
        asm = []
        for element in vout.scriptPubKey:
            if isinstance(element, CScriptOp):
                asm.append(str(element))
            else:
                asm.append(element)

        print(f"\nvout[{idx}]: nValue={vout.nValue}")
        print(f"  asm[0]={type(asm[0]).__name__}:{asm[0] if isinstance(asm[0], (int, str)) else asm[0].hex()[:20]}")
        print(f"  asm[-1]={asm[-1]}")
        print(f"  len(asm)={len(asm)}")

        if asm[-1] == "OP_CHECKMULTISIG":
            # Check multisig format
            if len(asm) == 6 and asm[0] == 1 and asm[4] == 3:
                asm3_hex = binascii.hexlify(asm[3]).decode("utf-8")
                is_burnkey = asm3_hex in config.BURNKEYS
                pubkeys = asm[1:3]
                print(f"  => 1-of-3 multisig, burnkey={is_burnkey} ({asm3_hex[:20]}...)")
                print(f"  => pubkey1 ({len(asm[1])} bytes): {asm[1].hex()[:40]}...")
                print(f"  => pubkey2 ({len(asm[2])} bytes): {asm[2].hex()[:40]}...")

                # Extract data bytes (strip first and last byte from each pubkey)
                for pk in pubkeys:
                    data_bytes = pk[1:-1]
                    all_pubkeys.append(pk)
                    print(f"     data ({len(data_bytes)} bytes): {data_bytes.hex()[:40]}...")

                multisig_outputs.append(idx)
            else:
                print(f"  => Non-standard multisig format")

    print(f"\n{'='*80}")
    print(f"ANALYSIS: Found {len(multisig_outputs)} multisig outputs, {len(all_pubkeys)} pubkeys total")

    # ===== Simulate RUST parser (per-output) =====
    print(f"\n{'='*80}")
    print("RUST PARSER SIMULATION (per-output decryption):")
    for msig_idx in multisig_outputs:
        vout = tx.vout[msig_idx]
        asm = []
        for element in vout.scriptPubKey:
            if isinstance(element, CScriptOp):
                asm.append(str(element))
            else:
                asm.append(element)

        pubkeys = asm[1:3]
        chunk = b"".join(pk[1:-1] for pk in pubkeys)
        print(f"\n  Output {msig_idx}: chunk size = {len(chunk)} bytes")

        key = init_arc4(prev_hash_display)
        decrypted = arc4_decrypt(chunk, key)
        print(f"  Decrypted first 20 bytes: {decrypted[:20]}")
        print(f"  Decrypted hex: {decrypted[:20].hex()}")

        prefix_pos = 2
        prefix = config.PREFIX  # b"stamp:"
        if len(decrypted) >= prefix_pos + len(prefix):
            found_prefix = decrypted[prefix_pos : prefix_pos + len(prefix)]
            print(f"  Bytes at position 2: {found_prefix}")
            print(f"  Has stamp: prefix: {found_prefix == prefix}")
        else:
            print(f"  Too short for prefix check")

    # ===== Simulate PYTHON pipeline (combined decryption) =====
    print(f"\n{'='*80}")
    print("PYTHON PIPELINE SIMULATION (combined decryption):")

    # Combine ALL pubkeys from ALL multisig outputs
    combined_chunk = b"".join(pk[1:-1] for pk in all_pubkeys)
    print(f"  Combined chunk size: {len(combined_chunk)} bytes")
    print(f"  (vs single output: {len(all_pubkeys[0][1:-1]) + len(all_pubkeys[1][1:-1])} bytes)")

    key = init_arc4(prev_hash_display)
    decrypted = arc4_decrypt(combined_chunk, key)

    print(f"\n  Decrypted first 20 bytes: {decrypted[:20]}")
    print(f"  Has stamp: prefix at pos 2: {decrypted[2:2+len(config.PREFIX)] == config.PREFIX}")

    # Length validation (exactly as in decode_checkmultisig)
    chunk_length_hex = decrypted[:2].hex()
    chunk_length = int(chunk_length_hex, 16)
    print(f"\n  Length prefix (2 bytes): {chunk_length_hex} = {chunk_length}")

    data_after_prefix = decrypted[len(config.PREFIX) + 2 :]
    data_stripped = data_after_prefix.rstrip(b"\x00")
    print(f"  data after stamp: prefix: {len(data_after_prefix)} bytes")
    print(f"  data after rstrip(null): {len(data_stripped)} bytes")

    all_after_length = decrypted[2:]
    all_stripped = all_after_length.rstrip(b"\x00")
    data_length = len(all_stripped)
    print(f"\n  data_length (chunk[2:].rstrip(null)): {data_length}")
    print(f"  chunk_length from prefix: {chunk_length}")
    print(f"  MATCH: {data_length == chunk_length}")

    if data_length != chunk_length:
        print(f"\n  *** DECODE ERROR: invalid data length ***")
        print(f"  This is exactly what happens in decode_checkmultisig()!")
        print(f"  The combined data from output 2 adds {data_length - chunk_length} extra bytes")

        # Show what the second output's data looks like after decryption
        single_output_size = len(all_pubkeys[0][1:-1]) + len(all_pubkeys[1][1:-1])
        print(f"\n  Bytes from output 1 (actual data): {single_output_size}")
        print(f"  Bytes from output 2 (padding):      {len(combined_chunk) - single_output_size}")
        print(f"  Output 2 decrypted (should be zeros if no bug): {decrypted[single_output_size:single_output_size+20].hex()}")
        print(f"  Output 2 decrypted IS all zeros: {all(b == 0 for b in decrypted[single_output_size:])}")

    # ===== Show the fix: use chunk_length to bound data extraction =====
    print(f"\n{'='*80}")
    print("WITH FIX (bound by length prefix):")
    actual_data = decrypted[2 + len(config.PREFIX) : 2 + chunk_length]
    print(f"  Extracted data ({len(actual_data)} bytes): {actual_data}")
    try:
        print(f"  Decoded: {actual_data.decode('utf-8')}")
    except Exception:
        print(f"  (not valid UTF-8)")


if __name__ == "__main__":
    fetch_and_analyze()
