#!/usr/bin/env python3
"""
Scan for transactions affected by issue #749: a valid bare-multisig SRC-20 stamp
whose data is silently dropped because the tx also has a P2WSH output (idx>0)
that shadows the multisig branch in get_tx_info().

Strategy (see issue #749 analysis):
  1. Every affected tx MUST carry a keyburn pubkey (valid multisig SRC-20 needs
     keyburn==1). Burnkeys are fixed 33-byte constants, so we byte-search each
     raw block's hex for them instead of deserializing every tx.
  2. For burnkey-hit blocks we deserialize and, per tx, mirror get_tx_info()'s
     exact SRC-20 branch logic (reusing index_core.script / index_core.arc4 /
     config so we don't diverge from consensus).
  3. affected = (P2WSH chunk present) AND (P2WSH path yields NO stamp data)
               AND (multisig path WOULD yield valid stamp data).
     These are exactly the txs get_tx_info drops via its `elif` short-circuit.
  4. Cross-check: affected txids must be ABSENT from the `transactions` table.

Usage:
  poetry run python tools/debug/scan_issue749.py --start 865000 --end 870000 [--workers 1]
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, "src")
import config  # noqa: E402
import index_core.arc4 as arc4  # noqa: E402
import index_core.script as script  # noqa: E402
from bitcoin.core import CBlock  # noqa: E402

RPC_URL = os.environ.get("RPC_URL", f"http://{os.environ.get('RPC_IP', '127.0.0.1')}:{os.environ.get('RPC_PORT', '8332')}")
RPC_AUTH = base64.b64encode(f"{os.environ.get('RPC_USER', 'rpc')}:{os.environ.get('RPC_PASSWORD', 'rpc')}".encode()).decode()
PREFIX = config.PREFIX
OLGA = config.BTC_SRC20_OLGA_BLOCK
BURNKEYS = [bytes.fromhex(b) for b in config.BURNKEYS]


def rpc(method, params):
    body = json.dumps({"jsonrpc": "1.0", "id": "s", "method": method, "params": params}).encode()
    req = urllib.request.Request(
        RPC_URL, data=body, headers={"Authorization": "Basic " + RPC_AUTH, "Content-Type": "text/plain"}
    )
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=120))["result"]
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(0.5 * (attempt + 1))


def multisig_yields_data(ctx, pubkeys_compiled):
    """Mirror decode_checkmultisig() data-extraction: RC4 + PREFIX + length check."""
    if not pubkeys_compiled:
        return None
    chunk = b"".join(pubkey[1:-1] for pubkey in pubkeys_compiled)
    key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
    chunk = arc4.arc4_decrypt_chunk(chunk, key)
    if chunk[2 : 2 + len(PREFIX)] == PREFIX:
        n = int(chunk[:2].hex(), 16)
        if len(chunk) < 2 + n:
            return None  # DecodeError("invalid data length")
        data = chunk[2 + len(PREFIX) : 2 + n]
        return data or None
    return None


def p2wsh_yields_data(p2wsh_data_chunks):
    """Mirror get_tx_info() P2WSH SRC-20 path: returns extracted data or None."""
    if not p2wsh_data_chunks:
        return None
    p2wsh = b"".join(p2wsh_data_chunks).rstrip(b"\x00")
    if p2wsh and len(p2wsh) >= 2 + len(PREFIX):
        n = int.from_bytes(p2wsh[:2], byteorder="big")
        if len(p2wsh) >= 2 + n:
            data_chunk = p2wsh[2 : 2 + n]
            if data_chunk.startswith(PREFIX):
                return data_chunk[len(PREFIX) :] or None
    return None


def classify_tx(ctx, block_index):
    """Return (affected: bool, decoded_multisig_data_or_None, has_p2wsh_chunk: bool)."""
    pubkeys_compiled = []
    p2wsh_data_chunks = []
    keyburn = None
    for idx, vout in enumerate(ctx.vout):
        try:
            asm = script.get_asm(vout.scriptPubKey)
        except Exception:
            continue
        if not asm:
            continue
        if asm[-1] == "OP_CHECKMULTISIG":
            try:
                pubkeys, _req, kb = script.get_checkmultisig(asm)
            except Exception:
                continue
            if kb is not None:
                keyburn = kb
            pubkeys_compiled += list(pubkeys)
        elif asm[0] == "OP_RETURN":
            pass
        elif asm[0] == 0 and len(asm[1]) == 32:
            if block_index >= OLGA and idx > 0:
                p2wsh_data_chunks.append(asm[1])

    ms_data = multisig_yields_data(ctx, pubkeys_compiled)
    p2_data = p2wsh_yields_data(p2wsh_data_chunks)
    # Affected: get_tx_info enters the `if p2wsh_data_chunks` branch (because chunks
    # exist), it produces no data, and the `elif` multisig branch (which WOULD have
    # produced data) is never reached.
    affected = bool(p2wsh_data_chunks) and p2_data is None and ms_data is not None and keyburn == 1
    return affected, ms_data, bool(p2wsh_data_chunks), (ms_data is not None and keyburn == 1)


def scan_block(height):
    bh = rpc("getblockhash", [height])
    raw = rpc("getblock", [bh, 0])
    rawb = bytes.fromhex(raw)
    if not any(bk in rawb for bk in BURNKEYS):
        return height, [], 0  # no burnkey -> no multisig stamp -> not affected
    block = CBlock.deserialize(rawb)
    affected = []
    clean_ms = 0
    for tx in block.vtx:
        try:
            is_aff, ms_data, has_p2wsh, valid_ms = classify_tx(tx, height)
        except Exception:
            continue
        if valid_ms and not has_p2wsh:
            clean_ms += 1  # ordinary multisig stamp, should be in transactions table
        if is_aff:
            txid = tx.GetTxid()[::-1].hex()
            try:
                payload = ms_data.decode("utf-8", "replace")
            except Exception:
                payload = ms_data.hex()
            affected.append({"txid": txid, "block": height, "data": payload})
    return height, affected, clean_ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default="/tmp/issue749_affected.json")
    args = ap.parse_args()

    heights = list(range(args.start, args.end + 1))
    t0 = time.time()
    affected_all = []
    clean_total = 0
    burnkey_blocks = 0
    done = 0

    def emit_progress():
        el = time.time() - t0
        rate = done / el if el else 0
        eta = (len(heights) - done) / rate / 60 if rate else 0
        print(
            f"  [{done}/{len(heights)}] {el:.0f}s  {rate:.1f} blk/s  ETA {eta:.1f}m  "
            f"affected={len(affected_all)} burnkey_blks={burnkey_blocks} clean_ms={clean_total}",
            flush=True,
        )

    if args.workers <= 1:
        for h in heights:
            _, aff, clean = scan_block(h)
            if aff:
                burnkey_blocks += 1  # at least had a burnkey + candidate; recount below
            affected_all += aff
            clean_total += clean
            done += 1
            if done % 250 == 0:
                emit_progress()
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(scan_block, h): h for h in heights}
            for fut in as_completed(futs):
                _, aff, clean = fut.result()
                affected_all += aff
                clean_total += clean
                done += 1
                if done % 250 == 0:
                    emit_progress()

    el = time.time() - t0
    print(f"\nDONE {args.start}-{args.end}: {len(heights)} blocks in {el:.0f}s ({len(heights)/el:.1f} blk/s)")
    print(f"affected(pre-DB-check)={len(affected_all)}  clean_multisig_stamps={clean_total}")
    with open(args.out, "w") as f:
        json.dump(affected_all, f, indent=2)
    print(f"wrote {args.out}")
    for a in affected_all[:25]:
        print("  AFFECTED", a["txid"], a["block"], a["data"][:90])


if __name__ == "__main__":
    main()
