# Bitcoin Stamps Protocols

This document details all protocols supported by the Bitcoin Stamps indexer, including their structure, validation rules, and examples.

## Table of Contents

1. [Common Concepts](#common-concepts)
2. [Classic Stamps](#classic-stamps)
3. [SRC-20 Tokens](#src-20-tokens)
4. [SRC-721 NFTs](#src-721-nfts)
5. [SRC-721r Recursive NFTs](#src-721r-recursive-nfts)
6. [SRC-101 Domains](#src-101-domains)
7. [OLGA Format](#olga-format)
8. [Transaction Sources](#transaction-sources)
9. [Transaction Detection](#transaction-detection)

## Common Concepts

All Bitcoin Stamps protocols share certain common attributes:

- **Immutability**: Data is stored permanently on the Bitcoin blockchain
- **PREFIX**: All protocols use the `stamp:` prefix in their data
- **Transaction Validation**: Each protocol has specific validation rules
- **Stamp ID**: Every valid stamp receives a unique sequential identifier
- **Dual-Source Architecture**: Stamps can originate from direct Bitcoin transactions or Counterparty transactions (with SRC-20 Counterparty transactions discontinued after block 796000)

## Classic Stamps

Classic Stamps are the original Bitcoin Stamps format, allowing for immutable image storage directly on the Bitcoin blockchain.

### Structure

```json
{
  "description": "Bitcoin Stamp: <base64-encoded-image>",
  "cpid": "<counterparty-asset-id>",
  "stamp": <stamp-number>,
  "creator": "<creator-address>"
}
```

### Encoding Methods

Classic Stamps can be encoded using two methods:

1. **OP_MULTISIG**: Original format that encodes data in public keys
   - Public key data is extracted from the multisig script
   - ARC4 decryption is applied using the previous transaction hash as the key
   - Decrypted data must contain the `stamp:` PREFIX
   
2. **OLGA (P2WSH)**: Newer, more efficient format
   - P2WSH scripts are used to store data more efficiently
   - Reduces transaction size by approximately 50%
   - Lowers costs by 60-70% compared to OP_MULTISIG

### Validation Rules

1. Valid Base64 data in the "description" field
2. PREFIX (`stamp:`) must be present after decryption
3. Proper transaction structure
4. Valid keyburn implementation
5. For Counterparty assets, valid CPID

### Example Transaction

```
Transaction ID: e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2
```

### Implementation Details

- Base64 decoding in `stamp.py:decode_base64()`
- File storage in `files.py:store_files()`
- Database recording in `database.py:insert_into_stamp_table()`

## SRC-20 Tokens

SRC-20 is a fungible token protocol inspired by BRC-20 but enhanced with the immutability guarantees of Stamps.

### Operations

#### Deploy

Create a new token with its parameters.

```json
{
  "p": "SRC-20",
  "op": "deploy",
  "tick": "STAMP",
  "max": "21000000",
  "lim": "1000",
  "dec": "0"
}
```

| Field | Description | Validation |
|-------|-------------|------------|
| `p` | Protocol identifier | Must be "SRC-20" |
| `op` | Operation type | Must be "deploy" |
| `tick` | Token ticker | 1-5 characters from allowed set |
| `max` | Maximum token supply | Integer > 0 |
| `lim` | Per-mint limit | Integer > 0 and <= max |
| `dec` | Decimal places | Integer 0-18 |

#### Mint

Create new token supply up to the limit per transaction.

```json
{
  "p": "SRC-20",
  "op": "mint",
  "tick": "STAMP",
  "amt": "1000"
}
```

| Field | Description | Validation |
|-------|-------------|------------|
| `amt` | Amount to mint | Integer > 0 and <= lim |

#### Transfer

Send tokens to another address.

```json
{
  "p": "SRC-20",
  "op": "transfer",
  "tick": "STAMP",
  "amt": "100"
}
```

| Field | Description | Validation |
|-------|-------------|------------|
| `amt` | Amount to transfer | Integer > 0 and <= balance |

### Validation Rules

- Token must be deployed before minting or transferring
- Mint amount cannot exceed per-mint limit
- Total minted cannot exceed max supply
- Transfer amount cannot exceed sender's balance
- Decimal places in amount cannot exceed specified decimal places

### Example Transactions

```
Deploy: 50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1
Mint: e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2
Transfer: 359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc
```

### Implementation Details

- Token validation in `src20.py:Src20Validator`
- Balance tracking in `src20.py:update_src20_balances()`
- Transaction validation in `src20.py:Src20Processor`

## SRC-721 NFTs

SRC-721 is an advanced NFT format that uses JSON manifests to construct complex, layered images from data distributed across multiple Stamps.

### Structure

```json
{
  "p": "SRC-721",
  "op": "mint",
  "ids": [123, 456, 789],
  "meta": {
    "name": "Example NFT",
    "description": "An NFT composed of multiple stamps",
    "attributes": [
      {
        "trait_type": "Background",
        "value": "Blue"
      }
    ]
  },
  "comp": {
    "type": "composite",
    "layers": [
      {
        "id": 123,
        "z": 1,
        "x": 0,
        "y": 0
      },
      {
        "id": 456,
        "z": 2,
        "x": 10,
        "y": 10
      }
    ]
  }
}
```

| Field | Description | Validation |
|-------|-------------|------------|
| `p` | Protocol identifier | Must be "SRC-721" |
| `op` | Operation type | Must be "mint" |
| `ids` | Referenced stamp IDs | Must be existing stamps |
| `meta` | Metadata for the NFT | JSON object |
| `comp` | Composition instructions | JSON object with layer instructions |

### Validation Rules

- All referenced stamp IDs must exist
- Creator must own the referenced stamps
- Valid JSON structure
- Composition instructions must be valid

### Implementation Details

- Composition parsing in `stamp.py`
- Relationship tracking in the database

## SRC-721r Recursive NFTs

SRC-721r extends SRC-721 to enable complex recursive images created using JavaScript and other libraries stored directly on Stamps.

### Structure

```json
{
  "p": "SRC-721r",
  "op": "mint",
  "ids": [123, 456, 789],
  "meta": {
    "name": "Example Recursive NFT",
    "description": "A recursive NFT with JavaScript rendering"
  },
  "code": {
    "type": "javascript",
    "main": 123,
    "resources": [456, 789],
    "entry": "render.js"
  }
}
```

| Field | Description | Validation |
|-------|-------------|------------|
| `p` | Protocol identifier | Must be "SRC-721r" |
| `code` | Code execution details | JSON object with rendering instructions |
| `entry` | Entry point file | Must exist in referenced stamps |

### Validation Rules

- All referenced stamp IDs must exist
- Creator must own the referenced stamps
- Valid JavaScript code structure
- Entry point must be a valid file

### Implementation Details

Similar to SRC-721 but with additional code reference tracking.

## SRC-101 Domains

SRC-101 is a domain name system native to Bitcoin Stamps.

### Operations

#### Register

```json
{
  "p": "SRC-101",
  "op": "reg",
  "name": "example",
  "owner": "bc1q..."
}
```

#### Transfer

```json
{
  "p": "SRC-101",
  "op": "transfer",
  "name": "example",
  "owner": "bc1q..."
}
```

#### Renew

```json
{
  "p": "SRC-101",
  "op": "renew",
  "name": "example"
}
```

| Field | Description | Validation |
|-------|-------------|------------|
| `p` | Protocol identifier | Must be "SRC-101" |
| `op` | Operation type | Must be "reg", "transfer", or "renew" |
| `name` | Domain name | Alphanumeric, 3-63 characters |
| `owner` | Owner address | Valid Bitcoin address |

### Validation Rules

- Domain name must follow format rules
- Registration ownership rules apply
- Domain must not be expired for transfers
- Transfer must be initiated by current owner

### Implementation Details

- Domain validation in `src101.py`
- Ownership tracking in `database.py:update_src101_owners()`

## OLGA Format

OLGA (On-chain Lightweight Graphics Array) is a technical innovation for all stamp types that eliminates Base64 encoding overhead.

### Advantages

- Reduces transaction size by approximately 50%
- Lowers costs by 60-70% compared to OP_MULTISIG
- Maintains full functionality
- More efficient data storage on-chain

### Implementation

OLGA uses P2WSH outputs to store data directly, as opposed to the older OP_MULTISIG approach:

1. Data is encoded directly in P2WSH script
2. First output goes to the recipient
3. Subsequent outputs contain the stamp data
4. Data is concatenated from all outputs
5. PREFIX is identified in the concatenated data

### Transition Point

OLGA became the standard starting at block 833000.

## Transaction Sources

Bitcoin Stamps transactions can originate from two different sources, which are both processed by the indexer:

### 1. Direct Bitcoin Transactions

These transactions embed stamp data directly in the Bitcoin transaction outputs, without using the Counterparty protocol as an intermediary:

- **Encoding**: Data is stored directly in OP_MULTISIG outputs (original method) or P2WSH scripts (OLGA format)
- **Detection**: The indexer scans raw Bitcoin transaction outputs for patterns indicating stamp data
- **Processing**: The indexer extracts and processes data directly from transaction outputs
- **Genesis**: For SRC-20, direct Bitcoin transactions became the standard starting from block 793068 (`BTC_SRC20_GENESIS_BLOCK`)
- **Current Standard**: All SRC-20 tokens now use this method, while classic stamps can use either this or Counterparty

### 2. Counterparty-Based Transactions

Stamps can be created using the Counterparty protocol, which provides a way to create custom assets on Bitcoin:

- **Encoding**: Data is encoded within Counterparty transactions
- **Detection**: The indexer queries the Counterparty API to retrieve transaction data
- **Processing**: The indexer processes pre-decoded data from the Counterparty API
- **Genesis**: The first stamp on Counterparty was at block 779652 (`CP_STAMP_GENESIS_BLOCK`)
- **SRC-20 Transition**: SRC-20 tokens were initially created on Counterparty (started at block 788041) but transitioned to direct Bitcoin transactions
- **End of CP SRC-20**: Only Counterparty SRC-20 transactions are ignored after block 796000 (`CP_SRC20_END_BLOCK`), classic stamp images via Counterparty are still supported

### Historical Transition

The project's evolution shows a transition from Counterparty-based to direct Bitcoin transactions for SRC-20, while maintaining support for both methods for classic stamps:

1. **Early Counterparty Era** (blocks 779652-793068):
   - Initial stamps were created using Counterparty
   - Provided a convenient way to encode data but required Counterparty fees
   - SRC-20 tokens were initially only on Counterparty (starting at block 788041)

2. **Transition Period** (around blocks 793068-796000):
   - Both Counterparty and direct Bitcoin methods were used for all stamp types
   - Direct Bitcoin methods gained popularity due to lower fees and fewer dependencies
   - First SRC-20 tokens on direct Bitcoin appeared at block 793068

3. **Current Era** (block 796000 onward):
   - For SRC-20 tokens: Only direct Bitcoin transactions are supported (Counterparty SRC-20 ignored)
   - For classic stamps: Both direct Bitcoin and Counterparty methods are still supported
   - Direct Bitcoin transactions were further optimized with the OLGA format at block 833000

### Implementation Details

The indexer maintains compatibility with both transaction types:
- Uses different processing paths based on transaction source
- Maintains ongoing support for Counterparty transactions for classic stamps
- After block 796000, only SRC-20 tokens from direct Bitcoin transactions are processed
- Queries the Counterparty API (`CP_RPC_URL`) for Counterparty-based transactions
- Directly processes Bitcoin transactions through the Bitcoin node API

## Transaction Detection

The indexer uses a multi-stage approach to detect protocol-relevant transactions:

### 1. Dual-Path Filtering

The indexer uses two different paths for transaction detection based on source:

#### Direct Bitcoin Transaction Filtering (in blocks.py)

```python
# Pseudocode from filter_block_transactions
for tx in block_data["tx"]:
    # Try to filter with Rust parser first (for direct Bitcoin transactions)
    if backend_instance._parser is not None:
        parsed_txs = backend_instance._parser.batch_parse_transactions(tx_hexes)
        # Process returned transactions (all should be included)
    else:
        # Use Python implementation
        ctx = backend_instance.deserialize(tx["hex"])
        filter_result = quick_filter_src20_transaction(ctx)
        if filter_result:
            raw_transactions[tx["txid"]] = tx["hex"]
```

#### Counterparty Transaction Retrieval

```python
# Pseudocode for Counterparty transaction retrieval
def fetch_xcp_block_async(block_index):
    if block_index < CP_STAMP_GENESIS_BLOCK:
        return None  # Skip blocks before Counterparty stamps existed
    
    # Make API call to retrieve pre-processed Counterparty data
    cp_data = make_xcp_api_call(f"/blocks/{block_index}")
    
    # Process all transactions, but filter out SRC-20 after cutoff block
    transactions = []
    for tx in cp_data.get("transactions", []):
        # For SRC-20, ignore CP transactions after cutoff block
        if block_index > CP_SRC20_END_BLOCK and is_src20_transaction(tx):
            continue
        # Still process classic stamp transactions after cutoff
        transactions.append(tx)
        
    return process_cp_transactions(transactions)
```

### 2. Rust Parser Detection (for Direct Bitcoin Transactions)

The Rust parser evaluates Bitcoin transactions based on:

```rust
// Simplified detection logic
let has_valid_pattern = check_for_p2wsh_pattern() || check_for_multisig_pattern();
let has_valid_data = check_for_prefix_in_decrypted_data();
let keyburn = detect_keyburn_in_transaction();

// Final determination
let should_include = (has_valid_pattern && has_valid_data) || 
                     (has_valid_data && keyburn == 1);

// Only return transactions that should be included
if should_include {
    results.push(tx_info.clone());
}
```

### 3. Unified Protocol-Specific Processing

After transaction filtering/retrieval, each transaction is processed by unified protocol handlers regardless of source:

```python
# In BlockProcessor.process_transaction_results
if stamp_data.pval_src20:
    _, src20_dict = parse_src20(self.db, prevalidated_src, self.processed_src20_in_block, self._lock)
    with self._lock:
        self.processed_src20_in_block.append(src20_dict)
elif stamp_data.pval_src101:
    _, src101_dict = parse_src101(
        self.db, prevalidated_src, self.processed_src101_in_block, stamp_data.block_index, self._lock
    )
    with self._lock:
        self.processed_src101_in_block.append(src101_dict)
```

### 4. Transaction Source Detection

The system identifies transaction sources based on several factors:

```python
# Pseudocode for source detection
def determine_transaction_source(tx_data, block_index):
    # Check if it's a Counterparty transaction (has specific fields)
    if "bindings" in tx_data and tx_data.get("status") == "valid":
        # For SRC-20 after cutoff, reject Counterparty transactions
        if block_index > CP_SRC20_END_BLOCK and is_src20_transaction(tx_data):
            return None  # Reject CP SRC-20 after cutoff
        return "counterparty"  # Accept CP classic stamps after cutoff
        
    # Check for OLGA P2WSH pattern (direct Bitcoin)
    if has_p2wsh_pattern(tx_data) and block_index >= BTC_SRC20_OLGA_BLOCK:
        return "direct_bitcoin"
        
    # Check for OP_MULTISIG pattern (direct Bitcoin)
    if has_multisig_pattern(tx_data):
        return "direct_bitcoin"
        
    return None  # Not a stamp transaction
```