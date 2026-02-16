---
title: "Bitcoin Stamps Security Analysis"
description: "Immutability guarantees, attack vectors, and threat mitigations"
section: 8
prev: "./implementation.md"
next: "./future.md"
---

# 8. Security Analysis

## 8.1 Immutability Guarantees

Bitcoin Stamps' security model is fundamentally derived from its UTXO-based storage architecture. This section analyzes the threat model, attack vectors, and security properties inherited from Bitcoin.

### 8.1.1 UTXO Set Permanence

**Security Property**: Once a stamp transaction is confirmed in a Bitcoin block with sufficient depth, the embedded data is **effectively immutable** and **unprunable**.

**Mechanism**:
```
Stamp Transaction (Block N)
    ↓
Bitcoin Miners Confirm (6+ confirmations)
    ↓
UTXO Created (scriptPubKey contains stamp data)
    ↓
Full Nodes Store UTXO (required for validation)
    ↓
Data Persists (unprunable consensus-critical data)
```

**Proof-of-Work Protection**:
- To reverse a stamp (via blockchain reorganization), attacker must:
  1. Mine competing chain longer than confirmed depth
  2. Accumulate more proof-of-work than honest network
  3. Sustain 51% hashrate majority for extended period

**Cost Analysis** (6 confirmations = ~1 hour):
```python
# Attack cost to reverse 6-block-deep stamp (as of 2026)
network_hashrate = 600_000_000 TH/s  # ~600 exahash/s
block_reward = 3.125 BTC  # Post-2024 halving
btc_price = 60000  # USD

# Minimum cost to mine 7 blocks (replace 6 + extend by 1)
attack_cost = 7 * block_reward * btc_price
attack_cost = 7 * 3.125 * 60000 = $1,312,500 USD

# Reality: Requires acquiring 51% hashrate hardware (billions USD)
# Practical cost >> $1M due to hardware, electricity, opportunity cost
```

**Result**: Reversing confirmed stamps is economically infeasible for rational attackers.

### 8.1.2 UTXO vs Witness Data

**Critical Distinction**: Bitcoin Stamps store data in UTXO set, NOT witness data.

| Property | UTXO Set Data (Stamps) | Witness Data (Ordinals) |
|----------|------------------------|-------------------------|
| **Required for validation** | ✅ Yes (spending UTXO) | ❌ No (signature verification only) |
| **Prunable by nodes** | ❌ No (breaks validation) | ✅ Yes (after tx validation) |
| **Consensus-critical** | ✅ Yes | ⚠️ Partial (not for future txs) |
| **Archival dependency** | ❌ None (all full nodes) | ⚠️ Requires archival nodes |
| **Long-term permanence** | ✅ Guaranteed | ⚠️ Dependent on node policies |

**Security Implication**: Stamps data survives even if:
- Archival nodes stop operating
- Witness data is pruned by majority of nodes
- Protocol indexers cease operation

**Threat Scenario Analysis**:

*Scenario 1: Ordinals data loss*
```
Year 2035: Bitcoin Core default config prunes witness data after 1 year
→ Majority of nodes delete old Ordinals inscription data
→ Only archival nodes retain full witness history
→ If archival nodes shut down, inscription data is lost
→ Ordinals become unrecoverable
```

*Scenario 2: Stamps resilience*
```
Year 2035: Same pruning scenario
→ Stamps data is in UTXO set (unprunable)
→ All full nodes retain stamp data (required for validation)
→ No dependency on archival nodes
→ Stamps remain permanently accessible
```

### 8.1.3 UTXO Spending Risk

**Vulnerability**: If stamp-bearing UTXO is spent, data remains in blockchain history but exits active UTXO set.

**Mitigation**: Stamp protocol uses **economically unspendable UTXOs**:
```python
# Example stamp output
scriptPubKey: OP_1 <fake_pubkey_1> <fake_pubkey_2> <real_pubkey> OP_3 OP_CHECKMULTISIG
value: 546 satoshis  # Dust limit

# Spending cost analysis
input_size = 150 bytes  # Approx size to spend this UTXO
fee_rate = 20 sat/vByte  # Typical fee rate
spend_cost = 150 * 20 = 3000 satoshis

# Economic rationality
output_value = 546 sats
spend_cost = 3000 sats
net_loss = 2454 sats

# Conclusion: Economically irrational to spend (lose money)
```

**Result**: Stamp UTXOs are **economically unspendable** under normal fee markets, ensuring perpetual UTXO set residence.

**Exception**: During extremely low fee periods (<1 sat/vByte), spending may become economically viable. However:
- Most stamp creators use addresses without private keys (burn addresses)
- Community norm: Do not spend stamp UTXOs
- Even if spent, data remains in blockchain history (recoverable via archival indexing)

### 8.1.4 Consensus-Layer Protection

**Property**: Stamps inherit Bitcoin's Proof-of-Work security.

**Attack Resistance**:
1. **51% Attack**: Requires sustained majority hashrate control (>$10B hardware investment)
2. **Sybil Attack**: PoW makes creating fake blocks prohibitively expensive
3. **Eclipse Attack**: Does not affect confirmed stamp data (only network propagation)
4. **Censorship**: Miners can censor new stamps, but cannot erase confirmed ones

**Finality**: After ~6 confirmations (~1 hour), stamp data has same security as Bitcoin monetary transactions. No known attack can reverse deeply confirmed stamps without breaking Bitcoin itself.

## 8.2 Indexer Security Model

### 8.2.1 Trust Assumptions

**Centralization Risk**: Unlike Bitcoin's native consensus, stamp *validity* is determined by off-chain indexers.

**Trust Model**:
```
Bitcoin Layer: Trustless (PoW consensus)
    ↓ (data storage)
Stamp Data: Permanently stored (guaranteed)
    ↓ (interpretation)
Indexer Layer: Trust-minimized (open-source, multi-implementation)
    ↓ (presentation)
Application Layer: Varies (wallet/explorer trust)
```

**Key Insight**: Users must trust indexer *validation logic*, not data availability. Data is guaranteed by Bitcoin; only interpretation requires indexer trust.

### 8.2.2 Indexer Attack Vectors

**Attack 1: Malicious Indexer**

*Scenario*: Rogue indexer reports false balances.

```python
# Honest indexer
get_balance("bc1q...xyz", "KEVIN") → 1000 KEVIN

# Malicious indexer
get_balance("bc1q...xyz", "KEVIN") → 999999 KEVIN  # False balance
```

*Mitigation*:
1. **Multi-indexer verification**: Users query multiple independent indexers
2. **Open-source validation**: Anyone can verify balances by running own indexer
3. **Consensus checkpoints**: Community-verified state hashes at key blocks
4. **Reputation systems**: Wallets prioritize trusted indexers (stampchain.io, OpenStamps)

*Result*: Attack detected when balances diverge across indexers. Malicious indexer loses reputation; honest indexers remain authoritative.

**Attack 2: State Divergence Bug**

*Scenario*: Bug in indexer code causes state divergence across implementations.

```python
# Indexer A (buggy edge case handling)
process_transfer(amount="1000.00000001")  # Accepts fractional indivisible token
→ balance_A["KEVIN"] = 1000.00000001

# Indexer B (correct validation)
process_transfer(amount="1000.00000001")  # Rejects invalid transfer
→ balance_B["KEVIN"] = 1000
```

*Detection*:
```bash
# Community monitoring
curl https://stampchain.io/api/balance/bc1q...xyz → {"KEVIN": "1000.00000001"}
curl https://openstamps.io/api/balance/bc1q...xyz → {"KEVIN": "1000"}

# Divergence alert triggered
```

*Mitigation*:
1. **Consensus checkpoints**: Pre-computed state hashes at milestone blocks
2. **Test suites**: Comprehensive edge case testing
3. **Multi-language implementations**: Python, Rust, Go reduce likelihood of identical bugs
4. **Bug bounty programs**: Incentivize discovery and reporting

*Resolution*:
1. Freeze indexer state at divergence block
2. Debug session: Compare validation logs transaction-by-transaction
3. Identify root cause (usually edge case in validation logic)
4. Patch reference implementation
5. All indexers re-sync from divergence point
6. Community consensus on canonical state

**Attack 3: Eclipse Attack on Indexer**

*Scenario*: Attacker isolates indexer's Bitcoin node, feeds fake blocks.

```
Attacker → Fake Bitcoin blocks → Isolated indexer node → False stamp state
```

*Mitigation*:
1. **Multiple Bitcoin node connections**: Indexer connects to diverse nodes
2. **Checkpoint validation**: Verify block hashes match known checkpoints
3. **Network diversity**: Connect to nodes across different ISPs, geolocations
4. **Block header verification**: Validate cumulative PoW matches expected difficulty

*Result*: Isolated indexer detects anomaly (PoW mismatch, checkpoint failure) and alerts operator.

### 8.2.3 Data Availability

**Property**: Stamp data is available as long as Bitcoin network operates.

**Availability Guarantees**:
1. **Full Nodes**: ~50,000 Bitcoin full nodes globally store UTXO set
2. **Geographic Distribution**: Nodes across 100+ countries
3. **Independent Operators**: Diverse node operators (mining pools, exchanges, enthusiasts)
4. **Redundancy**: Single node failure has no impact (1000s of backups)

**Failure Scenario Analysis**:

*Scenario: All indexers shut down*
```
→ Stamp data remains in Bitcoin UTXO set (unchanged)
→ Any party can launch new indexer, sync from genesis
→ Asset balances reconstructible from blockchain
→ Protocol continues functioning (trustless recovery)
```

*Scenario: Catastrophic Bitcoin network failure*
```
→ If Bitcoin dies, stamps die with it (accepted risk)
→ No protocol can survive underlying blockchain failure
→ Stamps permanence = Bitcoin permanence (aligned incentives)
```

## 8.3 Protocol-Specific Vulnerabilities

### 8.3.1 Front-Running Attacks

**Vulnerability**: Attacker observes pending stamp transaction (mempool), submits higher-fee competing transaction.

*Example*:
```
Alice broadcasts: MINT 1000 KEVIN (fee: 10 sat/vByte)
    ↓ (mempool)
Bob observes transaction, broadcasts: MINT 1000 KEVIN (fee: 50 sat/vByte)
    ↓ (next block)
Bob's transaction confirms first → Bob receives KEVIN
Alice's transaction confirms second → Alice receives nothing (max supply reached)
```

**Mitigation**:
1. **Privacy**: Use private transaction relay (direct miner submission)
2. **High fees**: Pay competitive fee rate to discourage front-running
3. **MEV-resistance**: SRC-20 minting is first-come-first-served (no extractable value in ordering)
4. **Batch minting**: Deploy + mint in same transaction (atomic operation)

**Limitation**: Front-running is inherent to public mempool. Complete mitigation requires private mempools (availability/centralization tradeoff).

### 8.3.2 Replay Attacks

**Vulnerability**: Reuse of stamp transaction on chain forks (e.g., contentious hard fork).

*Scenario*:
```
Bitcoin forks into Chain A and Chain B
Alice's stamp transaction valid on both chains
→ Stamp created on Chain A
→ Same stamp replayed on Chain B (unintended duplication)
```

**Mitigation**:
1. **Chain-specific indexers**: Community designates canonical chain (longest PoW)
2. **Replay protection**: Future SIPs may include chain ID in transactions
3. **Economic disincentive**: Forked chains typically have low value (no incentive to replay)

**Historical Example**: Bitcoin Cash (2017) and Bitcoin SV (2018) forks had separate Counterparty ecosystems. No significant stamp replay issues due to community consensus on Bitcoin mainnet.

### 8.3.3 Ticker Squatting

**Vulnerability**: Malicious actor deploys popular ticker before legitimate project.

*Example*:
```
Attacker deploys "STAMP" token (malicious)
    ↓ (1 month later)
Legitimate STAMP project launches
    ↓ (ticker already taken)
Legitimate project must use alternative ticker ("STAMP2", "STMP")
```

**Mitigation**:
1. **First-come-first-served**: Protocol design accepts ticker squatting as valid
2. **Community curation**: Indexers/wallets flag known malicious tickers
3. **Metadata verification**: Users verify deploy block, deployer address
4. **Naming services**: SRC-101 enables human-readable names (alternative to tickers)
5. **Social consensus**: Community recognizes legitimate projects regardless of ticker

**Accepted Risk**: Bitcoin Stamps follows permissionless ethos—anyone can deploy any ticker. Scam prevention is social/application layer responsibility, not protocol enforcement.

### 8.3.4 Dust Attack

**Vulnerability**: Attacker sends tiny stamp token amounts to many addresses, tracking UTXO linkage.

*Example*:
```
Attacker sends 0.00000001 KEVIN to 10,000 addresses
    ↓
Tracks which addresses consolidate UTXOs (reveals address clustering)
    ↓
Deanonymizes user identity via address linkage
```

**Mitigation**:
1. **Ignore dust**: Wallets can hide balances below threshold
2. **Coin control**: Users avoid consolidating dust with main balance
3. **Privacy protocols**: SIP-0004 (confidential transfers) breaks linkage
4. **CoinJoin integration**: Mix UTXOs before consolidation

**Limitation**: Account-based model means dust tokens don't create on-chain linkage (no UTXOs to track). Dust attack less effective against stamps than UTXO-based tokens.

## 8.4 Attack Cost Analysis

### 8.4.1 Stamp Reversal Attack

**Goal**: Delete or modify confirmed stamp data.

**Required Attack**: 51% attack on Bitcoin network.

**Cost** (as of 2026):
```python
# Current Bitcoin hashrate
total_hashrate = 600_000_000 TH/s  # 600 exahash/s

# To achieve 51% majority
required_hashrate = 600_000_000 * 0.51 / 0.49 = 624_489_796 TH/s

# Hardware cost (Antminer S19 XP: 140 TH/s, $5000 each)
miners_needed = 624_489_796 / 140 = 4,460,641 miners
hardware_cost = 4,460,641 * 5000 = $22,303,205,000 (~$22 billion USD)

# Operational cost (electricity: $0.05/kWh, 3.25 kW per miner)
daily_power_cost = 4,460,641 * 3.25 * 24 * 0.05 = $17,344,000/day

# Attack duration to reverse 6-deep stamp
attack_duration = 1 hour (mine 7 blocks)
attack_cost = $22.3B (hardware) + $720k (electricity) ≈ $22.3 billion

# Opportunity cost (forgoing legitimate mining revenue)
blocks_mined = 7
revenue_lost = 7 * 3.125 BTC * $60,000 = $1,312,500
```

**Total Attack Cost**: ~$22 billion USD (hardware) + ongoing electricity + lost revenue.

**Conclusion**: Economically irrational for all but nation-state attackers. Stamp data is secured by Bitcoin's cumulative PoW.

### 8.4.2 Indexer Manipulation Attack

**Goal**: Trick users into accepting false stamp balances.

**Attack Vector**: Operate malicious indexer reporting inflated balances.

**Cost**: ~$10,000 (server costs) + development time.

**Mitigation Cost**: $0 (users query multiple indexers for free).

**Success Probability**: Near zero (users detect divergence across indexers).

**Conclusion**: Low-cost attack with negligible success probability. Not economically viable.

### 8.4.3 Ticker Squatting Attack

**Goal**: Profit from squatting popular tickers before legitimate projects.

**Cost**: ~$50-$500 per ticker (deploy transaction fee).

**Potential Profit**: Speculative (reselling ticker to project, or scam exit).

**Mitigation**: Community curation, wallet warnings, metadata verification.

**Conclusion**: Low-cost nuisance attack. Profitable only if users fail to verify legitimacy. Social layer mitigation effective.

## 8.5 Threat Model Summary

### 8.5.1 Security Hierarchy

**Layer 1: Bitcoin Consensus (Trustless)**
- ✅ Stamp data permanence guaranteed by PoW
- ✅ Reversal requires >$20B attack (infeasible)
- ✅ Data availability as long as Bitcoin operates

**Layer 2: Indexer Validation (Trust-Minimized)**
- ⚠️ Requires trust in indexer validation logic
- ✅ Mitigated by multi-indexer consensus
- ✅ Open-source, verifiable by anyone
- ⚠️ State divergence bugs possible (rare, detectable, fixable)

**Layer 3: Application Layer (Trust-Dependent)**
- ⚠️ Wallets/explorers may report false data
- ⚠️ Users must verify application integrity
- ✅ Mitigated by using reputable services

### 8.5.2 Risk Matrix

| Threat | Likelihood | Impact | Mitigation | Residual Risk |
|--------|-----------|--------|------------|---------------|
| **51% attack** | Very Low | Critical | Bitcoin PoW | Negligible |
| **UTXO pruning** | None | N/A | Consensus-critical storage | None |
| **Indexer bug** | Low | Medium | Multi-indexer consensus | Low |
| **Malicious indexer** | Medium | Low | User verification | Very Low |
| **Front-running** | Medium | Low | Privacy tools | Medium |
| **Ticker squatting** | High | Low | Social consensus | Low |
| **Replay attack** | Very Low | Low | Chain consensus | Very Low |

### 8.5.3 Security Recommendations

**For Users**:
1. **Verify balances across multiple indexers** (stampchain.io, OpenStamps)
2. **Use reputable wallets** with established track record
3. **Check deploy metadata** (block height, deployer address) before transacting
4. **Run own indexer** for maximum trustlessness (advanced users)

**For Developers**:
1. **Implement multi-indexer queries** in applications
2. **Display divergence warnings** if indexers disagree
3. **Validate consensus checkpoints** during indexer sync
4. **Contribute to test suites** for edge case coverage

**For Indexer Operators**:
1. **Connect to diverse Bitcoin nodes** (prevent eclipse attacks)
2. **Verify consensus checkpoints** at milestone blocks
3. **Publish state hashes** for community verification
4. **Run comprehensive test suites** before deploying updates

## 8.6 Comparison with Other Protocols

### 8.6.1 Bitcoin Stamps vs Ordinals

| Security Property | Bitcoin Stamps | Ordinals (Inscriptions) |
|------------------|----------------|-------------------------|
| **Data permanence** | ✅ Guaranteed (UTXO set) | ⚠️ Dependent (witness pruning) |
| **Consensus enforcement** | ❌ Indexer-based | ❌ Indexer-based |
| **Pruning risk** | ✅ None | ⚠️ Possible (witness data) |
| **51% attack protection** | ✅ Full Bitcoin PoW | ✅ Full Bitcoin PoW |
| **Archival dependency** | ✅ None (full nodes sufficient) | ⚠️ Requires archival nodes |
| **Long-term guarantee** | ✅ As long as Bitcoin exists | ⚠️ Depends on node policies |

### 8.6.2 Bitcoin Stamps vs Counterparty

| Security Property | Bitcoin Stamps | Counterparty |
|------------------|----------------|--------------|
| **Data storage** | ✅ UTXO set (multisig/P2WSH) | ⚠️ OP_RETURN (80 bytes, prunable) |
| **Asset model** | ✅ Account-based (inherited) | ✅ Account-based |
| **Protocol maturity** | ⚠️ Young (est. 2023) | ✅ Mature (est. 2014) |
| **Indexer diversity** | ⚠️ Limited implementations | ✅ Multiple implementations |
| **Permanence guarantee** | ✅ UTXO-based | ⚠️ OP_RETURN (smaller, prunable) |

**Key Difference**: Counterparty uses 80-byte OP_RETURN outputs (provably unspendable, smaller data). Bitcoin Stamps use multisig/P2WSH for larger data and stronger permanence guarantees.

---

## 8.7 Future Security Considerations

### 8.7.1 Quantum Computing Threat

**Threat**: Quantum computers (Shor's algorithm) can break ECDSA signatures, potentially allowing theft of funds from known public keys.

**Impact on Stamps**:
- Stamp data permanence unaffected (data is public, not secret)
- UTXO spending risk if quantum attacker derives private keys
- Indexer validation logic unaffected (no cryptographic secrets)

**Mitigation**:
- Use burn addresses (no private key exists → quantum-proof)
- Future stamps may use quantum-resistant signatures (post-quantum cryptography)
- Bitcoin-level mitigation (soft fork to quantum-resistant signatures) protects all stamps

### 8.7.2 Bitcoin Protocol Changes

**Threat**: Future Bitcoin soft/hard forks may affect stamp permanence guarantees.

**Potential Risks**:
- UTXO set pruning mechanisms (BIP proposal: stateless validation)
- Changes to multisig or P2WSH validation rules
- Block size reductions affecting stamp relay

**Mitigation**:
- Community monitoring of Bitcoin Core development
- Participation in BIP discussions affecting data storage
- Fork contingency plans (maintain support for longest PoW chain)

### 8.7.3 Regulatory Challenges

**Threat**: Jurisdictions may ban stamp creation or indexing.

**Impact**:
- Stamp data remains on-chain (cannot be removed by regulation)
- Indexers may shut down in restricted jurisdictions
- Wallets may delist stamp functionality

**Mitigation**:
- Geographic indexer distribution (censorship-resistant)
- Open-source code enables permissionless operation
- Tor/VPN access to indexers in permissive jurisdictions
- Decentralized indexer networks (future research)

---

**References**:
- [Bitcoin Security Model](https://en.bitcoin.it/wiki/Weaknesses)
- [51% Attack Cost Analysis](https://www.crypto51.app/)
- [UTXO Set Research](https://research.mempool.space/utxo-set-report/)
- [Counterparty Security Model](https://counterparty.io/docs/protocol_specification/)
- [Ordinals vs Stamps Permanence Debate](https://bitcoinmagazine.com/technical/bitcoin-stamps-vs-ordinals-permanence)

---

**Next**: [Future Directions →](./future.md)
**Previous**: [← Implementation](./implementation.md)
