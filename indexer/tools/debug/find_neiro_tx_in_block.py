#!/usr/bin/env python3
"""Find multisig burnkey transactions in a specific block and check if they're in our DB."""
import binascii
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

import bitcoin.rpc
import pymysql
from bitcoin.core import lx
from bitcoin.core.script import CScriptOp

import config

BLOCK = int(sys.argv[1]) if len(sys.argv) > 1 else 933197

proxy = bitcoin.rpc.Proxy(service_url="http://rpc:rpc@127.0.0.1:8332", timeout=30)

# Get block transactions
result = subprocess.run(
    ["bitcoin-cli", "-rpcuser=rpc", "-rpcpassword=rpc", "getblockhash", str(BLOCK)],
    capture_output=True,
    text=True,
)
block_hash = result.stdout.strip()
result = subprocess.run(
    ["bitcoin-cli", "-rpcuser=rpc", "-rpcpassword=rpc", "getblock", block_hash],
    capture_output=True,
    text=True,
)
block = json.loads(result.stdout)
txids = block.get("tx", [])

print(f"Block {BLOCK}: {len(txids)} transactions")
print("Scanning for multisig with burnkey...")

conn = pymysql.connect(
    host=os.environ.get("RDS_HOSTNAME"),
    user=os.environ.get("RDS_USER"),
    password=os.environ.get("RDS_PASSWORD"),
    database=os.environ.get("RDS_DATABASE"),
    port=int(os.environ.get("RDS_PORT", "3306")),
)

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4
from cryptography.hazmat.primitives.ciphers import Cipher


def init_arc4(seed):
    return Cipher(ARC4(seed), mode=None, backend=default_backend())


def arc4_decrypt(data, key_cipher):
    decryptor = key_cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()


for txid_str in txids:
    txid = lx(txid_str)
    tx = proxy.getrawtransaction(txid)

    msig_count = 0
    has_burnkey = False
    msig_pubkeys = []
    for idx, vout in enumerate(tx.vout):
        asm = []
        for element in vout.scriptPubKey:
            if isinstance(element, CScriptOp):
                asm.append(str(element))
            else:
                asm.append(element)
        if asm[-1] == "OP_CHECKMULTISIG" and len(asm) == 6 and asm[0] == 1 and asm[4] == 3:
            msig_count += 1
            asm3_hex = binascii.hexlify(asm[3]).decode("utf-8")
            if asm3_hex in config.BURNKEYS:
                has_burnkey = True
                msig_pubkeys.extend(asm[1:3])

    if not (has_burnkey and msig_count > 0):
        continue

    # ARC4 decrypt to check for stamp: prefix
    prev_hash_display = tx.vin[0].prevout.hash[::-1]
    combined_chunk = b"".join(pk[1:-1] for pk in msig_pubkeys)
    key = init_arc4(prev_hash_display)
    decrypted = arc4_decrypt(combined_chunk, key)

    has_stamp = decrypted[2 : 2 + len(config.PREFIX)] == config.PREFIX
    if not has_stamp:
        continue

    # Extract the SRC-20 data
    chunk_length = int(decrypted[:2].hex(), 16)
    actual_data = decrypted[2 + len(config.PREFIX) : 2 + chunk_length]
    try:
        json_str = actual_data.decode("utf-8")
        src20 = json.loads(json_str)
    except Exception:
        json_str = actual_data.hex()
        src20 = {}

    # Check source type
    prev_hash = tx.vin[0].prevout.hash[::-1]
    prev_n = tx.vin[0].prevout.n
    prev_tx = proxy.getrawtransaction(lx(prev_hash.hex()))
    prev_vout = prev_tx.vout[prev_n]
    prev_asm = []
    for element in prev_vout.scriptPubKey:
        if isinstance(element, CScriptOp):
            prev_asm.append(str(element))
        else:
            prev_asm.append(element)
    if isinstance(prev_asm[0], int) and prev_asm[0] == 0 and isinstance(prev_asm[1], bytes):
        if len(prev_asm[1]) == 20:
            src = "P2WPKH"
        elif len(prev_asm[1]) == 32:
            src = "P2WSH"
        else:
            src = "witness_v0"
    elif isinstance(prev_asm[0], int) and prev_asm[0] == 1:
        src = "P2TR"
    else:
        src = "other"

    # Output types
    out_types = []
    for vout in tx.vout:
        asm = []
        for element in vout.scriptPubKey:
            if isinstance(element, CScriptOp):
                asm.append(str(element))
            else:
                asm.append(element)
        if asm[-1] == "OP_CHECKMULTISIG":
            out_types.append("MSIG")
        elif isinstance(asm[0], int) and asm[0] == 1 and len(asm) == 2:
            out_types.append("P2TR")
        elif isinstance(asm[0], int) and asm[0] == 0 and len(asm) == 2:
            if isinstance(asm[1], bytes) and len(asm[1]) == 20:
                out_types.append("P2WPKH")
            elif isinstance(asm[1], bytes) and len(asm[1]) == 32:
                out_types.append("P2WSH")
        else:
            out_types.append("OTHER")

    # Check if in DB
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM SRC20Valid WHERE tx_hash = %s", (txid_str,))
    in_src20 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM StampTableV4 WHERE tx_hash = %s", (txid_str,))
    in_stamps = cur.fetchone()[0]
    cur.close()

    # Check output 2 encryption
    out2_nonzero = 0
    if msig_count >= 2 and len(msig_pubkeys) >= 4:
        out2_raw = b"".join(pk[1:-1] for pk in msig_pubkeys[2:4])
        out2_nonzero = sum(1 for b in out2_raw if b != 0)

    print(f"\n  FOUND SRC-20 MULTISIG: {txid_str}")
    print(f"    Block: {BLOCK}, Source: {src}, Outputs: {out_types}")
    print(f"    Multisig outputs: {msig_count}, Total pubkeys: {len(msig_pubkeys)}")
    print(f"    SRC-20 data: {json_str}")
    print(f"    In SRC20Valid: {in_src20}, In StampTableV4: {in_stamps}")
    if msig_count >= 2:
        print(f"    Output 2 non-zero ciphertext bytes: {out2_nonzero}/62")
        if out2_nonzero < 10:
            print(f"    *** NON-STANDARD ENCRYPTION (output 2 is raw zeros) ***")
        else:
            print(f"    Standard encryption (output 2 fully encrypted)")

conn.close()
