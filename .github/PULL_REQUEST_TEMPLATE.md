<!--
Bitcoin Stamps Indexer — Pull Request
Base branch MUST be `dev` (not `main`). v1.9.0 cuts via long-running PR #495 (dev→main).
-->

## Summary

<!-- What does this PR do and why? Link the issue: Closes #NNN -->

## Consensus impact

This is a Bitcoin **consensus-critical indexer**. Any change on the decode/filter/parse
path must be output-neutral OR flag-gated and default OFF. Pick one:

- [ ] **None** — does not touch the decode/filter/parse path or the rolling hashes
      (txlist_hash / ledger_hash / messages_hash).
- [ ] **Output-neutral** — touches the consensus path but the three rolling hashes are
      provably identical.
- [ ] **Flag-gated, default OFF** — new behavior is behind a flag. Flag name: `__________`.

## Validation

- [ ] Lint clean: `isort` / `black` / `flake8` / `mypy` / `bandit`
      (one-shot: `poetry run lint`; full gate: `poetry run check-code`).
- [ ] Unit suite green (`poetry run task test-unit`, i.e. `-m "not requires_bitcoin_node and not integration"`).
- [ ] **Reparse Consensus Validation green** for any consensus-path change —
      txlist + ledger hashes identical (`reparse-validate.yml`; local:
      `poetry run python ci/ci_reparse_subprocess.py --limit 5`). N/A if "None" above.

## Housekeeping

- [ ] Base branch is `dev`.
- [ ] Milestone set (e.g. `v1.9.0`) and labels applied
      (`consensus` / `ci` / `perf` / `supply-chain` / `documentation`).
- [ ] Files staged **explicitly** — never `git add -A`.
- [ ] Did **not** hand-edit `VERSION` / `pyproject` version / `config.py:VERSION_STRING`
      (version bumps are automated via `.bumpversion.cfg`).
