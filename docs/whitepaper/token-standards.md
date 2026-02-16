# 4. Token Standards

The Bitcoin Stamps protocol supports three distinct token standards, each optimized for specific use cases while maintaining the core principle of UTXO-based immutability. All standards leverage Bitcoin's Proof-of-Work consensus mechanism, ensuring data integrity once confirmed.

## 4.1 SRC-20: Fungible Token Standard

### Overview

SRC-20 is an account-based fungible token protocol that enables fair, accessible token creation with only standard Bitcoin miner fees. Inspired by BRC-20 but designed with Stamps' immutability guarantees, SRC-20 operates directly on the Bitcoin blockchain without dependency on Counterparty since block 796,000.

**Critical Design Note**: SRC-20 is **account-based**. Balances are tracked per address in indexer state, NOT per UTXO. This distinguishes it from UTXO-based protocols where tokens are locked in specific transaction outputs.

### First Deployment

The KEVIN token, deployed by Arwyn at block 788,041, represents the genesis SRC-20 deployment.

### Transaction Structure

SRC-20 transactions follow standardized JSON encoding embedded in Bitcoin transaction outputs. Required fields include:

- `p`: Protocol identifier ("src-20")
- `op`: Operation type (deploy, mint, transfer)
- `tick`: Token ticker symbol
- Additional operation-specific parameters

### Operations

**DEPLOY**: Initializes a new token collection with supply limits, per-mint caps, and optional pricing.

**MINT**: Creates new token units within deployment constraints. Minting continues until max supply is reached.

**TRANSFER**: Moves tokens between addresses. The indexer validates sender balance before updating account states.

### Validation and Indexing

The indexer validates transactions through multi-step verification:

1. **Length Verification**: First two bytes represent expected decoded data length in hex
2. **JSON Validation**: Transaction must parse as valid JSON with required fields
3. **Balance Check**: For transfers, sender must hold sufficient balance
4. **State Update**: Successful transactions update the account-based balance ledger

Invalid transactions receive no stamp number and do not affect user balances. The Rust-based parser provides 20-50x performance improvement over pure Python implementations.

### Economic Model

SRC-20 deployments incur only Bitcoin miner fees, eliminating token burn requirements or auxiliary cryptocurrency costs. This "fair launch" model ensures accessibility while maintaining immutability through UTXO set storage.

## 4.2 SRC-721: Layered NFT Standard

### Overview

SRC-721 addresses the economic challenge of high-resolution NFT collections by introducing a layered composition architecture. Instead of embedding complete images per mint, collections store reusable layer components once, then reference them through lightweight JSON manifests.

### Architecture

**Layer Storage**: Collections deploy up to 10 layered stamp images using standard Stamps protocol. Each layer is independently stamped with full immutability guarantees.

**Composition Manifests**: Users mint small JSON files (~100-500 bytes) that reference pre-stamped layers, specifying:
- Layer stamp IDs
- Stacking order (z-index)
- Optional layer transformations
- Metadata fields

**Rendering**: Client applications reconstruct final artwork by retrieving and compositing referenced layers in specified order.

### Benefits

1. **Cost Efficiency**: 60-70% reduction in per-NFT minting costs through layer reuse
2. **High Fidelity**: Supports indexed color palettes and high-resolution assets per layer
3. **Composability**: Enables 10K PFP projects and generative art collections
4. **Immutability**: Both layers and manifests are permanently stored in UTXO set

### Transaction Fields

Required fields for valid SRC-721 transactions:

- `p`: "src-721"
- `op`: Operation type (deploy, mint)
- `layers`: Array of stamp IDs comprising the composition
- `attributes`: Metadata describing trait composition

### First Implementation

The AVIME collection by Derp Herpenstein, deployed at block 788041, pioneered the SRC-721 standard.

## 4.3 SRC-721r: Recursive Rendering Standard

### Evolution from SRC-721

SRC-721r extends the layered model by incorporating **on-chain JavaScript libraries** for complex recursive rendering. This enables animated, interactive, and algorithmically generated artwork while maintaining complete on-chain data storage.

### Technical Capabilities

**JavaScript Runtime**: Manifests can include or reference stamped JavaScript libraries that execute client-side to produce final artwork.

**Recursive Composition**: Supports:
- Nested layer hierarchies
- Algorithmic pattern generation
- Animation sequences
- Interactive elements responding to block data or timestamps

**Library Reuse**: Common rendering functions (e.g., noise generators, easing functions) are stamped once and referenced across collections.

### Use Cases

- Generative art projects with algorithmic variation
- Animated collections with on-chain animation logic
- Interactive NFTs responding to blockchain state
- Complex visual effects requiring computational rendering

### Security Considerations

All JavaScript executes client-side in sandboxed environments. The protocol does not introduce execution risk to the Bitcoin network itself, as rendering is strictly a presentation-layer concern.

## 4.4 SRC-101: Domain Registration Standard

### Overview

SRC-101 provides a Bitcoin-native domain name service leveraging Stamps' immutability to solve UTXO-linked asset challenges. Jointly developed by Bitname and Stamp teams, it enables permanent, address-tied naming while supporting the entire Bitcoin ecosystem including Layer 2 solutions.

### Core Design

Domain names are stamped directly onto the Bitcoin blockchain as permanent records tied to user addresses. This separates name ownership from UTXO management, preventing accidental spending of domain-bearing transaction outputs.

### Operations

#### DEPLOY
Creates a name service collection with deployment parameters:

- `name`: Collection identifier
- `tick`: Token symbol (e.g., "BNS")
- `owner`: Must match transaction signer
- `pri`: Price in satoshis per mint
- `max`: Supply limit (0 = unlimited)
- `lim`: Maximum 10 mint operations per transaction
- Optional whitelist with discount rates

#### MINT
Registers individual domain names:

- References deploy transaction hash
- `tokenid`: Name in hexadecimal format
- `dua`: Duration in years before expiration
- `toaddress`: Recipient (may differ from transaction signer)

#### TRANSFER
Moves domain ownership between addresses:

- Transaction signer must be current owner
- `toaddress`: New recipient address
- Supports all Bitcoin address types (Legacy, SegWit, Taproot)

#### SETRECORD
Associates resolver data with domains:

- Supported record types: "address" (resolution target) and "txt" (arbitrary metadata)
- Signer must be service owner
- Multiple records permitted; duplicate keys overwrite previous values

#### RENEW
Extends domain lease period:

- Requires owner authorization
- Payment in satoshis per deployment pricing
- Extends expiration by specified duration

#### TRANSFEROWNERSHIP
Transfers administrative control of the name service:

- Service owner only
- New owner assumes deployment-level permissions

### Address Interoperability

SRC-101 supports resolution and interconversion of all Bitcoin address types, enabling seamless integration with:
- Mainnet (Legacy, P2SH, P2WPKH, P2WSH, Taproot)
- Layer 2 protocols (Lightning Network, sidechains)
- Bitcoin ecosystem extensions

### Economic Model

Deployers set per-mint pricing in satoshis, creating sustainable name services without reliance on external fee structures. Renewal fees provide ongoing revenue while ensuring active namespace use.

## 4.5 Cross-Protocol Guarantees

All token standards share fundamental properties:

1. **Immutability**: Data stored in UTXO set cannot be pruned or modified
2. **Consensus Security**: Protected by Bitcoin's Proof-of-Work
3. **Indexer Validation**: Multiple independent indexer implementations can verify state
4. **No Burn Requirements**: Only Bitcoin miner fees required
5. **Open Source**: Reference indexer and validation logic publicly available

These guarantees distinguish Stamps-based protocols from witness-data alternatives that compromise on permanence or introduce auxiliary dependencies.

---

**References**:

- [Bitcoin Stamps Indexer Repository](https://github.com/stampchain-io/btc_stamps)
- [SRC-101 Specification](https://bitname.gitbook.io/bitname/src-101)
- [Stampchain FAQ](https://stampchain.io/faq)
- [SRC-20 Token Standard Overview](https://trustmachines.co/learn/what-is-the-src-20-token-standard/)
- [Bitcoin Stamps vs Ordinals Analysis](https://coinpedia.org/guest-post/bitcoin-stamps-vs-ordinals-deep-dive-into-future-of-on-chain-permanence/)
