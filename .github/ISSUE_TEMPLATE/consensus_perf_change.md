---
name: Consensus / performance change
about: Propose a change to the decode/filter/parse path, the ledger engine, or indexer performance
title: 'area: '
labels: ''
assignees: ''
---

## Context

<!-- Where in the indexer does this live? e.g. index_core/src20.py, rust_parser/lib.rs, ci/. -->

## What

<!-- The proposed change, concisely. -->

## Why

<!-- Motivation: correctness, performance, maintainability, supply-chain, etc. -->

## Consensus risk

- Does this touch the **txlist_hash / ledger_hash / messages_hash** path? (yes / no)
- If yes, is it **output-neutral** or **flag-gated, default OFF**? (flag name if any)
- How will neutrality be proven via differential reparse?
  (Reparse Consensus Validation — txlist + ledger identical;
  full from-genesis stampsdev reindex for cross-block SRC-20 `ledger_hash`.)

## Acceptance criteria

- [ ] Lint + unit suite green.
- [ ] **Reparse Consensus Validation green** (txlist + ledger identical), or change is
      proven not to touch the consensus path.
- [ ] Behavior either output-neutral or flag-gated default OFF.

## References

<!-- Related issues/PRs, docs (docs/ARCHITECTURE.md, PROTOCOLS.md), commits, milestone. -->
