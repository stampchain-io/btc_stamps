=

# Checkpoint-Based Hash Validation (CI-Optimised)

## 1. Purpose
Validate that the parser still selects the exact same set of Bitcoin transactions for a handful of historical blocks **without** replaying all prior state.  
The method is designed for quick execution in CI (< 1 s) while preserving cryptographic assurance thanks to the chained consensus-hash design already used in production (`index_core.check.create_check_hashes`).

## 2. Core Idea
1. For every block height we want to test we store **two values**
   * `prev_*_hash` – the *previous* consensus hash at height *N-1* (ledger, txlist, messages).
   * `expected_*_hash` – the official hash at height *N* (taken from production / `CHECKPOINTS_MAINNET`).
2. In the test we:
   1. Fetch raw block *N* via RPC (or use a fixture).
   2. Run `filter_block_transactions` to obtain the ordered list of relevant TXIDs.
   3. Call `create_check_hashes` once, passing the **seed** `prev_*_hash` values as the `previous_*` parameters.
   4. Assert that the returned hashes equal `expected_*_hash`.

Because the consensus algorithm itself chains each hash to its predecessor, validating a single block given a trusted predecessor is sufficient and avoids any need to simulate earlier blocks or protocol state.

## 3. Repository Layout
```
snapshots/
├── quick_ci.json   #   {"seeds": {"779700": {...}}, "expected": {...}}
└── reference_full.json  # optional full snapshot for nightly jobs
```

Structure of `quick_ci.json`:
```json
{
  "seeds": {
    "779700": {
      "ledger_prev_hash": "…",
      "txlist_prev_hash": "…",
      "messages_prev_hash": "…"
    },
    "820000": { … }
  },
  "expected": {
    "779700": {
      "ledger_hash": "…",
      "txlist_hash": "…",
      "messages_hash": "…"
    },
    "820000": { … }
  }
}
```
A helper script (`tools/dump_seeds.py`, TBD) extracts both seed and expected hashes directly from a synced database so the file stays authoritative.

## 4. Test Flow (pytest)
```python
@pytest.mark.parametrize("height", [779700, 820000, 885000])
def test_consensus_hash(height, snapshot_mgr):
    seeds  = snapshot_mgr.seeds[height]
    expect = snapshot_mgr.expected[height]

    block_hash = backend.getblockhash(height)
    block_data = backend.getblock(block_hash, 2)
    txids, raw = filter_block_transactions(block_data)

    new_ledger, new_txlist, new_messages = create_check_hashes(
        mock_db, height, [], [], txids,
        seeds["ledger_prev_hash"],
        seeds["txlist_prev_hash"],
        seeds["messages_prev_hash"],
    )

    assert new_txlist == expect["txlist_hash"]
    assert new_ledger == expect["ledger_hash"]
    assert new_messages == expect["messages_hash"]
```
The entire test suite completes in milliseconds because only three RPC calls and one hash computation occur per block.

## 5. Selecting Blocks
Choose heights that exercise parsing edge-cases and protocol transitions, e.g.:
* `CP_STAMP_GENESIS_BLOCK` (779652)
* Whitespace-stripping rule (`STRIP_WHITESPACE`)
* SRC-20 genesis (788041)
* P2WSH/OLGA upgrade (865000)
* Latest checkpoint in `CHECKPOINTS_MAINNET`

Update `quick_ci.json` whenever a **new checkpoint** is added or when a bug-fix changes past hashes.

## 6. Nightly / Full Validation
For deeper assurance, a nightly job can still perform:
* full in-memory replay from genesis (current `reparse` mode), or
* replay between consecutive checkpoints (≤5 000 blocks) using seed hashes as above.

## 7. Roadmap: Merkle-Root Proofs
Long-term we plan to expose an even simpler and externally-auditable proof:
1. **Per-block Merkle root** of the ordered stamp-txid list:  
   `stamps_root = merkle(txids)` using double-SHA-256 internal hashing (Bitcoin style).
2. Store `stamps_root` in snapshot and optionally anchor aggregated roots on-chain via OP_RETURN transactions every N blocks.
3. CI can then recompute `stamps_root` without any seed value (stateless) and compare directly.
4. Inclusion proofs become trivial for external auditors: given a txid and the block height, the Merkle branch shows membership unambiguously.

Implementation hint:
```python
def merkle(leaves):
    if not leaves:
        return "00"*32
    level = [bytes.fromhex(t)[::-1] for t in leaves]
    while len(level) > 1:
        if len(level) & 1:
            level.append(level[-1])
        level = [dbl_sha256(level[i] + level[i+1]) for i in range(0, len(level), 2)]
    return level[0][::-1].hex()
```

This future improvement is complementary; the seed-hash method remains the primary CI guardrail due to its tight coupling with existing consensus-hash code paths.

## 8. Benefits Recap
* **Fast** – <1 s for 10 blocks.
* **Deterministic** – Uses exactly the same `create_check_hashes` production logic.
* **Stateless** – Needs only the prior hashes shipped in the snapshot file.
* **Extensible** – Merkle-root layer will provide external proof-of-inclusion without changing the CI contract.

## 9. Online vs Fixture Mode
The quick-CI tests can run with **live RPC** access or **offline fixtures**.

| Mode | Description | Requirements |
|------|-------------|--------------|
| **Live (default)** | Fetches `getblockhash`, `getblock` and Counterparty issuance data on the fly. Best for internal runners and nightly jobs. | Environment variables: `RPC_USER`, `RPC_PASSWORD`, `RPC_IP`, `RPC_PORT`, plus CP‐node equivalents. These can be set as CI secrets. |
| **Fixture** | Uses pre-saved JSON blobs in `tests/fixtures/` so no external nodes are needed. Ideal for public forks, offline development, or when secrets are unavailable. | Set `CI_FIXTURE_MODE=true`. Ensure fixture files exist (see below). |

### Generating fixtures
Run once on a synced instance:
```bash
# explicit list
poetry run dump_block_fixtures --heights 779652,820000,885000 --out tests/fixtures

# OR derive automatically from the snapshot file (recommended)
poetry run dump_block_fixtures --from-snapshot snapshots/quick_ci.json --out tests/fixtures
```
This helper script (to be added in `indexer/tools/`) will create individual `HEIGHT.json` files in /snapshots/containing:
```json
{
  "block": { … output of getblock(HEIGHT,2) … },
  "cp":    { … output of fetch_xcp_blocks_concurrent … }
}
```
Commit these small files (≈150 kB each) so open-source contributors can run tests without node access.

### Selecting mode inside tests
```python
use_fixture = os.getenv("CI_FIXTURE_MODE", "false").lower() == "true"
if use_fixture:
    blob = json.load(open(Path("tests/fixtures")/f"{height}.json"))
    block_data = blob["block"]
    cp_data    = {height: blob["cp"]}
else:
    block_hash = backend.getblockhash(height)
    block_data = backend.getblock(block_hash, 2)
    cp_data    = fetch_xcp_blocks_concurrent(height, height)
```
The remaining validation logic stays identical.

### Generating seed snapshot
To capture seeds/expected hashes you have two options:

* **Specific heights only**
  ```bash
  poetry run dump-seeds --heights 820000,885000 \
                       --out snapshots/quick_ci.json
  ```
* **All checkpoints plus extras**
  ```bash
  poetry run dump-seeds --heights 820000,900000 \
                       --include-checkpoints \
                       --out snapshots/quick_ci.json
  ```
  The `--include-checkpoints` switch automatically appends every height found in `CHECKPOINTS_MAINNET` so you never forget the official consensus points.

## 10. Extending to txlist_hash & ledger_hash
The quick-CI suite only validates `messages_hash`. To also cover `txlist_hash` and `ledger_hash` you must provide a **state fixture** representing the protocol caches **at block N-1**.

Minimal keys to capture:
```
{
  "stamp_counter": 12345,
  "reissue": {"ASSET1": true, "ASSET2": true},
  "total_minted": {"gme": "21000000"},
  "balance": {"gme:1Boat...": "100"}
}
```
Load this JSON before parsing block N using `reparse_caching.cache_manager.set_cache_value(...)` then run full `create_check_hashes` as in production. A helper script `dump_state_fixtures.py` (TBD) can emit these snapshots.

## 11. Validating txlist_hash & ledger_hash (NEW)

While the quick‐CI suite originally validated only `messages_hash`, we now extend coverage to the remaining two
consensus hashes without compromising execution speed.

### 11.1 What is required?
1. **Valid stamp list for block _N_** –  exactly the `valid_stamps_in_block` list that production keeps after
   `BlockProcessor.process_transaction_results` (sorted by `stamp_number`).
2. **SRC-20 state changes for block _N_** –  the `processed_src20_in_block` list passed into
   `create_check_hashes`.
3. **Seed hashes from block _N − 1_** –  already shipped via `seeds[HEIGHT]` in `quick_ci.json`.

With these three ingredients the existing `create_check_hashes` function can deterministically recompute
`ledger_hash` and `txlist_hash` in a single call – no database or replay required.

### 11.2 Fixture layout additions
We keep the previously generated `BLOCK.json` files and extend their structure with two optional top-level keys:
```jsonc
{
  "block":    { /* unchanged */ },
  "cp":       { /* unchanged */ },
  "valid":    [ /* list[ValidStamp] for block N */ ],
  "src20":    [ /* list[dict] produced_src20_in_block for block N */ ]
}
```
If the `valid`/`src20` keys are missing, tests will gracefully fall back to `messages_hash`-only validation.

### 11.3 Generating extended fixtures
A new helper (`tools/dump_state_fixtures.py`) complements `dump_block_fixtures.py`.
Example usage:
```bash
poetry run dump_state_fixtures --heights 820000,865000 --out tests/fixtures

# or automatically derive the list from the snapshot file
poetry run dump_state_fixtures --from-snapshot snapshots/quick_ci.json --out tests/fixtures
```
`dump_state_fixtures` internally runs the **in-memory** `BlockProcessor` logic for each requested height and dumps
exactly the two structures required for hash calculation.  On typical hardware it needs <40 ms per block, so the
CI runtime impact is negligible.

### 11.4 Test changes
`tests/test_quick_consensus.py` now:
1. Loads `valid` and `src20` if present.
2. Passes them into `create_check_hashes` along with the existing `txids` list and seed hashes.
3. Asserts all three hashes – `messages`, `txlist`, and `ledger`.

### 11.5 Backwards compatibility
Older fixture files that lack the new keys continue to work – only `messages_hash` will be asserted in that case.
This allows a smooth transition for downstream forks.

### 11.6 Static vs Dynamic delta strategy

| Strategy | What is stored in fixture? | What the test recomputes | Pros | Cons |
|----------|---------------------------|--------------------------|------|------|
| **Static-delta** (current default) | Final `valid` & `src20` lists for block N | Nothing (hashes are computed straight from stored lists) | • blazing fast<br>• fixtures are deterministic | • **cannot detect** future code changes that alter the *content* of those lists – only `messages_hash` would fail if filtering changes but deeper validation bugs could slip through |
| **Dynamic** | Minimal cache snapshot for block N−1 (`stamp_counter`, balances, reissue-set, …) | Parses block N during the test to regenerate the lists | • Catches any behaviour change in stamp/SRC-20 parsing logic | • slightly larger fixtures<br>• a few extra milliseconds of compute |

For now we ship the **static-delta** variant because it keeps CI under one second and still guards the most brittle layer: *transaction selection*.  Once the parsing pipeline stabilises we can switch to the dynamic mode with just a fixture tweak—no test code changes required.

> **Important:** when modifying core stamp/SRC-20 validation logic locally, run the full `reparse` test-suite or regenerate state fixtures to ensure no silent divergences are introduced.

---
Last updated : {{DATE}} 