# Rust-parser output snapshots (`parser_snapshots.json`)

Byte-exact snapshots of the Rust parser
(`btc_stamps_parser.FastTransactionParser`) output for a committed corpus of
real stamp transactions. Used by **`tests/test_parser_snapshots.py`** to catch
consensus drift in parser output on every PR — at unit-test speed, with **no
DB, no docker, and no network** (it only needs the compiled `btc_stamps_parser`
extension). See issue [#765].

## Why this exists

`TransactionInfo` (the parser's output) is a **pure function of the transaction
bytes**: deserialize via the `bitcoin` crate → multisig/keyburn classification,
P2WSH/OLGA pattern detection, and the ARC4 `PREFIX` check (`arc4.rs`). A bump to
a consensus-surface crate (`bitcoin`, `pyo3`, `hex`, `rand`) could silently move
that output. The only other ground-truth check today is a full from-genesis
reindex against prod RDS — a manual 24-48h job. This snapshot gives ~80% of the
per-PR signal at ~1% of the cost: a crate bump either keeps the bytes stable
(ship with confidence) or fails this test and makes the diff visible *before*
anyone sinks a day into a reindex.

It is **not** a replacement for the release-gate reindex — the corpus is ~20
transactions, not the whole chain — but it turns "silent divergence on a dep
bump" into a fast, loud CI failure.

## What the corpus covers

The snapshot is built from two committed, network-free sources:

- `tests/fixtures/transaction_cache/*.json` — real stamp transactions (each with
  a raw `hex` field and `block_height`).
- `tests/fixtures/bitcoin_node_fixtures.json` → `special_transactions`.

Together they exercise the Rust parser's classification branches: multisig
keyburn detection, the ARC4 `PREFIX` check (valid-data **true and false**),
P2WSH/OLGA pattern detection, and `should_include` **true and false**.
`test_corpus_covers_parser_code_paths` asserts this spread stays intact.

> **Scope note:** MIME type and SRC-20 / SRC-721 / SRC-101 *class* are decided
> **downstream in Python**, not in the Rust parser — at this layer they are all
> just multisig / P2WSH bytes. This snapshot therefore covers the *Rust*
> consensus surface (deserialize + ARC4 + script classification). To widen
> coverage, drop more transaction fixtures into `transaction_cache/` and re-run
> `refresh.sh`.

## Regenerating

Run this **only** after an *intentional*, reindex-validated change to the parser
or its consensus-surface dependencies — refresh the baseline in the **same PR**
as the change, so the bump becomes a deliberate, reviewable baseline move rather
than a silent behavior shift:

```sh
./indexer/tests/fixtures/parser_snapshots/refresh.sh
```

(Equivalently, from `indexer/`: `poetry run python -m tests.parser_snapshot_utils`.)

The generator lives in `tests/parser_snapshot_utils.py`; output is written with
sorted keys and entries sorted by txid, so regeneration is deterministic and
diffs stay minimal.

[#765]: https://github.com/stampchain-io/btc_stamps/issues/765
