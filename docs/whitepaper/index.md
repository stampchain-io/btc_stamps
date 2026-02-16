---
title: "Bitcoin Stamps Protocol: A Technical Whitepaper"
description: "Permanent digital asset protocol leveraging Bitcoin UTXO permanence through bare multisig and P2WSH encoding"
leoType: "whitepaper"
audience: "unified"
version: "1.0"
date: "2026-02-16"
authors: ["The Original Trinity", "Bitcoin Stamps Community"]
mentions: ["bitcoin-stamps", "src-20", "src-721", "src-101", "olga", "counterparty", "utxo", "p2wsh"]
culturalSignificance: "high"
category: "technical-specification"
---

# Bitcoin Stamps Protocol: A Technical Whitepaper

## Abstract

Bitcoin Stamps is a metaprotocol for creating permanent, immutable digital assets on Bitcoin through direct UTXO storage. Unlike witness-data approaches, Bitcoin Stamps embed asset data in transaction outputs using bare multisig and P2WSH encoding, ensuring universal node storage and consensus-critical permanence.

The protocol evolved from Counterparty foundations (block 779,652) through native Bitcoin encoding (block 793,068) to P2WSH optimization via OLGA (block 865,000). Built on account-based asset tracking, Bitcoin Stamps support fungible tokens (SRC-20), non-fungible assets (base stamps), decentralized naming (SRC-101), and composable recursion (SRC-721).

**Core Innovation**: Leveraging Bitcoin's UTXO set for permanent data storage, making asset data consensus-critical and unprunable. All full nodes must store stamp data to validate transactions, guaranteeing permanence as long as Bitcoin exists.

**Key Properties**:
- **UTXO-based permanence**: Data stored in spendable outputs, not witness segments
- **Consensus-critical storage**: Required for transaction validation across all nodes
- **Account-based assets**: Counterparty-style balance tracking, not UTXO-bound tokens
- **Multi-protocol support**: Extensible architecture for tokens, names, and recursion
- **Cost-optimized encoding**: OLGA P2WSH reduces fees 30-95% vs bare multisig

**Architecture**: The protocol separates data encoding (UTXO layer) from asset tracking (account layer). Stamps create permanent records in Bitcoin's UTXO set while maintaining balances through Counterparty-proven account ledger. This hybrid approach combines Bitcoin's permanence with practical asset management.

---

## Table of Contents

1. **[Introduction](./introduction.md)** — Protocol motivation, history, evolution
2. **[Protocol Architecture](./architecture.md)** — UTXO storage, encoding layers, account model
3. **Data Encoding Methods** — Bare multisig, P2WSH/OLGA technical specs
4. **[Token Standards](./token-standards.md)** — SRC-20 tokens, SRC-721 recursion, SRC-101 names
5. **[Economic Model](./economics.md)** — Fee structures, miner incentives, sustainability
6. **[Stamps Improvement Proposals](./improvement-proposals.md)** — SIP governance, active proposals, roadmap
7. **[Implementation](./implementation.md)** — Indexer architecture, consensus model, validation logic
8. **[Security Analysis](./security.md)** — Permanence guarantees, attack vectors, mitigations
9. **[Future Directions](./future.md)** — Conditional transfers, privacy, bridges, research areas
10. **Appendices** — Reference implementations, test vectors, block timeline

---

## Document Structure

This whitepaper consists of multiple sections:

- **[introduction.md](./introduction.md)** — Protocol history from Counterparty origins (block 779,652) through native encoding (793,068) to OLGA optimization (865,000)
- **[architecture.md](./architecture.md)** — Technical architecture: UTXO storage model, bare multisig vs P2WSH encoding, account-based asset tracking
- **[token-standards.md](./token-standards.md)** — SRC-20, SRC-721, SRC-721r, SRC-101 specifications
- **[economics.md](./economics.md)** — UTXO permanence economics, storage costs, fee analysis
- **[improvement-proposals.md](./improvement-proposals.md)** — SIP governance framework and active proposals (SIP-0001 through SIP-0008)
- **[implementation.md](./implementation.md)** — Indexer architecture, consensus mechanisms, validation logic
- **[security.md](./security.md)** — Threat model, attack vectors, immutability guarantees
- **[future.md](./future.md)** — Roadmap for conditional transfers, privacy enhancements, cross-chain bridges

---

## Quick Reference

**Genesis Block**: 779,652 (March 29, 2023) — First Bitcoin Stamp by Mikeinspace
**Native Encoding**: 793,068 (April 20, 2023) — Direct Bitcoin encoding begins
**Counterparty Cutoff**: 796,000 (August 15, 2023) — SRC-20 consensus rule
**OLGA Activation**: 865,000 (October 15, 2023) — P2WSH optimization available

**Foundation**: Built on Counterparty protocol (est. 2014) for proven account-based asset tracking
**Storage Model**: UTXO-based (consensus-critical, unprunable)
**Asset Model**: Account-based (balances tracked per address, not per UTXO)

---

*This whitepaper serves as the canonical technical specification for Bitcoin Stamps protocol. All implementations should reference this document for protocol compliance.*
