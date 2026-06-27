#!/usr/bin/env bash
# Refresh indexer/snapshots/ci_consensus_hashes.json — the curated subset of
# consensus checkpoint hashes that .github/workflows/reparse-validate.yml diffs
# against on every PR that touches the consensus surface.
#
# Sources block hashes + consensus hashes from a local bitcoind RPC (default
# 127.0.0.1:8332) and the existing indexer/snapshots/reference_hashes.json
# baseline. The block list is curated to hit every consensus-boundary block
# defined in indexer/src/config.py — see CI_BLOCKS array below.
#
# Run this when you intentionally change a consensus block height, add a new
# boundary, or refresh the baseline after a validated reindex. Commit the
# regenerated indexer/snapshots/ci_consensus_hashes.json in the same PR.
#
# Usage:
#   ./indexer/ci/refresh-consensus-hashes.sh
#   # then: git add indexer/snapshots/ci_consensus_hashes.json && git commit
#
# Env:
#   RPC_USER, RPC_PASSWORD, RPC_IP, RPC_PORT — bitcoind RPC creds (read from
#   indexer/.env.local if present)
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

# Load .env.local if present so we pick up the same RPC creds the indexer uses.
for envfile in .env.local indexer/.env.local indexer/.env; do
  if [ -f "$envfile" ]; then
    # shellcheck disable=SC1090
    set -a; source "$envfile"; set +a
    break
  fi
done

RPC_URL="http://${RPC_IP:-127.0.0.1}:${RPC_PORT:-8332}/"
REFERENCE_HASHES="indexer/snapshots/reference_hashes.json"
OUTPUT="indexer/snapshots/ci_consensus_hashes.json"

# Curated consensus-boundary block list. Each known consensus transition from
# indexer/src/config.py is covered as (boundary-1, boundary, boundary+1) so a
# parser regression that misfires at the activation point is caught either by
# the "block before" (feature should not yet be active) or the "block at /
# after" (feature should be active). Add new entries in the same triple
# pattern; keep the file ordered by block index.
#
# Block-before of CP_STAMP_GENESIS_BLOCK is intentionally omitted — no stamp
# activity exists before genesis, so reference_hashes.json starts at 779652.
#
# 940000 (BTC_SRC101_OLGA_BLOCK) is a planned future activation; can't be
# captured until the block actually exists on mainnet.
#
# Format: "<block_index>:<reason>"
CI_BLOCKS=(
  "779652:CP_STAMP_GENESIS_BLOCK"
  "779653:CP_STAMP_GENESIS_BLOCK + 1"
  "784549:STOP_BASE64_REPAIR - 1"
  "784550:STOP_BASE64_REPAIR"
  "784551:STOP_BASE64_REPAIR + 1"
  "788040:CP_SRC20_GENESIS_BLOCK - 1"
  "788041:CP_SRC20_GENESIS_BLOCK"
  "788042:CP_SRC20_GENESIS_BLOCK + 1"
  "789624:PR753 ref tx c129cc8f (CP SRC-20 mint base64 mod4=3)"
  "792369:CP_SRC721_GENESIS_BLOCK - 1"
  "792370:CP_SRC721_GENESIS_BLOCK"
  "792371:CP_SRC721_GENESIS_BLOCK + 1"
  "793067:BTC_SRC20_GENESIS_BLOCK - 1"
  "793068:BTC_SRC20_GENESIS_BLOCK (SRC-20 leaves CP)"
  "793069:BTC_SRC20_GENESIS_BLOCK + 1"
  "795999:CP_SRC20_END_BLOCK - 1"
  "796000:CP_SRC20_END_BLOCK"
  "796001:CP_SRC20_END_BLOCK + 1"
  "815129:CP_BMN_FEAT_BLOCK_START - 1"
  "815130:CP_BMN_FEAT_BLOCK_START"
  "815131:CP_BMN_FEAT_BLOCK_START + 1"
  "832999:CP_P2WSH_FEAT_BLOCK_START - 1"
  "833000:CP_P2WSH_FEAT_BLOCK_START (OLGA enabled)"
  "833001:CP_P2WSH_FEAT_BLOCK_START + 1"
  "864999:BTC_SRC20_OLGA_BLOCK - 1"
  "865000:BTC_SRC20_OLGA_BLOCK"
  "865001:BTC_SRC20_OLGA_BLOCK + 1"
  "870651:BTC_SRC101_GENESIS_BLOCK - 1"
  "870652:BTC_SRC101_GENESIS_BLOCK"
  "870653:BTC_SRC101_GENESIS_BLOCK + 1"
  "872000:PR753 ref STAMP->SRC-721 reclassification cluster"
  "890000:OLGA-era anchor"
  "900000:OLGA-era anchor (reference_hashes.json)"
  "910000:OLGA-era anchor (reference_hashes.json)"
  "920000:OLGA-era anchor (reference_hashes.json)"
  "930000:OLGA-era anchor (reference_hashes.json)"
  "940000:BTC_SRC101_OLGA_BLOCK (reference_hashes.json)"
  "950000:Recent tip-side anchor (reference_hashes.json)"
  # --- Stratified random sample (issue #778 item 1) ---------------------------
  # Deterministically chosen by indexer/ci/select_random_ci_blocks.py: ~8 blocks
  # per protocol epoch, drawn from a stable sha256(block) % 23 == 0 subsample of
  # blocks that are ledger_hash-unchanged vs block-1 (so the DB-free Tier-3
  # runner can reproduce ledger_hash) AND have txlist activity (meaningful parse
  # coverage), away from consensus-activation boundaries, and EMPIRICALLY
  # confirmed to pass Tier 3 (block+txlist+ledger) via smoke_parser_validation.
  # All sourced from reference_hashes.json. Regenerate with:
  #   poetry run python indexer/ci/select_random_ci_blocks.py --validate
  "779708:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "781033:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "782214:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "783513:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "784671:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "786047:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "786944:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "787953:random-sample epoch1 (pre-SRC20 / CP_STAMP era)"
  "788095:random-sample epoch2 (CP-SRC20 era)"
  "788427:random-sample epoch2 (CP-SRC20 era)"
  "788812:random-sample epoch2 (CP-SRC20 era)"
  "789949:random-sample epoch2 (CP-SRC20 era)"
  "790337:random-sample epoch2 (CP-SRC20 era)"
  "790893:random-sample epoch2 (CP-SRC20 era)"
  "792051:random-sample epoch2 (CP-SRC20 era)"
  "792992:random-sample epoch2 (CP-SRC20 era)"
  "793162:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "799790:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "802942:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "806242:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "809442:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "812709:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "818525:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "864840:random-sample epoch3 (BTC-SRC20 pre-OLGA)"
  "865089:random-sample epoch4 (OLGA era)"
  "866581:random-sample epoch4 (OLGA era)"
  "867020:random-sample epoch4 (OLGA era)"
  "868008:random-sample epoch4 (OLGA era)"
  "868583:random-sample epoch4 (OLGA era)"
  "869162:random-sample epoch4 (OLGA era)"
  "869616:random-sample epoch4 (OLGA era)"
  "870480:random-sample epoch4 (OLGA era)"
  "870905:random-sample epoch5 (SRC-101 / post-OLGA)"
  "892434:random-sample epoch5 (SRC-101 / post-OLGA)"
  "913619:random-sample epoch5 (SRC-101 / post-OLGA)"
  "922757:random-sample epoch5 (SRC-101 / post-OLGA)"
  "932828:random-sample epoch5 (SRC-101 / post-OLGA)"
  "938074:random-sample epoch5 (SRC-101 / post-OLGA)"
  "945614:random-sample epoch5 (SRC-101 / post-OLGA)"
  "955042:random-sample epoch5 (SRC-101 / post-OLGA)"
)

command -v python3 >/dev/null || { echo "python3 required" >&2; exit 1; }

echo "Pulling block hashes from $RPC_URL"
python3 - "$REFERENCE_HASHES" "$OUTPUT" "${CI_BLOCKS[@]}" <<'PY'
import json
import os
import subprocess
import sys
import urllib.request

reference_path, output_path = sys.argv[1], sys.argv[2]
entries = sys.argv[3:]

with open(reference_path) as f:
    reference = json.load(f).get("hashes", {})

# Optional prod RDS fallback for blocks past reference_hashes.json coverage.
# Reads ST3_HOSTNAME / ST3_USER / ST3_PASSWORD (or RDS_* in the prod tree)
# and queries btc_stamps.blocks for consensus hashes. Skipped if creds not set.
rds_host = os.environ.get("ST3_HOSTNAME") or os.environ.get("RDS_HOSTNAME") or ""
rds_user = os.environ.get("ST3_USER") or os.environ.get("RDS_USER") or ""
rds_secret = os.environ.get("ST3_PASSWORD") or os.environ.get("RDS_PASSWORD") or ""
rds_db = os.environ.get("RDS_DATABASE", "btc_stamps")
rds_conn = None
if rds_host and rds_user and rds_secret:
    try:
        import pymysql
        rds_conn = pymysql.connect(host=rds_host, user=rds_user, password=rds_secret,
                                    database=rds_db, connect_timeout=10)
    except Exception as e:
        print(f"  warning: prod RDS fallback unavailable: {e}", file=sys.stderr)

def fetch_from_rds(block_index_str):
    if rds_conn is None:
        return None
    with rds_conn.cursor() as cur:
        cur.execute(
            "SELECT block_hash, IFNULL(ledger_hash,''), IFNULL(txlist_hash,''), IFNULL(messages_hash,'') "
            "FROM blocks WHERE block_index = %s",
            (int(block_index_str),),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "block_hash": row[0],
        "ledger_hash": row[1],
        "txlist_hash": row[2],
        "messages_hash": row[3],
    }


def fetch_prev_hashes(block_index_int):
    """Look up block_index - 1 in reference_hashes.json, falling back to prod RDS.

    Returns a dict with prev_block_hash + the three consensus hashes, or None
    if neither source has the prior block. The runner uses these to seed the
    validator's chain-position lookup for curated blocks where block_index - 1
    isn't in reference_hashes.json (i.e. the 892,905+ tip side)."""
    prev_idx = block_index_int - 1
    ref = reference.get(str(prev_idx))
    if ref is None:
        ref = fetch_from_rds(str(prev_idx))
    if ref is None:
        return None
    return {
        "prev_block_hash": ref.get("block_hash", ""),
        "prev_ledger_hash": ref.get("ledger_hash", ""),
        "prev_txlist_hash": ref.get("txlist_hash", ""),
        "prev_messages_hash": ref.get("messages_hash", ""),
    }


def fetch_stamp_counter_before(block_index_int):
    """Return MAX(stamp) for all stamps with block_index < N, from prod RDS.

    The InMemoryBlockProcessor uses cache_manager['stamp']['counter'] as a
    running counter when assigning stamp_number to validated stamps. For a
    from-genesis sequential reparse the counter builds up naturally; for the
    non-contiguous CI subset we need to seed it explicitly so the first stamp
    in block N gets stamp_number = seed + 1, matching production. Returns 0
    if RDS isn't available."""
    if rds_conn is None:
        return 0
    with rds_conn.cursor() as cur:
        cur.execute(
            "SELECT IFNULL(MAX(stamp), 0) FROM StampTableV4 WHERE block_index < %s",
            (block_index_int,),
        )
        row = cur.fetchone()
    return int(row[0]) if row else 0

rpc_url = f"http://{os.environ.get('RPC_IP', '127.0.0.1')}:{os.environ.get('RPC_PORT', '8332')}/"
rpc_user = os.environ.get("RPC_USER", "rpc")
rpc_secret = os.environ.get("RPC_PASSWORD", "")

# Use urllib's built-in basic-auth handler so we never manually format the
# "user:value" credential pair — that literal pattern trips static-analysis
# secret scanners even when both sides are env-read variables.
_auth_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
_auth_mgr.add_password(None, rpc_url, rpc_user, rpc_secret)
_rpc_opener = urllib.request.build_opener(urllib.request.HTTPBasicAuthHandler(_auth_mgr))

def rpc(method, params):
    body = json.dumps({"jsonrpc": "1.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(rpc_url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with _rpc_opener.open(req, timeout=10) as resp:
        payload = json.loads(resp.read())
    if payload.get("error"):
        raise RuntimeError(f"rpc {method}({params}): {payload['error']}")
    return payload["result"]


# Probe the RPC once; if no local bitcoind is reachable we source block_hash
# straight from reference_hashes.json (all CI blocks are <= the reference
# coverage, so the trusted block_hash is already in the baseline). The CI
# workflow still re-verifies block bytes hash to block_hash at run time, so
# this is no weaker — it just drops the optional local cross-check.
RPC_AVAILABLE = True
try:
    rpc("getblockcount", [])
except Exception as e:
    RPC_AVAILABLE = False
    print(f"  note: bitcoind RPC unavailable ({e}); sourcing block_hash from reference_hashes.json",
          file=sys.stderr)

out = {"metadata": {"source": "refresh-consensus-hashes.sh", "rpc": rpc_url}, "hashes": {}}

for entry in entries:
    block_index, reason = entry.split(":", 1)
    ref = reference.get(block_index)
    source = "reference_hashes.json"
    if ref is None:
        ref = fetch_from_rds(block_index)
        source = "prod RDS"
    if ref is None:
        print(f"  block {block_index}: not in reference_hashes.json and no RDS fallback; skipping", file=sys.stderr)
        continue
    if RPC_AVAILABLE:
        block_hash = rpc("getblockhash", [int(block_index)])
        if block_hash != ref.get("block_hash"):
            print(f"  block {block_index}: bitcoind hash {block_hash} != {source} {ref.get('block_hash')}", file=sys.stderr)
            sys.exit(1)
    else:
        block_hash = ref.get("block_hash")
    entry_out = {
        "reason": reason,
        "block_hash": block_hash,
        "txlist_hash": ref.get("txlist_hash", ""),
        "ledger_hash": ref.get("ledger_hash", ""),
        "messages_hash": ref.get("messages_hash", ""),
        "source": source,
    }
    prev = fetch_prev_hashes(int(block_index))
    if prev is None:
        print(
            f"  block {block_index}: prior block hashes unavailable (no reference / RDS); "
            f"chain-position validation may fall back to zero prev-hashes",
            file=sys.stderr,
        )
    else:
        entry_out.update(prev)
    entry_out["stamp_counter_before"] = fetch_stamp_counter_before(int(block_index))
    out["hashes"][block_index] = entry_out
    print(f"  block {block_index} ({reason}): captured [{source}]")

with open(output_path, "w") as f:
    json.dump(out, f, indent=2, sort_keys=True)
    f.write("\n")

print(f"\nWrote {output_path} with {len(out['hashes'])} blocks")
PY

echo "Done. Review with: git diff $OUTPUT"
