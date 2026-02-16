# 5. Economic Model

The Bitcoin Stamps protocol's economic model is fundamentally shaped by its design choice to store data in the UTXO set rather than witness data. This section analyzes the permanence guarantees, cost structures, and economic tradeoffs inherent to this architecture.

## 5.1 UTXO Set Permanence Guarantees

### Architectural Foundation

Bitcoin Stamps are stored directly in Bitcoin's Unspent Transaction Output (UTXO) set, which full nodes maintain in memory or indexed storage for efficient transaction validation. This contrasts with witness-data protocols (e.g., Ordinals) that leverage SegWit's discounted witness field for data inscription.

### Permanence Mechanism

**Unprunable by Design**: UTXO set entries cannot be pruned from full nodes without breaking consensus rules. While nodes can prune historical block data and witness information after verification, they must retain all unspent outputs to validate new transactions.

**Stamp UTXOs**: Once created, Stamp-bearing UTXOs are expected to remain unspent indefinitely, ensuring:
1. Data persists in the globally replicated UTXO set
2. No dependency on archival node policies
3. Immunity to pruning configurations

**Counterparty Integration**: Classic Stamps leverage Counterparty's bare multisig (P2MS) outputs, which chunk image data across multiple outputs. By avoiding OP_RETURN (limited to 80 bytes and prunable), Stamps achieve true immutability.

### Economic Implications of Permanence

**UTXO Set Bloat**: Every Stamp contributes to permanent UTXO set growth, imposing ongoing storage costs on all full nodes. As of 2026, the UTXO set exceeds 10GB, with protocols like Stamps representing a measurable fraction.

**Node Operation Costs**: Validators bear the cost of storing Stamp UTXOs perpetually, creating a commons dilemma where minters externalize storage costs to the network.

**Economic Finality**: Permanence ensures that Stamp data survives even catastrophic scenarios (e.g., protocol deprecation, indexer abandonment). The data exists independently of any external service.

## 5.2 Storage Format Evolution

### Bare Multisig (OP_MULTISIG)

**Original Format**: Early Stamps used Counterparty's bare multisig encoding:
- Base64-encode image binary
- Split encoded data into 33-byte chunks
- Embed chunks as fake public keys in multisig outputs (e.g., 1-of-3, 2-of-3)

**Size Limits**: Maximum 7KB per Stamp due to standard transaction size constraints.

**Weight Calculation**: Multisig data is stored in the base transaction block, counting as 4 weight units per byte under SegWit's accounting.

### P2WSH Migration

**Efficiency Gains**: Pay-to-Witness-Script-Hash (P2WSH) outputs store data in the witness field, which receives a 75% discount under SegWit rules:
- Base block data: 4 weight units per byte
- Witness data: 1 weight unit per byte

**Cost Reduction**: P2WSH-based Stamps pay ~25% of bare multisig fees for equivalent data size.

**Pruning Concern**: Witness data is technically prunable by nodes that don't serve historical blocks. However, archival nodes and blockchain explorers retain witness data, ensuring practical permanence.

**Stamps P2WSH Variant**: Stamps protocol adopted P2WSH for certain formats while maintaining UTXO set references, balancing cost efficiency with permanence goals.

### OLGA Encoding

**Breakthrough Optimization**: P2WSH encoding was enabled at block 833,000 (`CP_P2WSH_FEAT_BLOCK_START`), with the first SRC-20 OLGA transaction at block 865,000 (`BTC_SRC20_OLGA_BLOCK`). OLGA (Octet Linked Graphical Artifacts) eliminates Base64 encoding:

**Technical Innovation**:
- Stores raw binary data directly in transaction outputs
- Removes 33% overhead from Base64 conversion
- Achieves 50% transaction size reduction vs. OP_MULTISIG
- Reduces minting costs by 60-70%

**Size Expansion**: Maximum file size increased to 64KB, enabling higher-fidelity artwork and larger datasets.

**Adoption**: OLGA became the standard for new Stamps due to dramatic cost savings without compromising immutability.

## 5.3 Miner Fee Economics

### Fee Market Competition

**Base Layer Fees**: Stamp minters compete in Bitcoin's fee market alongside financial transactions. During congestion (e.g., Ordinals inscription waves, halving periods), Stamp costs scale proportionally.

**Fee Rate Dynamics**:
- Low congestion: 1-5 sat/vByte (Stamps cost $0.50-$5 per KB)
- Medium congestion: 20-50 sat/vByte (Stamps cost $10-$30 per KB)
- High congestion: 100-500 sat/vByte (Stamps cost $60-$300 per KB)

**Batching Economies**: Minting multiple Stamps in a single transaction amortizes overhead:
- Single Stamp: ~300 bytes overhead + data
- 10 Stamps: ~300 bytes overhead + (10 × data), reducing per-Stamp cost

### Cost Structure Analysis

**Per-Stamp Breakdown** (OLGA format, 5KB image, 20 sat/vByte):

| Component | Size | Cost |
|-----------|------|------|
| Transaction overhead | 150 bytes | 3,000 sats |
| OLGA data (5KB) | 5,000 bytes | 100,000 sats |
| Output creation | 50 bytes | 1,000 sats |
| **Total** | **5,200 bytes** | **~104,000 sats (~$62 @ $60K BTC)** |

**Comparative Costs**:
- Ordinals inscription (5KB): ~26,000 sats (~$16) — 75% cheaper due to witness discount
- Classic Stamp (Base64): ~180,000 sats (~$108) — 73% more expensive due to encoding overhead
- OLGA Stamp: ~104,000 sats (~$62) — balanced cost-permanence tradeoff

### Miner Revenue Impact

**Protocol Contribution**: During 2023-2024 inscription waves, data-heavy protocols contributed 5-15% of miner fee revenue, with Stamps representing a smaller but consistent fraction.

**Incentive Alignment**: Stamp minters directly compensate miners for permanent block space allocation, aligning economic incentives without protocol subsidies.

## 5.4 Storage Cost Comparison

### Bitcoin Stamps vs. Ordinals

| Attribute | Bitcoin Stamps | Ordinals (Inscriptions) |
|-----------|----------------|-------------------------|
| **Storage Location** | UTXO set (base block data or P2WSH witness) | Witness data (SegWit) |
| **Prunability** | Unprunable (UTXO set) | Technically prunable (witness) |
| **Cost Multiplier** | 4x (OP_MULTISIG) to 1x (P2WSH OLGA) | 1x (witness discount) |
| **Size Limit** | 64KB (OLGA), 7KB (legacy) | ~400KB (block size constraints) |
| **Node Impact** | Perpetual UTXO set growth | Witness data pruning reduces impact |
| **Economic Model** | Minter pays permanent externality | Minter pays discounted temporary cost |

### UTXO Set Growth Implications

**Long-Term Costs**: As of 2026, storing 1GB of UTXO data costs validators:
- SSD storage: ~$0.10/GB/year
- RAM caching (performance nodes): ~$5/GB/year

**Scaling Concerns**: If Stamps adoption scales to 100GB UTXO footprint, validators face:
- $10/year storage costs (SSD)
- $500/year RAM costs (high-performance nodes)

These costs are externalized to the network, raising debate over sustainable protocol economics.

### Alternative Protocols

**IPFS + Bitcoin Anchoring**: Store data off-chain (IPFS), anchor hashes on Bitcoin:
- Cost: ~200 bytes per anchor (~$2 at 20 sat/vByte)
- Tradeoff: Requires IPFS network availability; not truly immutable

**Arweave + Bitcoin Verification**: Permanent storage layer with Bitcoin proof references:
- Cost: ~$5-$10 per MB on Arweave
- Tradeoff: Dependency on Arweave network; cross-chain trust assumptions

**Stamps Advantage**: True Bitcoin-native permanence without external dependencies, at the cost of higher fees and UTXO set impact.

## 5.5 Economic Sustainability

### Protocol Fee Structure

**No Native Fees**: Stamps protocol itself collects no fees. All costs are miner fees paid to Bitcoin validators.

**Token Economics** (SRC-20/721/101):
- **Deploy Fees**: Set by deployer; collected in satoshis by minting smart contracts or indexer-enforced logic
- **Royalties**: Not enforced at protocol level; marketplace-dependent
- **Renewal Fees** (SRC-101): Deployer-set pricing for domain lease extensions

### Miner Incentive Alignment

**Short-Term**: Stamps generate direct fee revenue for miners, incentivizing block inclusion during low-congestion periods.

**Long-Term**: UTXO set growth imposes costs on future miners/validators. If externalized costs exceed fee revenue, validators may advocate for protocol-level restrictions.

### Market-Driven Equilibrium

**Fee Market Regulation**: High congestion naturally limits Stamp creation as costs rise, creating self-regulating supply dynamics.

**Quality vs. Quantity**: Expensive minting favors high-value assets (rare art, critical data) over spam, improving signal-to-noise ratio.

**Indexer Sustainability**: Open-source indexer model ensures community-driven validation without centralized service dependencies. Multiple independent indexers can verify state, preventing single points of failure.

## 5.6 Economic Tradeoffs Summary

### Advantages

1. **True Immutability**: UTXO-based storage guarantees permanence without reliance on archival nodes
2. **Censorship Resistance**: Data survives even if protocol indexers cease operation
3. **Bitcoin-Native Security**: Inherits full Proof-of-Work consensus guarantees
4. **No Auxiliary Dependencies**: Only Bitcoin miner fees required; no token burns or external fees

### Disadvantages

1. **High Costs**: 1-4x more expensive than witness-based alternatives
2. **UTXO Set Externality**: Imposes permanent storage costs on all validators
3. **Scaling Constraints**: Limited to ~64KB per asset (OLGA), vs. 400KB for Ordinals
4. **Fee Market Competition**: Vulnerable to congestion-driven cost spikes

### Strategic Positioning

Bitcoin Stamps occupies the "maximum permanence" niche within Bitcoin's data inscription ecosystem. Users willing to pay premium costs for uncompromising immutability choose Stamps over cheaper, less permanent alternatives. This positions the protocol as a premium store-of-value layer for digital artifacts requiring absolute permanence guarantees.

---

## 5.7 Future Economic Considerations

### UTXO Set Management Proposals

**Spent Output Archiving**: Future Bitcoin soft forks may introduce mechanisms to archive spent outputs while maintaining cryptographic proofs, potentially affecting Stamp permanence.

**Fee Policy Changes**: BIP proposals targeting data-heavy transactions could introduce additional costs or restrictions on multisig/P2WSH data embedding.

**Stamps Adaptation**: Protocol must monitor Bitcoin Core development to ensure continued viability under potential consensus rule changes.

### Layer 2 Integration

**Lightning Network**: Stamps could leverage LN for microtransactions involving SRC-20 tokens, though atomic swaps face account-based model challenges.

**Sidechains**: Federated sidechains (e.g., Liquid) may support Stamps-compatible standards with different cost structures.

**Rollups**: Bitcoin rollup proposals (e.g., BitVM) could enable Stamps-like permanence at reduced on-chain footprint.

### Competitive Landscape Evolution

As Bitcoin's data inscription ecosystem matures, protocols will differentiate along cost-permanence-functionality axes. Stamps' commitment to UTXO-based immutability positions it as the "gold standard" for applications where permanence justifies premium costs—archival NFTs, legal records, decentralized identity systems, and foundational digital artifacts.

---

**References**:

- [Bitcoin UTXO Set Research](https://research.mempool.space/utxo-set-report/)
- [SegWit Witness Discount Analysis](https://bitcoinmagazine.com/technical/the-witness-discount-why-some-bytes-are-cheaper-than-others)
- [Bitcoin Stamps vs Ordinals Permanence Analysis](https://coinpedia.org/guest-post/bitcoin-stamps-vs-ordinals-deep-dive-into-future-of-on-chain-permanence/)
- [Economically Unspendable Bitcoin UTXOs](https://blog.lopp.net/economically-unspendable-bitcoin-utxos/)
- [Bitcoin Core SegWit Costs and Risks](https://bitcoincore.org/en/2016/10/28/segwit-costs/)
- [Bitcoin Stamps FAQ](https://stampchain.io/faq)
