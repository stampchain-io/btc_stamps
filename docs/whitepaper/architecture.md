---
title: "Bitcoin Stamps Protocol: Architecture"
description: "UTXO storage model, encoding layers, account-based asset tracking, and protocol separation"
section: 2
prev: "./introduction.md"
next: "#"
---

# 2. Protocol Architecture

## 2.1 Architectural Overview

Bitcoin Stamps employs a layered architecture separating concerns:

```
┌─────────────────────────────────────────────────────────┐
│                 APPLICATION LAYER                        │
│  Wallets, Explorers, Minting Interfaces, DEX Protocols  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│                  STANDARDS LAYER                         │
│     SRC-20 (Tokens)  │  SRC-721 (Recursion)  │  SRC-101 │
│                     (Names)                              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│                 ASSET TRACKING LAYER                     │
│        Account-based Ledger (Counterparty Model)         │
│   Address Balances, Ownership State, Transfer History   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│                  ENCODING LAYER                          │
│   Bare Multisig (Pre-865k)  │  P2WSH/OLGA (Post-865k)  │
│           Data → Bitcoin Transaction Outputs             │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│                  STORAGE LAYER                           │
│                Bitcoin UTXO Set                          │
│      Consensus-Critical, Unprunable, Universal           │
└─────────────────────────────────────────────────────────┘
```

**Key architectural principle**: Data encoding (UTXO storage) is independent from asset tracking (account balances). Stamps permanently embed transaction data in Bitcoin outputs while maintaining ownership through account ledger.

## 2.2 UTXO Storage Model

### 2.2.1 Bitcoin UTXO Set

Bitcoin maintains an **Unspent Transaction Output (UTXO) set**—the complete list of all unspent outputs on the blockchain. This set is:

- **Consensus-critical**: Required for validating new transactions (ensure inputs reference valid UTXOs)
- **Universal**: Every full node maintains identical UTXO set
- **Unprunable**: Cannot be deleted without breaking transaction validation
- **Permanent**: Persists as long as Bitcoin network operates

**UTXO structure**:
```rust
struct UTXO {
    txid: [u8; 32],           // Transaction ID
    vout: u32,                // Output index
    amount: u64,              // Satoshis
    scriptPubKey: Vec<u8>,    // Locking script
    height: u32,              // Block height
}
```

**Validation requirement**: To validate a transaction spending UTXO X, nodes must:
1. Verify X exists in UTXO set
2. Check spending transaction provides valid unlock script
3. Verify amount conservation (inputs ≥ outputs + fees)
4. Execute output scripts to verify spending conditions

**Critical insight**: Any data embedded in `scriptPubKey` must be stored by all nodes to validate future spends. This makes UTXO-embedded data consensus-critical and unprunable.

### 2.2.2 Why UTXO Storage Guarantees Permanence

Contrast with witness data (SegWit):

**Witness data** (signatures, witness scripts):
- Required only during transaction validation
- After validation, nodes can prune witness data
- Not part of transaction hash (malleability fix)
- Not consensus-critical for future transactions
- **Result**: Witness data is prunable, not guaranteed permanent

**UTXO data** (scriptPubKey, amounts):
- Required for all future transaction validation
- Cannot be pruned without breaking validation
- Part of transaction hash (UTXO uniquely identified by txid:vout)
- Consensus-critical for network operation
- **Result**: UTXO data is unprunable, guaranteed permanent

**Bitcoin Stamps strategy**: Embed asset data in scriptPubKey (output scripts) rather than witness data. This makes stamp data UTXO-embedded and thus consensus-critical.

### 2.2.3 UTXO Set Size Implications

UTXO storage has real cost—every full node stores entire UTXO set in fast-access databases. As of 2026:
- ~150M UTXOs globally (~6GB UTXO database)
- Each stamp adds 1-20 UTXOs depending on data size
- Trade-off: Higher fees for permanent storage vs lower fees for prunable witness data

**Design philosophy**: Accept higher costs for true permanence. Bitcoin Stamps reflects accurate economics of permanent Bitcoin storage. Protocols using witness data or external storage have hidden costs (pruning risk, service maintenance, infrastructure failure).

## 2.3 Encoding Layer Architecture

### 2.3.1 Bare Multisig Encoding (Blocks 779,652 - 865,000)

**Structure**: Use Bitcoin's native multisig scripts to encode data.

**Multisig script format**:
```
OP_1 <pubkey1> <pubkey2> <pubkey3> OP_3 OP_CHECKMULTISIG
```

**Data encoding**:
- `<pubkey1>`, `<pubkey2>`, `<pubkey3>` are 33-byte compressed pubkey format
- Actually contain stamp data, not real public keys
- 2-of-3 multisig: keys 1 & 2 are data (66 bytes), key 3 is real signing key
- Multiple outputs chained for larger data

**Example** (simplified):
```python
# Encode 64 bytes of image data in bare multisig
output_script = OP_1 + data[0:33] + data[33:66] + real_pubkey + OP_3 + OP_CHECKMULTISIG
```

**Characteristics**:
- **Permanent**: Data in scriptPubKey, part of UTXO set
- **Consensus-critical**: Required to spend multisig UTXO
- **Expensive**: Full transaction weight (4 WU per byte)
- **Simple**: Native Bitcoin scripts, no special rules
- **Universal**: Any Bitcoin node can validate

**Limitations**:
- High fees due to no witness discount
- Large stamps require many outputs (cost scales linearly)
- Multisig scripts flagged by some mempool policies (relay issues)

### 2.3.2 P2WSH/OLGA Encoding (Block 865,000+)

**OLGA** (Octet Linked Graphical Artifacts) uses Pay-to-Witness-Script-Hash for 30-95% cost reduction.

**Structure**:
```
Output script: OP_0 <32-byte-script-hash>
Witness: <actual-witness-script>
```

**Data encoding**:
```python
# Encode data in P2WSH witness script
witness_script = data_chunks + OP_DROP_sequence + <conditions>
script_hash = SHA256(witness_script)
output_script = OP_0 + script_hash

# To spend: provide witness_script in witness field
witness = [signatures, witness_script]
```

**Witness script construction**:
```
<data_chunk_1> OP_DROP <data_chunk_2> OP_DROP ... <signature_check>
```
Data chunks are pushed to stack and dropped, leaving only signature verification logic.

**Characteristics**:
- **Still consensus-critical**: Witness script must be provided to spend P2WSH output
- **Weight discount**: Witness data counted at 1/4 weight (WU)
- **Cost reduction**: 30-95% vs bare multisig
- **Same permanence**: Witness scripts stored in UTXO set (not prunable)
- **Better relay**: P2WSH is standard, no mempool policy issues

**Key distinction**: P2WSH witness *scripts* (containing data) are consensus-critical, unlike witness *signatures* (prunable). To spend P2WSH output, validator must:
1. Hash provided witness script
2. Compare to hash in output script
3. Execute witness script
4. Verify conditions satisfied

**Result**: Witness scripts cannot be pruned—required for validation. Stamp data embedded in witness scripts remains permanent and unprunable.

### 2.3.3 Encoding Layer Comparison

| Dimension | Bare Multisig | P2WSH/OLGA |
|-----------|---------------|------------|
| **Permanence** | ✅ UTXO-embedded | ✅ UTXO-embedded (witness script) |
| **Consensus-critical** | ✅ Yes | ✅ Yes (script hash validation) |
| **Prunable** | ❌ No | ❌ No (scripts required for spending) |
| **Cost** | High (4 WU/byte) | Low (1 WU/byte witness) |
| **Relay** | Potential issues | ✅ Standard P2WSH |
| **Complexity** | Simple | Moderate (witness construction) |
| **Block range** | 779,652 - present | 865,000 - present |

**Protocol evolution**: OLGA doesn't replace bare multisig—both remain valid. Stamps can use either encoding; indexers must support both. OLGA is optimization, not consensus change.

## 2.4 Account-Based Asset Tracking

### 2.4.1 The Account Model

**Critical architectural decision**: Bitcoin Stamps uses **account-based** asset tracking, NOT UTXO-based.

**Account-based** (Bitcoin Stamps, Counterparty):
```python
# State: simple address → balance mapping
balances = {
    "bc1q...xyz": {"KEVIN": 1000, "STAMP": 50},
    "bc1q...abc": {"KEVIN": 500}
}

# Transfer: update sender and receiver balances
def transfer(from_addr, to_addr, asset, amount):
    balances[from_addr][asset] -= amount
    balances[to_addr][asset] += amount
```

**UTXO-based** (Colored Coins, theoretical models):
```python
# State: track which UTXOs contain which tokens
token_utxos = {
    "txid1:vout0": {"asset": "TOKEN", "amount": 100},
    "txid2:vout1": {"asset": "TOKEN", "amount": 200}
}

# Transfer: complicated UTXO tracking across inputs/outputs
def transfer(tx):
    input_tokens = sum(token_utxos[input] for input in tx.inputs)
    # Allocate to outputs (complex rules for multi-input, change, fees)
    distribute_to_outputs(tx.outputs, input_tokens)
```

**Why account-based wins**:

1. **Simplicity**: Address balances simpler than UTXO tracking across coin mixing
2. **Privacy**: Don't reveal which specific coins hold tokens
3. **Efficiency**: Single DB query for balance vs scanning UTXO set
4. **Proven**: Counterparty ran 10+ years on account model
5. **UX**: Users understand "address balance" better than "token-bearing UTXO"

**Common misconception**: "SRC-20 tokens are locked in UTXOs." **False**. SRC-20 balances are tracked per address in indexer database. Tokens aren't "in" any specific UTXO—ownership is account-based.

### 2.4.2 Asset State Management

**Indexer responsibilities**:
1. Scan Bitcoin blocks for stamp transactions
2. Decode stamp data (bare multisig or P2WSH)
3. Parse asset operations (DEPLOY, MINT, TRANSFER)
4. Update account balances per consensus rules
5. Serve API queries for balances, history, metadata

**State schema** (simplified):
```sql
-- Account balances
CREATE TABLE balances (
    address TEXT,
    asset TEXT,
    amount NUMERIC,
    PRIMARY KEY (address, asset)
);

-- Transfer history
CREATE TABLE transfers (
    txid TEXT,
    block_height INTEGER,
    from_address TEXT,
    to_address TEXT,
    asset TEXT,
    amount NUMERIC,
    timestamp INTEGER
);

-- Asset metadata
CREATE TABLE assets (
    asset_name TEXT PRIMARY KEY,
    deploy_txid TEXT,
    deploy_block INTEGER,
    total_supply NUMERIC,
    divisible BOOLEAN,
    locked BOOLEAN
);
```

**Consensus rules** (SRC-20 example):
```python
def process_src20_transfer(tx, from_addr, to_addr, asset, amount):
    # Validation
    if balances[from_addr][asset] < amount:
        return False  # Insufficient balance

    # State update
    balances[from_addr][asset] -= amount
    balances[to_addr][asset] += amount

    # History
    transfers.append({
        'txid': tx.txid,
        'from': from_addr,
        'to': to_addr,
        'asset': asset,
        'amount': amount,
        'block': tx.block_height
    })

    return True
```

**Reorganization handling**:
```python
def handle_reorg(old_chain_tip, new_chain_tip):
    # Rollback state to fork point
    fork_height = find_fork_point(old_chain_tip, new_chain_tip)
    rollback_to_height(fork_height)

    # Replay blocks from fork point to new tip
    for block in range(fork_height + 1, new_chain_tip.height + 1):
        process_block(block)
```

### 2.4.3 Transfer Mechanism

**Transaction flow**:

1. **User action**: Send 100 KEVIN tokens to recipient
2. **Transaction construction**:
   - Create Bitcoin transaction from sender's address
   - Embed SRC-20 TRANSFER operation in stamp encoding:
     ```json
     {
       "p": "src-20",
       "op": "transfer",
       "tick": "KEVIN",
       "amt": "100",
       "to": "bc1q...recipient"
     }
     ```
   - Broadcast to Bitcoin network
3. **Block confirmation**: Transaction included in Bitcoin block
4. **Indexer processing**:
   - Detects stamp transaction
   - Decodes TRANSFER operation
   - Validates sender has 100+ KEVIN balance
   - Updates balances: sender -100, recipient +100
5. **User query**: Recipient checks balance via indexer API → sees 100 KEVIN

**Key point**: The Bitcoin transaction itself only stores the TRANSFER instruction. Actual balance updates happen in indexer state. Indexers independently compute same state by replaying transactions.

**Consensus**: Multiple indexers process same blockchain, arrive at identical balances. If indexers disagree, indicates implementation bug—consensus rules must be deterministic.

## 2.5 Layer Separation

### 2.5.1 Encoding ≠ Ownership

**Encoding layer** (UTXO storage):
- Determines WHERE data is stored (which UTXOs)
- Ensures permanence (consensus-critical storage)
- Handles Bitcoin transaction construction
- **Example**: Bare multisig or P2WSH encoding

**Asset tracking layer** (account balances):
- Determines WHO owns WHAT (balances per address)
- Manages transfer logic and validation
- Maintains asset metadata and history
- **Example**: SRC-20 balance ledger

**Independence**: You can change encoding (bare multisig → P2WSH) without changing asset tracking. You can add new asset standards (SRC-721, SRC-101) without changing encoding.

### 2.5.2 Standards Layer Flexibility

**Base stamps protocol**:
- Defines encoding methods (bare multisig, P2WSH)
- No inherent asset semantics
- Just permanent data storage on Bitcoin

**Standards define semantics**:
- **SRC-20**: Fungible tokens with DEPLOY/MINT/TRANSFER operations
- **SRC-721**: Recursion standard for composable stamps
- **SRC-101**: Decentralized naming system
- **Future standards**: Can add new semantics without protocol changes

**Example**: A single stamp transaction can embed:
```json
{
  "stamp": {
    "image": "base64_data",
    "src20": {"op": "mint", "tick": "TOKEN", "amt": "1000"},
    "src721": {"parent": 1234, "trait": "golden"}
  }
}
```
Multiple standards operate on same underlying UTXO permanence.

## 2.6 Architecture Summary

**Layered design**:
1. **Storage**: Bitcoin UTXO set (consensus-critical permanence)
2. **Encoding**: Bare multisig or P2WSH (data → UTXOs)
3. **Asset tracking**: Account-based ledger (Counterparty model)
4. **Standards**: SRC-20/721/101 defining asset semantics
5. **Applications**: Wallets, DEXs, explorers building on indexer APIs

**Key innovations**:
- **UTXO permanence**: Leverage Bitcoin's consensus requirements for guaranteed storage
- **Account simplicity**: Counterparty-proven model avoids UTXO tracking complexity
- **Layer separation**: Encoding independent from asset logic; standards independent from protocol
- **P2WSH optimization**: OLGA reduces costs 30-95% while maintaining permanence

**Tradeoffs**:
- **Higher fees**: True cost of permanent Bitcoin storage (vs prunable witness tricks)
- **Indexer dependency**: Need off-chain state computation (vs pure Bitcoin validation)
- **Larger UTXO set**: Global node storage impact (vs transient witness data)

**Design philosophy**: Embrace Bitcoin's constraints, pay true costs, achieve genuine permanence. No clever hacks—just aligned incentives and honest economics.

---

**Next**: [Token Standards →](./token-standards.md)
**Previous**: [← Introduction](./introduction.md)
