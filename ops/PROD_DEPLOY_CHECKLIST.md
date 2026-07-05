# Production Deploy Checklist — btc_stamps indexer

How to deploy a tagged release to the production systemd service safely, with fork-prevention and post-deploy reconciliation. Prod runs as the host systemd unit `btc-stamps-indexer.service` (working dir `/home/ubuntu/btc_stamps/indexer`, `ExecStart=poetry run indexer`) against an AWS RDS database.

## Golden rules
- **Prod runs a TAGGED RELEASE** (`git checkout <X.Y.Z>`, detached HEAD) — **never** a `dev`/canary branch checkout.
- **Prod's only git remote is `origin` → `stampchain-io/btc_stamps`.** Never add a fork remote (see §6).
- **Deploy only certified releases** — the release must have passed the from-genesis reparse (txlist+ledger hash-identical to the prod-derived reference).
- **Run on Python 3.10–3.12, never 3.13** (3.13 diverges from consensus).
- The prod DB is **AWS RDS**; any reconcile writes there — back up first.

## 1. Pre-flight (READ-ONLY — change nothing)
- [ ] `git -C /home/ubuntu/btc_stamps remote -v` → shows **only** `origin` = `stampchain-io`. **If any other/fork remote exists → STOP, remove it (§6) before continuing.**
- [ ] Working tree clean: `git -C /home/ubuntu/btc_stamps status --porcelain` is empty.
- [ ] Target tag reachable + correct: `git -C /home/ubuntu/btc_stamps ls-remote origin <X.Y.Z>` matches the expected release commit.
- [ ] Service state: `systemctl is-active btc-stamps-indexer.service`; note current VERSION and indexed height (`SELECT MAX(block_index) FROM blocks`).
- [ ] `.env` sanity (`indexer/.env`): `CP_SKIP_NO_COUNTERPARTY_BLOCKS`, `FORCE`, `OPS_ALERT_SNS_TOPIC_ARN`, `API_WEBHOOK_URL`, `RDS_*` set as intended.
- [ ] Disk: enough free for `poetry install` + the Rust `--release` build (`df -h /home`).
- [ ] Runtime: `.venv` Python is 3.10–3.12; `poetry` available.
- [ ] Privileges: passwordless `sudo` for `systemctl` (else a human operator runs the stop/start steps).

## 2. Deploy
- [ ] `git -C /home/ubuntu/btc_stamps fetch origin --tags` → verify `git rev-parse <X.Y.Z>` == expected commit.
- [ ] `sudo systemctl stop btc-stamps-indexer.service` → confirm stopped.
- [ ] `git -C /home/ubuntu/btc_stamps checkout <X.Y.Z>` (detached on the tag) → confirm `VERSION` file == `<X.Y.Z>`.
- [ ] `cd /home/ubuntu/btc_stamps/indexer && poetry install && poetry run task build` (rebuilds the Rust parser, `maturin ... --release`) → build exit 0.
- [ ] Confirm/set env (e.g. `CP_SKIP_NO_COUNTERPARTY_BLOCKS=true`).
- [ ] `sudo systemctl start btc-stamps-indexer.service`.
- [ ] **Verify healthy:** service `active`; logs show `Version updated … <X.Y.Z>`; the startup **chain-integrity check passes**; it resumes and **advances** blocks; no errors/tracebacks. Confirm `SELECT MAX(block_index)` climbs.

## 3. Post-deploy reconciliation (only if the release changes classification/detection)
Some releases improve detection (e.g. SRC-721 IDENT) and reclassify historical rows the running DB still stores under the old value. These are **hash-neutral** (`txlist_hash`/`ledger_hash` unaffected) but should be reconciled.
- [ ] Run `indexer/tools/compare_tables.py` (prod vs a certified dev reparse DB) → get the expected-delta list (e.g. `STAMP → SRC-721`).
- [ ] **Hash-neutrality guard:** confirm `txlist_hash` + `ledger_hash` have **0 diffs**. If either differs → **STOP** — that's a real consensus effect, not a relabel.
- [ ] Back up the affected rows; apply the reconcile as a **reviewed transaction**: pre-flight guard → backup → dry-run (rollback) → real apply (commit) → verify. (See issue #874 for the worked pattern; key on `tx_hash`.)

## 4. Reorg / `messages_hash` artifacts
- Releases ≥ 1.9.1 self-heal reorgs: `verify_recent_chain_integrity()` (startup, `STARTUP_CHAIN_INTEGRITY_DEPTH`, default 100) compares stored `block_hash` vs bitcoind and rolls back to the oldest divergence; the reorg-recovery path recomputes **all** hashes together. So a mid-reorg crash no longer leaves a stale `messages_hash` behind a correct `block_hash`.
- A **pre-existing** stale `messages_hash` (correct `block_hash`, so the startup check won't catch it) is repaired with a one-time roll-back-reindex: stop → `purge_block_db(<first_diverged_block>)` (in a verified transaction) → start → it reindexes forward and recomputes correct hashes. Non-consensus; ~15–40 min reindex with a temporary recent-block availability gap. (See the 955,070 `messages_hash` fix for the worked pattern.)

## 5. Rollback
If the new release misbehaves:
- [ ] `sudo systemctl stop btc-stamps-indexer.service`
- [ ] `git -C /home/ubuntu/btc_stamps checkout <previous-tag>` (or the prior commit)
- [ ] `cd indexer && poetry install && poetry run task build`
- [ ] `sudo systemctl start btc-stamps-indexer.service` — the DB resumes from its last block.

## 6. Fork-prevention (permanent invariant)
Production must **never** have a non-`stampchain-io` git remote — a careless `git checkout <fork>/<branch>` or `git pull <fork>` would run **untrusted code on the consensus node**.
- [ ] Audit routinely: `git -C /home/ubuntu/btc_stamps remote -v` → only `origin` = `stampchain-io`.
- [ ] If a fork/foreign remote ever appears: `git remote remove <name>`, `rm -rf .git/refs/remotes/<name>`, and **investigate how it was added**. Verify the running code is a canonical commit (`git merge-base --is-ancestor <HEAD> origin/<default>` in a canonical clone).
