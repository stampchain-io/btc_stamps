---
title: "Bitcoin Stamps Protocol: Introduction"
description: "Protocol motivation, historical evolution from Counterparty origins to P2WSH optimization"
section: 1
prev: "./index.md"
next: "./architecture.md"
---

# 1. Introduction

## 1.1 Motivation

Bitcoin's primary innovation is permanent, censorship-resistant value storage backed by proof-of-work consensus. While Bitcoin enables programmable transactions through Script, the network primarily serves as monetary infrastructure. Bitcoin Stamps extends this permanence to arbitrary data—images, tokens, names—by embedding information directly in Bitcoin's UTXO set.

**Core Problem**: Digital assets require permanent storage to retain value. Traditional NFT platforms rely on IPFS, Arweave, or centralized servers—all subject to failure modes outside asset holders' control. Even Bitcoin-based solutions using witness data lack permanence guarantees since nodes can prune witness segments after validation.

**Solution**: Store asset data in transaction outputs (UTXOs) rather than witness data or external systems. Bitcoin's consensus rules require all full nodes to maintain the UTXO set for transaction validation, making UTXO-embedded data:

- **Consensus-critical**: Required for network operation
- **Unprunable**: Cannot be removed without breaking validation
- **Universal**: Stored by every full node globally
- **Permanent**: Survives as long as Bitcoin exists

**Design Philosophy**: Embrace Bitcoin's constraints rather than fight them. Higher fees for UTXO storage reflect true economic cost of permanent Bitcoin storage. Protocol design prioritizes permanence over convenience, aligning with Bitcoin's long-term value proposition.

## 1.2 Historical Context

### 1.2.1 Counterparty Foundation (2014-2023)

Bitcoin Stamps builds on Counterparty protocol, established January 2014 as Bitcoin's first metaprotocol for asset creation. Counterparty introduced:
- **Account-based assets**: Balance ledger tracked per address, not per UTXO
- **OP_RETURN encoding**: Embed metadata in 80-byte provably unspendable outputs
- **Decentralized exchange**: On-chain order books and atomic swaps
- **10+ years production**: Battle-tested architecture handling millions of transactions

Counterparty proved account-based asset tracking works at scale on Bitcoin. Rather than track which UTXOs contain tokens (complex, privacy-leaking), maintain address-level balances (simple, efficient, private).

**Critical insight**: SRC-20 tokens inherit Counterparty's account model. Token ownership is tracked per address in indexer state, NOT embedded in specific UTXOs. This is foundational to Bitcoin Stamps architecture.

### 1.2.2 Genesis: Block 779,652 (March 29, 2023)

Mikeinspace created the first Bitcoin Stamp—a laser-eyes pixel art embedded via Counterparty transaction. This stamp used traditional OP_RETURN encoding but sparked recognition: Bitcoin could permanently store visual art, not just monetary metadata.

**Innovation**: Frame digital art as permanent Bitcoin artifacts rather than ephemeral files. If art data lives in Bitcoin's UTXO set, it inherits Bitcoin's permanence and censorship resistance.

**Community formation**: The Original Trinity (Mikeinspace, Arwyn, Reinamora) recognized potential for permanent digital culture on Bitcoin. Within days, Stampchain.io launched as reference indexer and minting interface, establishing infrastructure for ecosystem growth.

### 1.2.3 Cultural Milestone: KEVIN (Blocks 783,718 & 788,041)

**Block 783,718** (March 15, 2023): Arwyn created KEVIN (Stamp #4258) as homage to Rare Pepe culture. The artwork unexpectedly exhibited "ghost-like" behavior—appearing in unexpected system locations, inspiring organic derivative works. KEVIN evolved from artistic experiment to community symbol.

**Block 788,041** (April 20, 2023): Arwyn deployed KEVIN as first SRC-20 token (Stamp #18,516), formalizing fungible token standard atop Bitcoin Stamps. This dual nature (unique stamp #4258 + fungible token) established pattern: stamps provide non-fungible foundation, SRC-20 adds fungible layer.

**Cultural impact**: KEVIN demonstrated fair launch principles—no pre-mine, equal minting access, community-driven distribution. These values became protocol philosophy: "we are all Kevin" (echoing Mayan "In Lak'ech Ala K'in"—"I am you, you are me"). Over 2,300 holders grew organically without marketing or speculation.

### 1.2.4 Technical Evolution: Block 793,068 (April 20, 2023)

First stamp using native Bitcoin bare multisig encoding rather than Counterparty OP_RETURN. This transition marked protocol independence—stamps no longer required Counterparty infrastructure, only Bitcoin itself.

**Bare multisig encoding**:
```
OP_1 <pubkey1> <pubkey2> <pubkey3> OP_3 OP_CHECKMULTISIG
```
Each "pubkey" is 32 bytes of image/data. A 2-of-3 multisig provides 64 bytes usable data per output. Multiple outputs chain together for larger assets.

**Advantages**:
- Direct Bitcoin encoding without metaprotocol dependencies
- UTXO-based storage (consensus-critical, unprunable)
- No witness data—data is part of transaction validation itself
- Simplified indexer logic (scan multisig outputs, decode data)

**Tradeoffs**: Higher fees (4x witness discount lost) but guaranteed permanence. Design choice: pay for true permanence rather than optimize for cost.

### 1.2.5 Asset Standards: Blocks 788,041 - 796,000

**SRC-20 fungible tokens** (block 788,041): JSON metadata in stamp encoding defines DEPLOY, MINT, TRANSFER operations. Indexers maintain account balances per Counterparty model—ownership tracked by address, not UTXO.

**SRC-721 recursion** (block 792,370): Stamps can reference other stamps by ID, enabling composable artwork. A stamp might combine background #1234 + character #5678 + effects #9012, creating infinite combinations from finite on-chain components.

**Counterparty cutoff** (block 796,000): Community consensus rule—SRC-20 tokens on Counterparty only valid until block 796,000. After this, only Bitcoin-native encoded tokens recognized. Ensures protocol independence while honoring early adopters.

### 1.2.6 Optimization: OLGA at Block 865,000 (October 15, 2023)

Reinamora introduced OLGA (Octet Linked Graphical Artifacts)—P2WSH encoding replacing bare multisig for 30-95% cost reduction.

**P2WSH structure**:
```
OP_0 <32-byte-hash-of-witness-script>
```
Witness script contains data, hashed and stored in output. More efficient than bare multisig pubkeys in output scripts.

**Key insight**: P2WSH witness scripts are still consensus-critical (unlike witness data for signatures). Scripts must be provided to spend P2WSH outputs, so nodes must store them for UTXO validation. Data remains unprunable and permanent.

**Cost reduction mechanism**:
- Bare multisig: 3 fake pubkeys (96 bytes) per output in transaction data
- P2WSH: 32-byte hash per output, actual data in witness script
- Witness discount: 4:1 reduction (witness data counted at 1/4 weight)
- Result: 60-80% fee reduction for typical stamps

**OLGA benefits**:
- Maintains UTXO permanence (witness scripts are consensus-critical)
- Dramatically reduces creation costs (broader accessibility)
- Better miner priority (more efficient byte usage)
- Universal compatibility (works across all stamp protocols)

## 1.3 Protocol Overview

Bitcoin Stamps protocol comprises:

1. **Data encoding layer**: Bare multisig (pre-865,000) or P2WSH/OLGA (post-865,000) for embedding data in UTXOs
2. **Asset tracking layer**: Account-based ledger (Counterparty-style) for ownership and balances
3. **Standards layer**: SRC-20 (tokens), SRC-721 (recursion), SRC-101 (names) defining asset semantics
4. **Indexer layer**: Software parsing stamp transactions, maintaining asset state, serving APIs

**Critical distinction**: Encoding determines WHERE data is stored (UTXOs). Asset tracking determines WHO owns WHAT (accounts). These layers are independent—SRC-20 tokens use UTXO storage for transaction permanence but account balances for ownership tracking.

## 1.4 Design Principles

**Permanence over cost**: Pay Bitcoin's true storage cost rather than rely on prunable witness data or external systems. Expensive stamps reflect accurate economics of permanent Bitcoin storage.

**Simplicity over features**: Account-based assets simpler than UTXO-bound tokens. Proven Counterparty model beats novel approaches requiring complex state tracking.

**Bitcoin-native alignment**: Work with Bitcoin's economic incentives (UTXO storage fees support miners) rather than fight them (clever witness hacks ultimately prunable).

**Community governance**: Fair launches (no pre-mines), organic growth (no VC funding), cultural values (authenticity over speculation). KEVIN's success demonstrates aligned incentives create sustainable ecosystems.

**Extensibility**: Base stamp protocol provides permanence primitive. Standards like SRC-20/721/101 add semantics without modifying underlying encoding. Future protocols can leverage same UTXO permanence.

## 1.5 Document Scope

This whitepaper specifies:
- UTXO storage architecture and data encoding — bare multisig and P2WSH/OLGA (Section 2)
- Token standards — SRC-20, SRC-721, SRC-101 (Section 3)
- Economic model (Section 4)
- Stamps Improvement Proposals / SIP governance (Section 5)
- Implementation guidelines (Section 6)
- Security analysis (Section 7)
- Future work and research directions (Section 8)

**Out of scope**: Wallet integration details, specific indexer implementations, user interface design, market dynamics. Focus is protocol specification for implementers.

## 1.6 Terminology

- **Stamp**: Non-fungible digital asset permanently stored in Bitcoin UTXO set via bare multisig or P2WSH encoding
- **SRC-20**: Fungible token standard atop stamps, using account-based balance tracking
- **UTXO set**: Set of all unspent transaction outputs in Bitcoin; consensus-critical data structure required for transaction validation
- **Account-based**: Asset ownership tracked per address (account balance) rather than per UTXO (UTXO-bound tokens)
- **Bare multisig**: Native Bitcoin multisig scripts used to encode data in fake pubkeys
- **P2WSH/OLGA**: Pay-to-Witness-Script-Hash outputs storing data in witness scripts (consensus-critical but weight-discounted)
- **Counterparty**: First Bitcoin metaprotocol (est. 2014); provides account-based asset model inherited by Bitcoin Stamps
- **Indexer**: Software parsing stamp transactions from Bitcoin blockchain, maintaining asset state database, serving API queries

---

**Next**: [Protocol Architecture →](./architecture.md)
