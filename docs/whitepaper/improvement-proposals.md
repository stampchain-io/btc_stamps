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

### 6.2.1 SIP-0001: Conditional Transfers

**GitHub Issue**: [#685](https://github.com/stampchain-io/btc_stamps/issues/685)

**Status**: Draft (as of 2026-02)

**Motivation**: Enable programmable token transfers with conditions evaluated by indexers. Supports DeFi primitives (escrows, swaps, vesting) without modifying Bitcoin consensus.

**Technical Design**:
```json
{
  "p": "src-20",
  "op": "conditional_transfer",
  "tick": "KEVIN",
  "amt": "1000",
  "to": "bc1q...recipient",
  "conditions": {
    "unlock_height": 900000,
    "oracle_signature": "witness_required",
    "multisig_threshold": {"m": 2, "n": 3}
  }
}
```

**Use Cases**:
- **Time-locked transfers**: Tokens released at specific block height
- **Escrow services**: Third-party oracle signatures required for release
- **Atomic swaps**: Cross-asset exchange with cryptographic settlement
- **Vesting schedules**: Gradual token unlock over time

**Challenges**:
- Oracle trust assumptions (mitigated by multi-oracle schemes)
- Indexer validation complexity (requires condition evaluation logic)
- Backward compatibility (legacy indexers ignore conditional fields)

**Activation Timeline**: TBD pending community review and implementation testing.

### 6.2.2 SIP-0003: Cross-Chain Bridges

**GitHub Issue**: [#485](https://github.com/stampchain-io/btc_stamps/issues/485)

**Status**: Review (as of 2026-02)

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

### 6.2.4 SIP-0005: Binary Data Format

**GitHub Issue**: [#688](https://github.com/stampchain-io/btc_stamps/issues/688)

**Status**: Review (as of 2026-02)

**Motivation**: Replace JSON-encoded SRC-20 transactions with compact binary format. Reduce transaction size by 40-60%, lowering minting costs and increasing throughput.

**Format Specification**:
```
Binary SRC-20 Transfer:
[1 byte: version] [1 byte: op_code] [4 bytes: tick_id]
[8 bytes: amount] [32 bytes: to_address_hash]

Total: 46 bytes vs. ~120 bytes JSON equivalent
```

**Op Codes**:
- `0x01`: DEPLOY
- `0x02`: MINT
- `0x03`: TRANSFER
- `0x04`: CONDITIONAL_TRANSFER (SIP-0001)

**Encoding Rules**:
- **Variable-length integers**: Smaller amounts use fewer bytes
- **Address compression**: Use hash instead of full Bech32 string
- **Tick identifiers**: Numeric IDs replace string tickers (lookup table)

**Benefits**:
- 40-60% size reduction → 40-60% cost savings
- Faster indexer parsing (binary vs JSON)
- Increased data density (more stamps per block)

**Migration Strategy**:
- Binary format optional after activation
- JSON format remains valid indefinitely
- Indexers must support both formats
- Wallets can choose format based on user preference

**Activation Timeline**: Pending final specification review (target Q2 2026).

## 6.3 Superseded SIPs

### 6.3.1 SIP-0002: Extended Counterparty Support

**GitHub Issue**: [#484](https://github.com/stampchain-io/btc_stamps/issues/484)

**Status**: Superseded

**Original Motivation**: Extend SRC-20 Counterparty support beyond block 796,000 to maintain backward compatibility with legacy Counterparty infrastructure.

**Rejection Rationale**:
- **Protocol independence**: Community consensus favored Bitcoin-native encoding over Counterparty dependency
- **Technical debt**: Maintaining dual validation paths (Counterparty + native) increased complexity
- **Security surface**: Counterparty protocol vulnerabilities could affect Stamps
- **Migration success**: Block 796,000 cutoff executed smoothly without significant user disruption

**Historical Context**: Early stamps (blocks 779,652 - 796,000) used Counterparty OP_RETURN encoding. SIP-0002 proposed continuing this approach, but community voted to enforce native encoding only after block 796,000.

**Superseded By**: Native Bitcoin encoding became mandatory. No SIP replacement needed—community consensus rejected the proposal.

**Lessons Learned**:
- Clean breaks preferred over indefinite backward compatibility
- Protocol independence increases long-term resilience
- Sufficient migration time (779,652 → 796,000) prevented ecosystem disruption

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
| **0001** | Conditional Transfers | Draft | [#685](https://github.com/stampchain-io/btc_stamps/issues/685) | TBD |
| **0002** | Extended Counterparty Support | Superseded | [#484](https://github.com/stampchain-io/btc_stamps/issues/484) | N/A (Rejected) |
| **0003** | Cross-Chain Bridges | Review | [#485](https://github.com/stampchain-io/btc_stamps/issues/485) | Q3 2026 (target) |
| **0004** | Privacy Enhancements | Draft | [#687](https://github.com/stampchain-io/btc_stamps/issues/687) | 2027 (target) |
| **0005** | Binary Data Format | Review | [#688](https://github.com/stampchain-io/btc_stamps/issues/688) | Q2 2026 (target) |

---

**References**:
- [Bitcoin Stamps GitHub Repository](https://github.com/stampchain-io/btc_stamps)
- [SIP Process Documentation](https://github.com/stampchain-io/btc_stamps/blob/main/SIPS.md)
- [Counterparty Improvement Proposals (CIPs)](https://github.com/CounterpartyXCP/cips) — Inspiration for SIP governance model

---

**Next**: [Implementation Details →](./implementation.md)
**Previous**: [← Economic Model](./economics.md)
