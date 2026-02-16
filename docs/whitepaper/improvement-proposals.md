---
title: "Bitcoin Stamps Improvement Proposals (SIPs)"
description: "Protocol governance model and active improvement proposals"
section: 6
prev: "./economics.md"
next: "./implementation.md"
---

# 6. Stamps Improvement Proposals (SIPs)

## 6.1 SIP Governance Framework

Bitcoin Stamps protocol evolves through community-driven Stamps Improvement Proposals (SIPs). This governance model balances protocol stability with extensibility, enabling vetted enhancements while preserving core immutability guarantees.

### 6.1.1 SIP Lifecycle

**Draft**: Proposal submitted as GitHub Issue with specification outline. Author presents motivation, technical design, and backward compatibility analysis.

**Review**: Community discussion period (minimum 14 days). Technical reviewers evaluate:
- Specification clarity and completeness
- Implementation feasibility
- Security implications
- Impact on existing stamps and indexers
- Alignment with protocol philosophy

**Accepted**: Proposal achieves rough consensus among core developers and major indexer implementations. Specification finalized with version number (SIP-XXXX).

**Activated**: Implementation deployed with activation block height set 4+ weeks in future. Advance notice ensures all indexers, wallets, and services update before consensus rule changes take effect.

**Final**: Activation block height reached. New rules enforced by all compliant indexers. Proposal becomes immutable specification.

**Superseded**: Later SIP replaces or invalidates earlier proposal. Original SIP remains in historical record but no longer active.

### 6.1.2 Activation Lead Time

**Critical Safety Mechanism**: All consensus-changing SIPs must specify activation block height at least **4 weeks (approximately 4,032 blocks)** after acceptance.

**Rationale**:
- Indexer operators need time to upgrade software
- Wallet developers must integrate new transaction formats
- Service providers require testing and deployment cycles
- Community members must understand changes before activation

**Historical Precedent**: Block 796,000 (SRC-20 Counterparty cutoff) and block 865,000 (OLGA activation) both provided multi-week advance notice, ensuring smooth transitions without network disruption.

### 6.1.3 Consensus Requirements

**Indexer Consensus**: Bitcoin Stamps has no on-chain consensus mechanism. Protocol rules are enforced by indexer implementations. SIP activation requires:
- **Reference Indexer**: stampchain.io (official implementation) must deploy support
- **Secondary Indexers**: At least 2 independent implementations demonstrate compatibility
- **Community Signaling**: No significant objections from major stakeholders

**Backward Compatibility**: SIPs should maintain compatibility with existing stamps whenever possible. Breaking changes require strong justification and comprehensive migration path.

### 6.1.4 GitHub Issue Tracking

All SIPs are tracked as GitHub Issues in the Bitcoin Stamps repository:
- **Repository**: https://github.com/stampchain-io/btc_stamps
- **Issue Labels**: `SIP`, `enhancement`, `consensus-change`
- **Discussion Forum**: GitHub Discussions for preliminary ideas before formal SIP submission

## 6.2 Active SIPs

### 6.2.1 SIP-0001: SRC-20 HTLC (Hash Time-Locked Contracts)

**GitHub Issue**: [#685](https://github.com/stampchain-io/btc_stamps/issues/685)

**Status**: Draft (as of 2026-02)

**Motivation**: Enable trustless atomic swaps and escrow services for SRC-20 tokens through hash time-locked contracts. Supports cross-asset exchanges and conditional transfers without requiring external oracles or modifying Bitcoin consensus.

**Technical Design**:

SIP-0001 introduces three new SRC-20 operations:

**1. `conditional_transfer` — Create HTLC with hashlock and/or timelock**:
```json
{
  "p": "src-20",
  "op": "conditional_transfer",
  "tick": "KEVIN",
  "amt": "1000",
  "to": "bc1q...recipient",
  "hashlock": "a4b9c8d7e6f5...sha256hash",
  "timelock": 900000
}
```
- **hashlock** (optional): SHA-256 hash — recipient must reveal preimage to claim
- **timelock** (optional): Block height — sender can refund after this block if unclaimed
- At least one of hashlock/timelock required
- Tokens deducted from sender immediately, held in indexer escrow state

**2. `claim` — Recipient claims tokens with preimage**:
```json
{
  "p": "src-20",
  "op": "claim",
  "tick": "KEVIN",
  "transfer_tx": "abc123...original_txid",
  "preimage": "secret_value"
}
```
- Indexer verifies `SHA-256(preimage)` matches hashlock
- Must be before timelock block height (if timelock set)
- Tokens credited to recipient

**3. `refund` — Sender reclaims tokens after timelock expires**:
```json
{
  "p": "src-20",
  "op": "refund",
  "tick": "KEVIN",
  "transfer_tx": "abc123...original_txid"
}
```
- Only valid after timelock block height reached
- Tokens returned to original sender

**Use Cases**:
- **Atomic swaps**: Cross-asset exchange (e.g., KEVIN ↔ STAMP) with cryptographic settlement
- **Escrow services**: Time-locked deposits with refund guarantees
- **Trustless bridge deposits**: Lock tokens with hashlock, mint on L2 with preimage reveal (see SIP-0003)
- **Time-locked vesting**: Gradual token unlock over time

**Challenges**:
- **Liveness requirement**: Both parties must be online during swap window
- **Timelock griefing**: Malicious actors can lock counterparty funds then abandon swap
- **Multi-step process**: Atomic swap requires 4 transactions (2 conditional_transfer + 2 claim)
- **Indexer validation complexity**: Requires SHA-256 verification and timelock enforcement

**Activation Timeline**: TBD pending community review and implementation testing.

### 6.2.2 SIP-0003: Cross-Chain Bridges

**GitHub Issue**: [#485](https://github.com/stampchain-io/btc_stamps/issues/485)

**Status**: Draft (as of 2026-02)

**Motivation**: Enable SRC-20 token movement between Bitcoin mainnet and Layer 2 protocols (Lightning Network, sidechains, rollups) while maintaining UTXO-based permanence guarantees for bridged asset records.

**Architecture**:
```
Bitcoin L1 (Stamps)  ←→  Bridge Contract  ←→  L2 Protocol
     |                        |                      |
  Lock asset          Mint wrapped token       Fast transfers
  (UTXO proof)        (bridge attestation)     (off-chain)
```

**Bridge Operations**:

1. **Lock** (L1 → L2):
   - User sends SRC-20 transfer to bridge address
   - Bridge operators verify transaction and UTXO proof
   - L2 mints equivalent wrapped token to user address

2. **Unlock** (L2 → L1):
   - User burns wrapped token on L2
   - Bridge operators create SRC-20 transfer from bridge address to user
   - Bitcoin transaction permanently records bridge event

**Security Model**:
- **Federated multisig**: M-of-N bridge operators hold Bitcoin keys
- **Fraud proofs**: Users can challenge invalid bridge operations
- **Timelock withdrawals**: Delay allows dispute resolution

**Implementation Requirements**:
- Bridge indexer module for cross-chain state verification
- Oracle network for L2 state attestation
- Emergency pause mechanism for security incidents

**Activation Timeline**: Pending security audit and testnet deployment (target Q3 2026).

### 6.2.3 SIP-0004: Privacy Enhancements

**GitHub Issue**: [#687](https://github.com/stampchain-io/btc_stamps/issues/687)

**Status**: Draft (as of 2026-02)

**Motivation**: Improve SRC-20 transfer privacy through cryptographic commitments while maintaining indexer verifiability. Address concern that account-based model exposes address balances publicly.

**Privacy Techniques**:

**1. Confidential Amounts**:
```python
# Pedersen commitments hide transfer amounts
commitment = amount * G + blinding_factor * H
# Indexer verifies: commitment_in == commitment_out (balance preserved)
# Amount remains hidden from public queries
```

**2. Stealth Addresses**:
```python
# One-time address per transfer
stealth_addr = hash(sender_secret + recipient_pubkey)
# Only recipient can detect and claim transfer
# Breaks on-chain address linkage
```

**3. Range Proofs**:
```python
# Prove amount is positive without revealing value
prove(0 < amount < max_supply)
# Prevents negative balance attacks
# Maintains confidentiality
```

**Tradeoffs**:
- **Proof size**: Range proofs add 1-2KB per transfer (higher fees)
- **Validation cost**: Indexers must verify cryptographic proofs (slower sync)
- **Regulatory risk**: Privacy features may face jurisdictional challenges
- **Complexity**: Wallet implementations require cryptographic libraries

**Phased Rollout**:
- **Phase 1**: Optional confidential amounts for willing users
- **Phase 2**: Stealth address support in major wallets
- **Phase 3**: Full privacy by default with opt-out mechanism

**Activation Timeline**: Specification under development (target 2027).

### 6.2.4 SIP-0005: Binary Transfer Format for SRC-20

**GitHub Issue**: [#688](https://github.com/stampchain-io/btc_stamps/issues/688)

**Status**: Draft (as of 2026-02)

**Motivation**: Replace JSON-encoded SRC-20 transactions with compact binary format. Reduce transaction size by approximately 63%, lowering minting costs and increasing throughput.

**Format Specification**:
```
Binary SRC-20 Transfer Format (44 bytes total):
<prefix:6><version:1><op:1><tick:20><amount:8><decimals:8> = 44 bytes raw
```

**Field Breakdown**:
- **prefix** (6 bytes): `stamp:` — indexer detection marker (ASCII: `73 74 61 6D 70 3A`)
- **version** (1 byte): `0x01` for format version 1
- **op** (1 byte): Operation code
  - `0x01`: DEPLOY
  - `0x02`: MINT
  - `0x03`: TRANSFER
- **tick** (20 bytes): UTF-8 ticker padded with null bytes
  - Example: "KEVIN" → `4B 45 56 49 4E` + 15 null bytes (`0x00`)
- **amount** (8 bytes): uint64 big-endian raw amount (not decimal-adjusted)
- **decimals** (8 bytes): uint64 big-endian decimal precision

**Detection Logic**:
```python
if data[:6] == b'stamp:' and data[6] == 0x01:
    # Binary format
    parse_binary(data)
else:
    # JSON format (backward compatible)
    parse_json(data)
```

**Benefits**:
- **~63% size reduction**: 44 bytes binary vs ~120 bytes JSON
- **Faster indexer parsing**: Binary deserialization vs JSON parsing
- **Lower transaction fees**: Smaller data size reduces on-chain costs
- **Increased data density**: More stamps per block

**Migration Strategy**:
- Binary format optional after activation
- JSON format remains valid indefinitely (backward compatibility)
- Indexers must support both formats simultaneously
- Wallets can choose format based on user preference

**Activation Timeline**: TBD pending final specification review.

### 6.2.5 SIP-0006: Native SRC-20 AMM (Automated Market Maker)

**GitHub Issue**: [#689](https://github.com/stampchain-io/btc_stamps/issues/689)

**Status**: Draft (as of 2026-02)

**Motivation**: Enable trustless on-chain token swaps without order books or centralized exchanges. The account-based SRC-20 model is ideal for AMM implementation since balance updates are atomic indexer operations, eliminating UTXO coordination complexity.

**Technical Design**:

SIP-0006 introduces four new SRC-20 operations for constant product market maker (Uniswap V2-style):

**1. `create_pool` — Deploy new liquidity pool**:
```json
{
  "p": "src-20",
  "op": "create_pool",
  "tick_a": "KEVIN",
  "tick_b": "STAMP",
  "fee_tier": 30
}
```
- **fee_tier**: Fee in basis points (10 = 0.1%, 30 = 0.3%, 100 = 1.0%)
- Creates LP token with tick: `LP:KEVIN/STAMP`

**2. `add_liquidity` — Deposit token pair to pool**:
```json
{
  "p": "src-20",
  "op": "add_liquidity",
  "pool": "LP:KEVIN/STAMP",
  "amt_a": "1000",
  "amt_b": "5000"
}
```
- Deposits proportional to current pool ratio
- Mints LP tokens to liquidity provider
- LP tokens are standard SRC-20 (transferable, tradeable)

**3. `remove_liquidity` — Withdraw from pool**:
```json
{
  "p": "src-20",
  "op": "remove_liquidity",
  "pool": "LP:KEVIN/STAMP",
  "lp_amt": "500"
}
```
- Burns LP tokens
- Returns proportional share of pool reserves

**4. `swap` — Exchange tokens**:
```json
{
  "p": "src-20",
  "op": "swap",
  "pool": "LP:KEVIN/STAMP",
  "from_tick": "KEVIN",
  "amt_in": "100"
}
```

**Swap Pricing Formula (Constant Product)**:
```
amt_out = (reserve_out × amt_in_with_fee) / (reserve_in + amt_in_with_fee)

where:
  amt_in_with_fee = amt_in × (10000 - fee_bps)

Example (0.3% fee tier):
  amt_in_with_fee = 100 × (10000 - 30) / 10000 = 99.7
```

**LP Token Mechanics**:
- LP tokens are standard SRC-20 tokens with tick format `LP:{tick_a}/{tick_b}`
- Fully transferable between addresses
- Can be traded on secondary markets
- Mintable/burnable ONLY through AMM operations (add/remove liquidity)
- Represent proportional claim on pool reserves

**Phased Rollout**:
- **Phase 1**: SRC-20/SRC-20 pools (fully trustless, no external dependencies)
- **Phase 2**: wBTC pools (requires SIP-0007 wrapped asset standard)
- **Phase 3**: Stablecoin pools (requires SIP-0003 bridge for USDT/USDC)

**Benefits**:
- **Trustless**: No intermediaries, no custody risk
- **Permissionless**: Anyone can create pools or provide liquidity
- **Atomic operations**: Swaps execute in single indexer transaction
- **Capital efficient**: Liquidity providers earn fees on all trades

**Challenges**:
- **Impermanent loss**: Liquidity providers exposed to price divergence
- **MEV risk**: Indexer ordering can enable front-running (mitigated by transaction fee priority)
- **Pool fragmentation**: Multiple fee tiers for same pair splits liquidity

**Activation Timeline**: TBD pending community review and Phase 1 implementation.

### 6.2.6 SIP-0008: Dual Transaction Parsing — Combined SRC-20 Transfer + Stamp Issuance

**GitHub Issue**: [#692](https://github.com/stampchain-io/btc_stamps/issues/692) (originated from [#554](https://github.com/stampchain-io/btc_stamps/issues/554))

**Author**: DerpHerpenstein

**Status**: Draft

**Phase**: 1 (Foundation) | **Estimated Effort**: 2-3 weeks

**Motivation**: Currently, a single Bitcoin transaction can only perform one stamp operation — either issue a new stamp OR execute an SRC-20 transfer. Users who want to do both must create two separate transactions, paying double the fees. SIP-0008 enables a single transaction to contain both a stamp issuance and an SRC-20 transfer, reducing costs and enabling new composable workflows.

**Technical Design**:

The indexer currently processes each transaction for a single stamp operation. SIP-0008 extends the transaction parser to detect and process multiple stamp payloads within a single transaction:

```
Transaction outputs:
  Output 0: SRC-20 transfer payload (bare multisig or P2WSH)
  Output 1: Stamp image data (bare multisig or P2WSH)
  Output 2: Change output
```

**Parsing Rules**:
1. **Output scanning**: Indexer scans all outputs for stamp-compatible payloads
2. **Payload classification**: Each payload classified as SRC-20 operation or stamp issuance based on content type detection
3. **Ordered execution**: SRC-20 transfers processed before stamp issuance (deterministic ordering)
4. **Atomic processing**: Both operations succeed or both fail — no partial execution
5. **Backward compatibility**: Single-operation transactions continue to work unchanged

**Soft Dependency**: SIP-0005 (Binary Transfer Format) — binary encoding makes dual payloads more size-efficient, but SIP-0008 works with JSON encoding as well.

**Use Cases**:
- **Mint-and-transfer**: Create a stamp and immediately send SRC-20 tokens in one transaction
- **Composable workflows**: Agent-driven pipelines that batch stamp operations for efficiency
- **Fee optimization**: Single transaction fee instead of two for combined operations

**Activation Timeline**: TBD pending community review and Phase 1 implementation.

## 6.3 Superseded SIPs

### 6.3.1 SIP-0002: SRC-20 UTXO Binding & Transfer Format v2.0

**GitHub Issue**: [#484](https://github.com/stampchain-io/btc_stamps/issues/484)

**Status**: Superseded (by SIP-0001)

**Original Motivation**: Bind SRC-20 token balances to specific Bitcoin UTXOs to enable single-transaction PSBT-based atomic swaps without multi-step HTLC protocols.

**Proposed Design**:
```json
{
  "p": "src-20",
  "op": "bind_utxo",
  "tick": "KEVIN",
  "amt": "1000",
  "utxo": "txid:vout"
}
```
- Tokens would be locked to specific UTXO
- Spending the UTXO would automatically transfer bound tokens
- Enabled single-step atomic swaps via PSBT co-signing

**Rejection Rationale**:
- **Fundamental loss risk**: If user spends bound UTXO in normal Bitcoin transaction, SRC-20 tokens could be lost
  - Bitcoin consensus has no knowledge of SRC-20 state
  - Wallets cannot prevent accidental UTXO spending
  - Loss prevention is impossible without modifying Bitcoin protocol
- **Non-deterministic rescue operations**: Indexer "token recovery" would break consensus determinism
- **SIP-0001 provides superior solution**: HTLC covers all atomic swap use cases without loss risk
- **Complexity vs benefit**: UTXO coordination adds significant implementation burden for marginal UX improvement

**Superseded By**: SIP-0001 (HTLC) provides trustless atomic swaps without binding tokens to UTXOs, eliminating loss risk while maintaining full functionality.

**Lessons Learned**:
- Account-based models should not be forcibly bound to UTXO mechanics
- Protocol safety (loss prevention) outweighs UX convenience (single-step swaps)
- Multi-step protocols (HTLC) acceptable when they eliminate fundamental risks

## 6.4 SIP Process Best Practices

### 6.4.1 Proposal Template

**Title**: [SIP-XXXX] Brief descriptive title

**Author**: GitHub username / contact info

**Status**: Draft

**Type**: Standards Track / Informational / Process

**Created**: YYYY-MM-DD

**Sections**:
1. **Abstract**: One-paragraph summary
2. **Motivation**: Problem being solved, use cases
3. **Specification**: Technical design, data formats, validation rules
4. **Rationale**: Design decisions, alternatives considered
5. **Backward Compatibility**: Impact on existing stamps/indexers
6. **Test Cases**: Reference implementation tests
7. **Security Considerations**: Attack vectors, mitigations
8. **Activation**: Proposed block height, coordination plan

### 6.4.2 Review Criteria

**Technical Soundness**:
- Specification is complete and unambiguous
- Implementation is feasible with existing Bitcoin constraints
- No cryptographic or protocol vulnerabilities

**Protocol Alignment**:
- Preserves UTXO-based permanence guarantees
- Maintains account-based asset model
- Follows Bitcoin-native encoding principles
- Respects community governance values

**Ecosystem Impact**:
- Breaking changes justified and necessary
- Migration path documented for affected users
- Indexer implementation complexity is reasonable
- Wallet/service integration burden is acceptable

**Community Support**:
- Rough consensus among developers
- No strong objections from major stakeholders
- Clear demand from users and builders

### 6.4.3 Implementation Requirements

**Reference Implementation**: All accepted SIPs must include:
- Working code in stampchain.io indexer repository
- Comprehensive test suite with edge cases
- Documentation for indexer operators
- Example transactions on testnet

**Multi-Indexer Compatibility**: At least 2 independent indexer implementations must successfully validate SIP test cases before activation.

**Regression Testing**: New SIP implementations must pass full historical sync test (genesis block → current tip) without breaking existing stamp validation.

## 6.5 Open Research Areas

### 6.5.1 Zero-Knowledge Proofs

**Research Question**: Can zk-SNARKs enable private SRC-20 transfers with succinct on-chain proofs?

**Potential Benefits**:
- Strong privacy (ZCash-level confidentiality)
- Compact proofs (200-500 bytes regardless of transfer complexity)
- Trustless verification by indexers

**Challenges**:
- Trusted setup requirements (or STARK alternatives)
- Proof generation complexity for wallet implementations
- Validation performance impact on indexer sync speed

**Status**: Exploratory research; no formal SIP yet.

### 6.5.2 Recursive Stamps v2

**Research Question**: Can stamps reference external Bitcoin data (taproot scripts, DLCs) to enable advanced smart contracts?

**Potential Applications**:
- Stamps triggered by DLC oracle outcomes
- Integration with BitVM computation verification
- Lightning Network settlement to stamp ownership

**Challenges**:
- Cross-protocol coordination complexity
- Security assumptions for external data sources
- Indexer validation of external state

**Status**: Concept phase; community feedback sought.

### 6.5.3 Rollup Integration

**Research Question**: Can Bitcoin rollups (BitVM, Sovereign SDK) support Stamps-compatible assets with L1 permanence guarantees?

**Potential Architecture**:
- L2 transactions executed off-chain
- Periodic L1 commitment (Merkle root stamped on Bitcoin)
- L2 state reconstructible from L1 commitments

**Benefits**:
- High throughput (1000s of transfers per second)
- Low per-transfer cost (amortized L1 fees)
- Maintained UTXO permanence for rollup commitments

**Challenges**:
- Data availability (ensure L2 state accessible)
- Fraud proof mechanisms (dispute resolution)
- Indexer complexity (track both L1 and L2 state)

**Status**: Monitoring BitVM development; formal SIP pending rollup maturity.

---

## 6.6 SIP Summary Table

| SIP | Title | Status | GitHub | Target Activation |
|-----|-------|--------|--------|-------------------|
| **0001** | SRC-20 Conditional Transfers (HTLC) | Draft | [#685](https://github.com/stampchain-io/btc_stamps/issues/685) | TBD |
| **0002** | SRC-20 UTXO Binding & Transfer Format v2.0 | Superseded (by SIP-0001) | [#484](https://github.com/stampchain-io/btc_stamps/issues/484) | N/A |
| **0003** | SRC-20 Cross-Chain Bridge Specification | Draft | [#485](https://github.com/stampchain-io/btc_stamps/issues/485) | TBD |
| **0004** | Shielded SRC-20 — Privacy Extension | Draft | [#687](https://github.com/stampchain-io/btc_stamps/issues/687) | 2027+ (phased) |
| **0005** | Binary Transfer Format for SRC-20 | Draft | [#688](https://github.com/stampchain-io/btc_stamps/issues/688) | TBD |
| **0006** | Native SRC-20 AMM (Automated Market Maker) | Draft | [#689](https://github.com/stampchain-io/btc_stamps/issues/689) | TBD |
| **0008** | Dual Transaction Parsing | Draft | [#692](https://github.com/stampchain-io/btc_stamps/issues/692) | TBD |

---

**References**:
- [Bitcoin Stamps GitHub Repository](https://github.com/stampchain-io/btc_stamps)
- [SIP-0000: SIP Purpose and Guidelines](https://github.com/stampchain-io/btc_stamps/issues/686)
- [Counterparty Improvement Proposals (CIPs)](https://github.com/CounterpartyXCP/cips) — Inspiration for SIP governance model

---

**Next**: [Implementation Details →](./implementation.md)
**Previous**: [← Economic Model](./economics.md)
