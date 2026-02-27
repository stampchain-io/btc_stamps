#!/usr/bin/env python3
"""
Find ANY transaction in a block that contains SRC-20 data in any encoding:
- Bare multisig (1-of-3 with burnkey, ARC4 encrypted stamp: prefix)
- OLGA/P2WSH (P2WSH outputs with stamp: prefix in combined data)
- Any multisig format (1-of-2, 1-of-3, etc.)
Also search by specific address spending.
"""

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
SEARCH_ADDR = sys.argv[2] if len(sys.argv) > 2 else None

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4
from cryptography.hazmat.primitives.ciphers import Cipher


def init_arc4(seed):
    return Cipher(ARC4(seed), mode=None, backend=default_backend())


def arc4_decrypt(data, key_cipher):
    decryptor = key_cipher.decryptor()
    return decryptor.update(data) + decryptor.finalize()


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
block_data = json.loads(result.stdout)
txids = block_data.get("tx", [])

print(f"Block {BLOCK}: {len(txids)} transactions")
if SEARCH_ADDR:
    print(f"Searching for transactions spending from: {SEARCH_ADDR}")
print()

conn = pymysql.connect(
    host=os.environ.get("RDS_HOSTNAME"),
    user=os.environ.get("RDS_USER"),
    password=os.environ.get("RDS_PASSWORD"),
    database=os.environ.get("RDS_DATABASE"),
    port=int(os.environ.get("RDS_PORT", "3306")),
)

found_any_multisig = 0
found_stamp = 0

for txid_str in txids:
    txid = lx(txid_str)
    tx = proxy.getrawtransaction(txid)

    # Check if any input spends from the search address
    if SEARCH_ADDR:
        match = False
        for vin in tx.vin:
            prev_hash = vin.prevout.hash[::-1]
            prev_n = vin.prevout.n
            try:
                prev_tx = proxy.getrawtransaction(lx(prev_hash.hex()))
                prev_vout = prev_tx.vout[prev_n]
                # Decode address
                from index_core import util

                addr = util.decode_address(prev_vout.scriptPubKey)
                if str(addr) == SEARCH_ADDR:
                    match = True
                    break
            except Exception:
                pass
        if not match:
            continue
        print(f"  TX from {SEARCH_ADDR}: {txid_str}")

    # Scan outputs for any multisig or P2WSH
    has_multisig = False
    has_p2wsh_data = False
    out_types = []
    all_multisig_pubkeys = []

    for idx, vout in enumerate(tx.vout):
        asm = []
        for element in vout.scriptPubKey:
            if isinstance(element, CScriptOp):
                asm.append(str(element))
            else:
                asm.append(element)

        if not asm:
            out_types.append("EMPTY")
            continue

        if asm[-1] == "OP_CHECKMULTISIG":
            has_multisig = True
            found_any_multisig += 1
            if SEARCH_ADDR:
                # Print multisig details
                asm3_hex = binascii.hexlify(asm[3]).decode("utf-8") if len(asm) >= 4 and isinstance(asm[3], bytes) else "?"
                burn = asm3_hex in config.BURNKEYS if asm3_hex != "?" else False
                print(f"    vout[{idx}]: MULTISIG (len={len(asm)}, m={asm[0]}, n={asm[-2]}) burn={burn}")
                if len(asm) == 6:
                    all_multisig_pubkeys.extend(asm[1:3])
            out_types.append("MSIG")
        elif isinstance(asm[0], int) and asm[0] == 0 and len(asm) == 2 and isinstance(asm[1], bytes):
            if len(asm[1]) == 32:
                out_types.append("P2WSH")
                if idx > 0 and BLOCK >= config.BTC_SRC20_OLGA_BLOCK:
                    has_p2wsh_data = True
                    if SEARCH_ADDR:
                        print(f"    vout[{idx}]: P2WSH data: {asm[1].hex()[:40]}...")
            elif len(asm[1]) == 20:
                out_types.append("P2WPKH")
        elif isinstance(asm[0], int) and asm[0] == 1 and len(asm) == 2:
            out_types.append("P2TR")
        elif asm[0] == "OP_RETURN":
            out_types.append("OP_RET")
        else:
            out_types.append("OTHER")

    if SEARCH_ADDR:
        print(f"    Outputs: {out_types}")
        if all_multisig_pubkeys:
            # Try to decrypt
            combined = b"".join(pk[1:-1] for pk in all_multisig_pubkeys)
            prev_hash_display = tx.vin[0].prevout.hash[::-1]
            key = init_arc4(prev_hash_display)
            decrypted = arc4_decrypt(combined, key)
            has_prefix = decrypted[2 : 2 + len(config.PREFIX)] == config.PREFIX
            print(f"    ARC4 decrypt stamp: prefix: {has_prefix}")
            if has_prefix:
                cl = int(decrypted[:2].hex(), 16)
                data = decrypted[2 + len(config.PREFIX) : 2 + cl]
                print(f"    Data: {data}")

        # Check DB
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM SRC20Valid WHERE tx_hash = %s", (txid_str,))
        in_src20 = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM StampTableV4 WHERE tx_hash = %s", (txid_str,))
        in_stamps = cur.fetchone()[0]
        cur.close()
        print(f"    In DB: SRC20Valid={in_src20}, StampTableV4={in_stamps}")
        print()

if not SEARCH_ADDR:
    print(f"Total transactions with any multisig output: {found_any_multisig}")

conn.close()
