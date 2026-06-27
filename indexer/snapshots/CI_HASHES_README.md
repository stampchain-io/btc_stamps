# `ci_consensus_hashes.json`

Curated subset of consensus-checkpoint hashes used by the per-PR
`reparse-validate` CI workflow (78 blocks). Each entry pins either a known
consensus-boundary block from `indexer/src/config.py` (a PR #753 reference
case, or an era anchor) **or** a deterministically chosen
[stratified-random sample](#stratified-random-sampling-issue-778) block, and
records its expected `block_hash`, `txlist_hash`, `ledger_hash`, and
`messages_hash`.

## How this fits into the consensus-baseline file hierarchy

Three files in this repo carry consensus hashes; each has one job. They are
**not** redundant — they have overlapping data but different roles and
different readers.

| File | Role | Authority | Reader |
|---|---|---|---|
| `indexer/src/index_core/check.py:CHECKPOINTS_MAINNET` | Runtime self-check inside the indexer | Live; carries only `ledger_hash` + `txlist_hash` to stay small | The indexer at every checkpoint as it processes blocks |
| `indexer/snapshots/reference_hashes.json` | Canonical replay baseline (every block 779652..) | **The source of truth.** Full per-block: `block_hash` + `ledger_hash` + `txlist_hash` + `messages_hash` | `poetry run reparse`, `validate_hashes.py` |
| `indexer/snapshots/ci_consensus_hashes.json` (this file) | Curated subset for per-PR CI | **Derived** from `reference_hashes.json` (and prod RDS for recent anchors past `reference_hashes.json`'s coverage) | The `reparse-validate` workflow |

`ci_consensus_hashes.json` is regenerable from
`./indexer/ci/refresh-consensus-hashes.sh`. It's not authoritative — if
`reference_hashes.json` and `ci_consensus_hashes.json` ever disagree, the
fix is "regenerate the derived file."

The fourth piece — `indexer/ci/validate_checkpoints_vs_reference.py` — runs
on every relevant PR via the same `reparse-validate` workflow and asserts
that every block in `CHECKPOINTS_MAINNET` matches `reference_hashes.json`.
That catches the "someone edited one file without refreshing the other"
failure mode automatically. The three files are independently maintained;
this check is what enforces the invariant that they agree.

## Why these blocks specifically

Each known consensus transition from `config.py` is covered as a triple:
**boundary-1 / boundary / boundary+1**. A parser regression that misfires at
the activation point is caught either by the "block before" (feature should
not yet be active) or by the "block at / after" (feature should be active).
The current list:

| Block | What changes there |
|---|---|
| 779652 | `CP_STAMP_GENESIS_BLOCK` — first valid CP-encoded stamp (no `-1` — pre-genesis has no stamp activity and isn't in `reference_hashes.json`) |
| 784549, 784550, 784551 | `STOP_BASE64_REPAIR` — tier-3 base64 padding repair turns off |
| 788040, 788041, 788042 | `CP_SRC20_GENESIS_BLOCK` — first SRC-20 on Counterparty |
| 789624 | PR #753 ref tx `c129cc8f…` — CP SRC-20 mint, base64 mod4=3 |
| 792369, 792370, 792371 | `CP_SRC721_GENESIS_BLOCK` — first SRC-721 |
| 793067, 793068, 793069 | `BTC_SRC20_GENESIS_BLOCK` — SRC-20 leaves CP for native BTC |
| 795999, 796000, 796001 | `CP_SRC20_END_BLOCK` — last SRC-20 honoured on CP |
| 815129, 815130, 815131 | `CP_BMN_FEAT_BLOCK_START` — BMN audio file support |
| 832999, 833000, 833001 | `CP_P2WSH_FEAT_BLOCK_START` — OLGA / P2WSH enabled |
| 864999, 865000, 865001 | `BTC_SRC20_OLGA_BLOCK` — SRC-20 P2WSH OLGA encoding |
| 870651, 870652, 870653 | `BTC_SRC101_GENESIS_BLOCK` — first SRC-101 |
| 872000 | PR #753 ref STAMP→SRC-721 reclassification cluster |
| 890000, 900000, 910000, 920000, 930000, 940000, 950000 | OLGA-era / post-OLGA round-number anchors, all within `reference_hashes.json` (which now covers 779652–955061) |

In addition to these hand-picked boundary/anchor blocks, the baseline now
carries a **stratified-random sample** of ~8 blocks per protocol epoch — see
[Stratified random sampling](#stratified-random-sampling-issue-778) below.

The set covers both **CP-era SRC-20** (788040–796001) *and* **native-BTC
SRC-20** (793067+ / OLGA 864999+), which is the explicit dual-coverage
requirement called out in #765.

### Source of every entry

Each entry in `ci_consensus_hashes.json` records a `source` field so
maintainers can tell at review time where the hash came from. As of issue
#778, **`reference_hashes.json` now covers the full range 779652–955061**, so
**every curated block — including the 900000–950000 anchors that were
previously pulled from prod RDS — is sourced from `reference_hashes.json`**.
The whole derived file is regenerable offline by anyone, with no prod access.

The refresh script still has a `prod RDS` fallback (gated on
`ST3_HOSTNAME` / `ST3_USER` / `ST3_PASSWORD`, or `RDS_*`) for any future block
beyond `reference_hashes.json`'s coverage, but it is **left unset** for normal
refreshes so the script never touches prod. If no local bitcoind RPC is
reachable, the script sources `block_hash` directly from `reference_hashes.json`
as well (the CI workflow re-verifies block bytes against `block_hash` at run
time regardless, so this is trust-neutral).

> Note: regenerating from `reference_hashes.json` in #778 also corrected one
> drifted value — `950000.messages_hash` — which had been captured from prod
> RDS at `4eff1929…` but is `e1f20434…` in the canonical baseline. Per the
> rule above, the source of truth wins.

### Stratified random sampling (issue #778)

The boundary triples above prove the parser at each consensus *transition*.
To also catch regressions in the *interior* of each protocol era, the baseline
adds a deterministic, regenerable **stratified-random sample** of ~8 blocks per
epoch, generated by `indexer/ci/select_random_ci_blocks.py`.

**Epochs** (boundaries from `indexer/src/config.py`):

| Epoch | Range | Era |
|---|---|---|
| 1 | 779652–788040 | pre-SRC20 / CP_STAMP |
| 2 | 788041–793067 | CP-SRC20 |
| 3 | 793068–864999 | BTC-SRC20 pre-OLGA |
| 4 | 865000–870651 | OLGA |
| 5 | 870652–955061 | SRC-101 / post-OLGA |

**Selection criterion** — a block `N` is a candidate iff, in
`reference_hashes.json`:

1. `ledger_hash[N] == ledger_hash[N-1]` — no net SRC-20 ledger mutation, so the
   DB-free Tier-3 runner (seeded with the previous block's ledger hash) can
   reproduce `ledger_hash` without prior balances / mints / deploys; **and**
2. `txlist_hash[N] != txlist_hash[N-1]` — real stamp / Counterparty parse
   activity, so the block gives meaningful Tier-3 coverage; **and**
3. `N` is not already curated and is not a runtime checkpoint (those
   short-circuit the validator); **and**
4. `int(sha256(str(N)).hexdigest(), 16) % 23 == 0` — a stable pseudo-random
   1/23 subsample so the choice is spread, deterministic, and regenerable; **and**
5. `N` is ≥ 50 blocks away from every consensus-activation height.

That offline `ledger_hash`-unchanged rule is a strong **necessary** filter but
is empirically **not sufficient**: a few early native-BTC-SRC20 blocks (e.g.
793074, right at `BTC_SRC20_GENESIS_BLOCK`, and the STOP_BASE64_REPAIR boundary
— see #775) are ledger-unchanged yet still diverge on `txlist_hash` in the
in-memory runner. So the **binding** criterion is that each block *actually
passes* `ci/smoke_parser_validation.py --block N` end-to-end (block + txlist +
ledger). `select_random_ci_blocks.py --validate` enforces this gate, replacing
any failing candidate with the next deterministic one — so **every sampled
block is empirically Tier-3-green and none land in `TIER3_CROSS_BLOCK_LEDGER`.**

**Regenerate** the sample and the derived hash file:

```bash
cd indexer
# Optional fast path: point at a trusted txindex node to skip blockstream
# rate limits (block bytes are still hash-verified):
export CI_BITCOIN_RPC_URL=http://127.0.0.1:8332/ \
       CI_BITCOIN_RPC_USER=… CI_BITCOIN_RPC_PASSWORD=…
poetry run python ci/select_random_ci_blocks.py --validate   # prints CI_BLOCKS lines
# paste the lines into ci/refresh-consensus-hashes.sh, then:
./ci/refresh-consensus-hashes.sh                             # rebuilds the JSON
```

### Not yet included

- **Future planned activations** like a second OLGA-style protocol upgrade
  beyond what's in `config.py` today. Add when the activation block is
  proposed and a triple (boundary-1, boundary, boundary+1) is meaningful.

## Where block bytes come from at CI time

The workflow fetches each block's raw bytes from one of:

1. **`BITCOIN_RPC_URL` + `BITCOIN_RPC_USER` + `BITCOIN_RPC_PASSWORD`** GitHub
   Actions secrets — if set, the workflow calls `getblock <hash> 0` against
   the configured node. Use this when the CI runner has access to a trusted
   bitcoind (e.g. sparky's LAN node).
2. **`blockstream.info` public node** — fallback when no secrets are set.
   Bitcoin blocks are content-addressed: the workflow rejects any block whose
   bytes don't hash to the expected `block_hash`, so node trust is bounded by
   the integrity of this baseline file (i.e. by maintainer review of the
   refresh commit). A malicious blockstream response cannot produce a valid
   block_hash without breaking SHA256.

Block bytes are downloaded once per curated block per CI run regardless of
source. The list (78 blocks: the consensus-boundary triples/anchors plus the
issue-#778 stratified-random sample) is kept deliberately bounded to keep this
tractable; a trusted `BITCOIN_RPC_URL` avoids public-node rate limits entirely.

## Refresh workflow

Whenever you intentionally change a consensus block height in `config.py`,
add a new boundary entry to the curated list, or update the baseline after a
validated reindex:

```bash
./indexer/ci/refresh-consensus-hashes.sh
git add indexer/snapshots/ci_consensus_hashes.json
git diff --cached indexer/snapshots/ci_consensus_hashes.json   # eyeball
git commit
```

The refresh script reads from local bitcoind (`indexer/.env.local`-configured
RPC) and cross-checks the hashes against
`indexer/snapshots/reference_hashes.json`. If they don't match, the script
fails — that's a signal something has drifted and you need to investigate
before refreshing.

## Status — what this check covers today vs the planned follow-up

**Today (first commit of #765):** the workflow fetches each block, verifies
the SHA256 of its bytes matches `block_hash`. This proves baseline integrity
end-to-end on every PR.

**Planned follow-up:** wire `indexer/src/index_core/reparse/validator.py`
into the workflow so the indexer parser pipeline actually runs against each
block and the resulting `txlist_hash` / `ledger_hash` / `messages_hash` are
asserted against the baseline. That's the layer that catches Bucket A dep
bumps and Rust-parser regressions. The current PR lands the scaffolding so
the next iteration is purely "extend `ci_validate_consensus.py` to invoke the
parser." See the TODO in `indexer/ci/ci_validate_consensus.py`.

The check is **advisory on land**. Promote to required-on-dev after one
bake cycle confirms zero false positives.
