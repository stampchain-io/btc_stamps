# Consensus Serializer Replacement — Handoff Brief

**Status:** Investigation complete; implementation deferred to a dedicated session.
**Related work:** PR #751 (libmagic 5.41 pin) — anchors current chain, no hash change.
**Related work (parallel):** In-house byte-prefix classifier replacing libmagic on the consensus path. The serializer change and the classifier change SHOULD be bundled in one height-gated release so operators experience one hash-changing upgrade event and one checkpoint regeneration.

---

## Problem

`indexer/src/index_core/block_validation.py:60-75` constructs three SHA-256 pre-images using Python's `str()` of a list of dicts:

```python
sorted_valid_stamps = sorted(filtered_stamps, key=lambda x: x.get("stamp_number", 0))
txlist_content   = str(sorted_valid_stamps)        # → txlist_hash
ledger_content   = str(processed_src20_in_block)   # → ledger_hash
messages_content = str(txhash_list)                # → messages_hash (not checkpointed but consensus-checked block-to-block)
```

`str()` of a list of dicts is `repr()` formatting. It is **not** a stable contract across:
- Python versions (dict ordering pre-3.7; `Decimal` `__repr__` has shifted)
- Python implementations (PyPy dict ordering historically differed)
- Library versions (`Decimal.normalize()` returns `1E+2` for `Decimal("100").normalize()`)
- Value types (`str(datetime)` and `str(Decimal)` are conventionally stable, not contractually)

The libmagic incident (PR #751) was the same class of bug — an external classifier silently drifted. The serializer is the next-most-likely external dependency to bite us.

## Fields in the consensus pre-images (audit summary)

**ValidStamp** (`indexer/src/index_core/models.py:43-52`; built at `stamp.py:283-302`):
- `stamp_number: int`
- `tx_hash: str` (hex)
- `cpid: str` (normalized at construction)
- `is_btc_stamp: bool`
- `is_valid_base64: bool`
- `stamp_base64: str`
- `is_cursed: bool`
- `src_data: str`

**processed_src20_in_block** (`src20.py:54-105, 136-232`; persisted via `database.py:189-238`):
- `Decimal` for `amt`, `max`, `lim`, `total_minted`, `total_balance_*` — **highest-risk field**
- `int` for `dec`, `tx_index`, `block_index`, `valid`
- `str` for `tick`, `tick_hash`, `op`, `p`, `creator`, `destination`, `tx_hash`, `status`
- `None` for unset fields
- `block_time: Union[int, datetime]` (`models.py:91`) — datetimes can flow through `database.py:191, 259`

**txhash_list**: `list[str]` — safe under `str()`, but should be encoded consistently with the other two.

## Proposed canonical encoder

Drop `default=str` (footgun). Use an explicit normalize-then-JSON helper:

```python
# index_core/canonical_encoder.py
from decimal import Decimal
from datetime import datetime, timezone
import json

def _canon(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, Decimal):
        s = format(v.normalize(), "f")
        return s if s != "-0" else "0"
    if isinstance(v, float):
        raise TypeError("float in consensus pre-image")
    if isinstance(v, datetime):
        return int(v.replace(tzinfo=timezone.utc).timestamp())
    if isinstance(v, (bytes, bytearray)):
        return v.hex()
    if isinstance(v, dict):
        return {k: _canon(v[k]) for k in sorted(v)}
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    raise TypeError(f"non-canonical type {type(v).__name__}")

def canonical_dumps(obj) -> str:
    return json.dumps(_canon(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
```

**Key choices, justified:**
- `format(Decimal.normalize(), "f")` — avoids scientific-notation drift across CPython releases
- `float` raises rather than coerces — floats should not be in consensus pre-images; loud failure is the right mode
- `datetime` → int unix seconds — matches the int branch of `StampData.block_time`
- `bytes` → hex — deterministic, length-encoded
- `sort_keys=True, separators=(",",":"), ensure_ascii=True` — eliminates whitespace, ordering, and unicode-escape ambiguity

## Activation gate

Pattern is already used for consensus changes in this codebase (`config.py:375-379` for `SVG_GZIP_DETECTION_V2`, `ENHANCED_MIME_DETECTION`). Mirror it:

```python
# config.py
CANONICAL_SERIALIZER_V1: int = <SET_TO_~5K_BLOCKS_PAST_CURRENT_TIP>
```

Highest checkpoint in `CHECKPOINTS_MAINNET` today (`check.py:142-145`) is block 885000. Pick a height comfortably ahead — suggestion: **920000** (~5 weeks lead time at 6 blocks/hr). Confirm against current tip when implementing.

Conditional in `block_validation.py:60-75`:

```python
from config import CANONICAL_SERIALIZER_V1
from index_core.canonical_encoder import canonical_dumps

if block_index >= CANONICAL_SERIALIZER_V1:
    sorted_valid_stamps = sorted(
        filtered_stamps,
        key=lambda x: (x.get("stamp_number") is None,
                       x.get("stamp_number") or 0,
                       x.get("tx_hash", "")),
    )
    txlist_content   = canonical_dumps(sorted_valid_stamps)
    ledger_content   = canonical_dumps(processed_src20_in_block)
    messages_content = canonical_dumps(txhash_list)
else:
    sorted_valid_stamps = sorted(filtered_stamps, key=lambda x: x.get("stamp_number", 0))
    txlist_content   = str(sorted_valid_stamps)
    ledger_content   = str(processed_src20_in_block)
    messages_content = str(txhash_list)
```

## Risks that must be handled at the same time

1. **Sort tiebreaker.** Current sort `x.get("stamp_number", 0)` will `TypeError` if any stamp_number is ever explicitly `None` (Python 3 disallows `None < int`). The user has confirmed `stamp_number` should never be `None` or missing for indexed stamps, but the canonical-path sort should be defensive: `(is_none, value, tx_hash)`.
2. **Decimal.normalize() returning scientific notation.** `Decimal("100").normalize()` → `Decimal("1E+2")`. Without `format(..., "f")` the encoder leaks scientific notation into the pre-image.
3. **`block_time` mixed int/datetime.** Explicit coercion to int unix seconds; do NOT rely on `str(datetime)`.
4. **`messages_hash` is on the consensus path even though it isn't checkpointed.** It's compared block-to-block at `check.py:256-262`. The serializer swap must cover it.
5. **Non-BMP unicode in `tick` / `src_data`.** `ensure_ascii=True` handles it in JSON output.
6. **Floats in `StampData`.** `btc_amount`, `fee` are floats (`models.py:84-85`). They are not currently in either consensus dict; the encoder's `float` → raise is the regression guard if anyone ever adds them.

## Operator runbook (checkpoint regeneration)

1. Deploy build with libmagic 5.41 pin (PR #751) AND `CANONICAL_SERIALIZER_V1` set.
2. Reparse from the most recent **pre-activation** checkpoint (today: 885000 in `check.py:142`).
3. Continue indexing past activation height.
4. Once tip is well past activation + the existing 5000-block checkpoint cadence (`check.py:130-145`), run `indexer/tools/checkpoint_updater.py` — it already reads `blocks.ledger_hash`/`txlist_hash` from the DB and rewrites `CHECKPOINTS_MAINNET` in `check.py`.
5. PR the updated `CHECKPOINTS_MAINNET` — old pre-activation checkpoint hashes stay unchanged (gating preserves them).

## Test strategy

- **Golden fixtures.** Capture `(block_index, valid_stamps_in_block, processed_src20_in_block, txhash_list)` for ~20 representative blocks (issuance, OLGA, SRC-20 deploy/mint/transfer, SRC-101, multi-stamp). Compute expected `canonical_dumps` output + SHA-256 once; assert in unit tests.
- **Cross-interpreter matrix.** tox env over `py311, py312, py313, pypy3.10`. Identical hashes.
- **Cross-platform CI.** Add macOS to the canonical-encoder test job (cheap, no DB).
- **Property tests (hypothesis).** Generate Decimals, datetimes, nested dicts; assert `canonical_dumps(_canon(x))` is idempotent under re-encode.
- **Differential gate test.** Below activation height, confirm the conditional preserves byte-identical pre-image to the legacy `str()` implementation. This is the regression guard against accidental encoder bleed-through.
- **Reparse-in-CI.** Extend `indexer/tools/reparse_test_script.py` to reparse a small range straddling activation; assert post-activation checkpoints match.

## Punch list (dependency-ordered)

1. Add `index_core/canonical_encoder.py` with `_canon` + `canonical_dumps`.
2. Add `CANONICAL_SERIALIZER_V1` to `config.py` next to `ENHANCED_MIME_DETECTION`.
3. Update `block_validation.py:60-75` per §"Activation gate" — also harden the sort key tiebreaker for the canonical path.
4. Add golden-fixture unit tests + tox/CI matrix.
5. Add hypothesis property tests for `_canon`.
6. Document operator runbook in `indexer/tools/checkpoint_updater.py` docstring or release notes.
7. After dev-net soak past activation height, regenerate `CHECKPOINTS_MAINNET` entries for ≥activation height.
8. Bundle the release with the in-house classifier (parallel work) so operators experience one consensus upgrade event.

## Key file references

- `indexer/src/index_core/block_validation.py:60-75` — call sites
- `indexer/src/index_core/check.py:17-146` — `CHECKPOINTS_MAINNET`
- `indexer/src/index_core/check.py:182-289` — `consensus_hash()` plumbing
- `indexer/src/index_core/models.py:43-52, 84-91` — `ValidStamp` + `StampData` types
- `indexer/src/index_core/stamp.py:283-302` — ValidStamp construction
- `indexer/src/index_core/src20.py:54-105, 180-199` — SRC-20 dict construction (Decimal fields)
- `indexer/src/index_core/util.py:106-132` — sha256 plumbing
- `indexer/src/config.py:375-379` — existing height-gate pattern
- `indexer/tools/checkpoint_updater.py` — DB-driven checkpoint regen tooling
- `indexer/src/index_core/reparse/` — reparse harness

## Out of scope for this work item

- Replacing libmagic with an in-house classifier — that's a separate work item with the same height-gate and checkpoint-regen mechanics; the two SHOULD ship together but are tracked independently.
- Any change to what gets indexed (which stamps are valid, which are cursed). This work item only changes the bytes that summarize the existing indexed state.
