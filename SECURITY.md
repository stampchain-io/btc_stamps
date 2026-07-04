# Security Policy

The Bitcoin Stamps indexer is **consensus-critical** infrastructure: a divergence in the
rolling consensus hashes (`txlist_hash` / `ledger_hash` / `messages_hash`) can fork the
view of the protocol across nodes. We take security and consensus reports seriously.

## Supported versions

Security and consensus fixes target the active development line and the most recent
release series. Older releases are not maintained.

| Version            | Supported          |
| ------------------ | ------------------ |
| `dev` (latest)     | :white_check_mark: |
| Latest `1.8.x`     | :white_check_mark: |
| Older releases     | :x:                |

## Reporting a vulnerability

**Do not open a public issue for security, consensus, or supply-chain problems.**

Report privately via GitHub Security Advisories:

➡️ https://github.com/stampchain-io/btc_stamps/security/advisories/new

### In scope (and should be reported privately)

- **Consensus divergence** — any input that causes the indexer to produce a different
  `txlist_hash` / `ledger_hash` / `messages_hash` than the reference/checkpoints, or any
  way to make nodes disagree.
- **Supply-chain** — compromised or tampered dependencies, build/release pipeline issues,
  or drift in consensus-critical pinned packages (e.g. regex / PyNaCl / pybase64).
- Memory-safety, RCE, injection, credential exposure, or denial-of-service in the indexer
  or its tooling.

## Response expectations

- We aim to acknowledge a report within **3 business days**.
- We will work with you on a fix and a coordinated disclosure timeline, and will credit
  reporters who wish to be named.

Please give us a reasonable opportunity to remediate before any public disclosure.
