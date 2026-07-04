---
title: "Bitcoin Stamps Implementation"
description: "Indexer architecture, consensus model, and validation logic"
section: 7
prev: "./improvement-proposals.md"
next: "./security.md"
---

# 7. Implementation

## 7.1 Indexer Architecture

Bitcoin Stamps protocol relies on **off-chain indexers** to parse stamp transactions, validate operations, and maintain asset state. Unlike Bitcoin's native UTXO consensus, stamp validity is determined by indexer implementations following deterministic validation rules.

### 7.1.1 Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    INDEXER ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────┐         ┌──────────────────┐           │
│  │  Bitcoin Node  │────────▶│  Block Parser    │           │
│  │  (RPC/REST)    │         │  (ZMQ listener)  │           │
│  └────────────────┘         └────────┬─────────┘           │
│                                       │                      │
│                            ┌──────────▼─────────┐           │
│                            │  Transaction       │           │
│                            │  Decoder           │           │
│                            │  (Multisig/P2WSH) │           │
│                            └──────────┬─────────┘           │
│                                       │                      │
│                   ┌───────────────────┼───────────────┐     │
│                   │                   │               │     │
│         ┌─────────▼────────┐  ┌──────▼──────┐  ┌────▼────┐│
│         │ SRC-20 Validator │  │ SRC-721     │  │ SRC-101 ││
│         │ (Token logic)    │  │ Validator   │  │ Validator││
│         └─────────┬────────┘  └──────┬──────┘  └────┬────┘│
│                   │                   │               │     │
│                   └───────────────────┼───────────────┘     │
│                                       │                      │
│                            ┌──────────▼─────────┐           │
│                            │  State Database    │           │
│                            │  (PostgreSQL/      │           │
│                            │   SQLite)          │           │
│                            └──────────┬─────────┘           │
│                                       │                      │
│                            ┌──────────▼─────────┐           │
│                            │  API Server        │           │
│                            │  (REST/GraphQL)    │           │
│                            └────────────────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 7.1.2 Block Processing Pipeline

**1. Block Discovery**:
```python
# ZMQ subscription for real-time blocks
zmq_socket.subscribe("hashblock")

while True:
    block_hash = zmq_socket.recv()
    block = bitcoin_rpc.getblock(block_hash, 2)  # Verbosity 2: full tx data
    process_block(block)
```

**2. Transaction Filtering**:
```python
def is_stamp_transaction(tx):
    # Check for bare multisig outputs
    for vout in tx['vout']:
        script = vout['scriptPubKey']
        if script['type'] == 'multisig':
            return True
        # Check for P2WSH outputs (OLGA)
        if script['type'] == 'witness_v0_scripthash':
            return True
    return False
```

**3. Data Extraction**:
```python
def extract_stamp_data(tx):
    data_chunks = []

    # Bare multisig extraction
    for vout in tx['vout']:
        if vout['scriptPubKey']['type'] == 'multisig':
            # Extract fake pubkeys (33 bytes each)
            pubkeys = vout['scriptPubKey']['asm'].split()
            for pk in pubkeys[1:-2]:  # Skip OP_1, OP_N, OP_CHECKMULTISIG
                data_chunks.append(bytes.fromhex(pk))

    # P2WSH witness extraction
    for vin in tx['vin']:
        if 'txinwitness' in vin:
            witness_script = vin['txinwitness'][-1]  # Last item is script
            # Parse witness script for data chunks
            chunks = parse_witness_script(witness_script)
            data_chunks.extend(chunks)

    # Concatenate and decode
    raw_data = b''.join(data_chunks)
    return decode_stamp_format(raw_data)
```

**4. Validation**:
```python
def validate_stamp(tx, stamp_data, block_height):
    # Check format validity
    if not is_valid_json(stamp_data):
        return False

    parsed = json.loads(stamp_data)
    protocol = parsed.get('p')

    # Route to protocol-specific validator
    if protocol == 'src-20':
        return validate_src20(tx, parsed, block_height)
    elif protocol == 'src-721':
        return validate_src721(tx, parsed, block_height)
    elif protocol == 'src-101':
        return validate_src101(tx, parsed, block_height)

    return False  # Unknown protocol
```

**5. State Update**:
```python
def update_state(tx, stamp_data, block_height):
    parsed = json.loads(stamp_data)

    if parsed['op'] == 'deploy':
        create_asset(parsed, tx.txid, block_height)

    elif parsed['op'] == 'mint':
        increase_balance(
            address=tx.sender_address,
            asset=parsed['tick'],
            amount=parsed['amt']
        )

    elif parsed['op'] == 'transfer':
        transfer_balance(
            from_addr=tx.sender_address,
            to_addr=parsed['to'],
            asset=parsed['tick'],
            amount=parsed['amt']
        )
```

### 7.1.3 State Database Schema

**Core Tables**:
```sql
-- Asset registry
CREATE TABLE assets (
    asset_name TEXT PRIMARY KEY,
    deploy_txid TEXT NOT NULL,
    deploy_block INTEGER NOT NULL,
    deployer_address TEXT NOT NULL,
    max_supply NUMERIC,
    divisible BOOLEAN DEFAULT TRUE,
    locked BOOLEAN DEFAULT FALSE,
    metadata JSONB
);

-- Account balances (account-based model)
CREATE TABLE balances (
    address TEXT NOT NULL,
    asset TEXT NOT NULL REFERENCES assets(asset_name),
    amount NUMERIC NOT NULL DEFAULT 0,
    last_updated_block INTEGER NOT NULL,
    PRIMARY KEY (address, asset)
);

-- Transfer history
CREATE TABLE transfers (
    txid TEXT PRIMARY KEY,
    block_height INTEGER NOT NULL,
    timestamp INTEGER NOT NULL,
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    asset TEXT NOT NULL REFERENCES assets(asset_name),
    amount NUMERIC NOT NULL,
    status TEXT NOT NULL  -- 'valid', 'invalid'
);

-- Stamp metadata
CREATE TABLE stamps (
    stamp_id SERIAL PRIMARY KEY,
    txid TEXT NOT NULL,
    block_height INTEGER NOT NULL,
    cpid TEXT,  -- Counterparty asset ID (if legacy)
    stamp_url TEXT,
    stamp_hash TEXT,
    stamp_mimetype TEXT,
    supply INTEGER DEFAULT 1,
    divisible BOOLEAN DEFAULT FALSE,
    locked BOOLEAN DEFAULT FALSE,
    creator_address TEXT NOT NULL,
    encoding TEXT NOT NULL  -- 'multisig', 'p2wsh', 'olga'
);

-- SRC-721 compositions
CREATE TABLE src721_layers (
    composition_id TEXT PRIMARY KEY,
    parent_stamp_ids INTEGER[] NOT NULL,
    layer_order INTEGER[] NOT NULL,
    attributes JSONB,
    rendered_hash TEXT
);
```

### 7.1.4 Reorganization Handling

**Challenge**: Bitcoin can experience chain reorganizations (reorgs) where blocks are replaced. Indexers must roll back state and replay new chain.

```python
def handle_reorganization(old_tip_height, new_tip_height, fork_height):
    """
    old_tip_height: Previous chain tip
    new_tip_height: New chain tip after reorg
    fork_height: Block where chains diverged
    """

    # Step 1: Roll back state to fork point
    with db.transaction():
        # Reverse all transfers after fork height
        reversed_transfers = db.query("""
            SELECT * FROM transfers
            WHERE block_height > $1
            ORDER BY block_height DESC
        """, fork_height)

        for transfer in reversed_transfers:
            # Undo transfer: reverse balance changes
            balances[transfer.from_address][transfer.asset] += transfer.amount
            balances[transfer.to_address][transfer.asset] -= transfer.amount

        # Delete rolled-back data
        db.execute("DELETE FROM transfers WHERE block_height > $1", fork_height)
        db.execute("DELETE FROM stamps WHERE block_height > $1", fork_height)

    # Step 2: Replay blocks from new chain
    for height in range(fork_height + 1, new_tip_height + 1):
        block_hash = bitcoin_rpc.getblockhash(height)
        block = bitcoin_rpc.getblock(block_hash, 2)
        process_block(block)

    logger.info(f"Reorg handled: fork at {fork_height}, replayed to {new_tip_height}")
```

**Detection**:
```python
def check_for_reorg(new_block):
    # Get current chain tip from DB
    current_tip = db.query("SELECT MAX(block_height) FROM transfers").scalar()

    # Get parent of new block
    new_block_parent = new_block['previousblockhash']

    # Check if parent matches our current tip
    expected_parent = db.query("""
        SELECT block_hash FROM blocks WHERE block_height = $1
    """, current_tip).scalar()

    if new_block_parent != expected_parent:
        # Reorg detected - find fork point
        fork_height = find_fork_point(new_block_parent)
        handle_reorganization(current_tip, new_block['height'], fork_height)
```

## 7.2 Consensus Model

### 7.2.1 Deterministic Validation

**Critical Property**: All indexers processing the same blockchain must arrive at identical state.

```python
# Example: SRC-20 transfer validation must be deterministic
def validate_src20_transfer(tx, parsed, block_height):
    # Rule 1: Sender must have sufficient balance
    sender = tx.sender_address
    asset = parsed['tick']
    amount = Decimal(parsed['amt'])

    if balances[sender][asset] < amount:
        return False  # Invalid: insufficient balance

    # Rule 2: Asset must exist
    if not asset_exists(asset):
        return False  # Invalid: unknown asset

    # Rule 3: Asset must not be locked
    if assets[asset].locked:
        return False  # Invalid: asset locked

    # Rule 4: Amount must respect divisibility
    if not assets[asset].divisible and amount != int(amount):
        return False  # Invalid: fractional amount for indivisible asset

    # All rules pass
    return True
```

**Consensus Rules**:
- Validation logic must be **order-dependent**: Process transactions in block order
- Floating-point arithmetic **forbidden**: Use fixed-point decimals (Python `Decimal`)
- No external data sources: Only blockchain data determines validity
- Edge cases must have **defined behavior**: No ambiguous outcomes

### 7.2.2 First-Seen Rule

**Problem**: Multiple transactions in same block may conflict (e.g., double-spend attempt).

**Solution**: Process transactions in block order (first-seen wins).

```python
def process_block(block):
    # Process transactions in order (tx index 0, 1, 2, ...)
    for tx_index, tx in enumerate(block['tx']):
        if is_stamp_transaction(tx):
            stamp_data = extract_stamp_data(tx)

            # Validate with current state
            if validate_stamp(tx, stamp_data, block['height']):
                update_state(tx, stamp_data, block['height'])
                assign_stamp_number(tx.txid)  # Only valid stamps get numbers
            else:
                log_invalid_stamp(tx.txid, "Validation failed")

    # Result: First valid transaction wins; later conflicts are invalid
```

**Example**:
```
Block 900,000 contains:
- Tx A (index 5): Transfer 1000 KEVIN from Alice to Bob
- Tx B (index 12): Transfer 1000 KEVIN from Alice to Carol

Alice balance: 1000 KEVIN

Processing:
1. Tx A validated (Alice has 1000 KEVIN) → Alice: 0, Bob: 1000
2. Tx B validated (Alice has 0 KEVIN) → INVALID (insufficient balance)

Result: Bob receives 1000 KEVIN, Carol receives nothing
```

### 7.2.3 Consensus Checkpoints

**Purpose**: Ensure indexer implementations agree on historical state.

**Methodology**: Community-generated state hashes at key block heights.

```python
# Checkpoint format
CHECKPOINTS = {
    796000: {  # Counterparty cutoff block
        'state_hash': 'a3f5c9e8d7b6...',  # Hash of all balances at block 796000
        'total_stamps': 18516,
        'total_assets': 142
    },
    865000: {  # OLGA activation block
        'state_hash': 'e8d7b6a3f5c9...',
        'total_stamps': 45203,
        'total_assets': 387
    }
}

def verify_checkpoint(block_height):
    if block_height not in CHECKPOINTS:
        return True  # No checkpoint at this height

    # Compute state hash
    current_state_hash = compute_state_hash()
    expected_hash = CHECKPOINTS[block_height]['state_hash']

    if current_state_hash != expected_hash:
        raise ConsensusError(
            f"State mismatch at block {block_height}: "
            f"expected {expected_hash}, got {current_state_hash}"
        )

    logger.info(f"Checkpoint verified at block {block_height}")
    return True

def compute_state_hash():
    # Deterministic hash of all balances
    all_balances = db.query("""
        SELECT address, asset, amount
        FROM balances
        ORDER BY address, asset
    """).fetchall()

    # Serialize to JSON with sorted keys
    state_json = json.dumps(all_balances, sort_keys=True)
    return hashlib.sha256(state_json.encode()).hexdigest()
```

### 7.2.4 Multi-Indexer Consensus

**Reference Implementations**:
1. **stampchain.io** (official): Python/Rust hybrid, PostgreSQL backend
2. **OpenStamps** (community): Independent implementation for validation
3. **Alternative indexers**: Third-party implementations for redundancy

**Consensus Verification**:
```bash
# Compare indexer outputs at block height 900,000
curl https://stampchain.io/api/balances/bc1q...xyz?block=900000
# Response: {"KEVIN": "1000.0", "STAMP": "50.0"}

curl https://openstamps.io/api/balances/bc1q...xyz?block=900000
# Response: {"KEVIN": "1000.0", "STAMP": "50.0"}

# If outputs differ → consensus bug, investigation required
```

**Divergence Protocol**:
1. Community reports divergence via GitHub Issue
2. Indexer operators freeze state at divergence block
3. Debug sessions compare validation logs step-by-step
4. Root cause identified (usually edge case in validation logic)
5. Reference implementation patched
6. All indexers update and re-sync from divergence point

## 7.3 Validation Logic

### 7.3.1 SRC-20 Validation

```python
def validate_src20(tx, parsed, block_height):
    op = parsed.get('op')

    if op == 'deploy':
        return validate_src20_deploy(parsed, tx, block_height)
    elif op == 'mint':
        return validate_src20_mint(parsed, tx, block_height)
    elif op == 'transfer':
        return validate_src20_transfer(parsed, tx, block_height)
    else:
        return False  # Unknown operation

def validate_src20_deploy(parsed, tx, block_height):
    # Required fields
    required = ['p', 'op', 'tick', 'max', 'lim']
    if not all(field in parsed for field in required):
        return False

    # Ticker constraints
    tick = parsed['tick']
    if not (1 <= len(tick) <= 5):  # 1-5 characters
        return False
    if not tick.isupper():  # Uppercase only
        return False

    # Check uniqueness
    if asset_exists(tick):
        return False  # Duplicate ticker

    # Supply constraints
    max_supply = Decimal(parsed['max'])
    mint_limit = Decimal(parsed['lim'])

    if max_supply <= 0 or mint_limit <= 0:
        return False
    if mint_limit > max_supply:
        return False

    # Counterparty cutoff rule
    if block_height > 796000:
        # After block 796,000, must use native Bitcoin encoding
        if uses_counterparty_encoding(tx):
            return False

    return True

def validate_src20_mint(parsed, tx, block_height):
    # Asset must exist
    asset = parsed['tick']
    if not asset_exists(asset):
        return False

    # Check supply constraints
    asset_info = get_asset(asset)
    current_supply = get_total_supply(asset)
    mint_amount = Decimal(parsed['amt'])

    # Respect per-mint limit
    if mint_amount > asset_info.mint_limit:
        return False

    # Respect max supply
    if current_supply + mint_amount > asset_info.max_supply:
        return False

    # Asset must not be locked
    if asset_info.locked:
        return False

    return True

def validate_src20_transfer(parsed, tx, block_height):
    sender = tx.sender_address
    asset = parsed['tick']
    amount = Decimal(parsed['amt'])

    # Asset must exist
    if not asset_exists(asset):
        return False

    # Sender must have balance
    if get_balance(sender, asset) < amount:
        return False

    # Amount must be positive
    if amount <= 0:
        return False

    # Respect divisibility
    asset_info = get_asset(asset)
    if not asset_info.divisible:
        if amount != int(amount):
            return False  # No fractional amounts

    return True
```

### 7.3.2 SRC-721 Validation

```python
def validate_src721(tx, parsed, block_height):
    # Required fields
    if 'layers' not in parsed or not isinstance(parsed['layers'], list):
        return False

    # Verify all referenced stamps exist
    for layer_stamp_id in parsed['layers']:
        if not stamp_exists(layer_stamp_id):
            return False  # Invalid: references non-existent stamp

    # Layer count limits (prevent DOS via huge compositions)
    if len(parsed['layers']) > 100:
        return False

    # Optional attributes validation
    if 'attributes' in parsed:
        if not isinstance(parsed['attributes'], dict):
            return False

    return True
```

### 7.3.3 Encoding Detection

```python
def detect_encoding(tx):
    """Determine stamp encoding method"""

    # Check for bare multisig
    for vout in tx['vout']:
        if vout['scriptPubKey']['type'] == 'multisig':
            return 'bare_multisig'

    # Check for P2WSH (OLGA)
    for vout in tx['vout']:
        if vout['scriptPubKey']['type'] == 'witness_v0_scripthash':
            # Verify witness script contains stamp data
            if is_olga_format(tx):
                return 'p2wsh_olga'

    # Check for legacy Counterparty OP_RETURN
    for vout in tx['vout']:
        if vout['scriptPubKey']['type'] == 'nulldata':
            if is_counterparty_format(tx):
                return 'counterparty_op_return'

    return None  # Not a stamp
```

## 7.4 Performance Optimization

### 7.4.1 Rust Parser Integration

**Bottleneck**: Python JSON parsing is slow for high-volume indexing.

**Solution**: Rust-based parser for critical path (stampchain.io implementation).

```rust
// Rust: Fast binary parsing and validation
use serde_json;

pub fn parse_stamp_data(raw_bytes: &[u8]) -> Result<StampData, ParseError> {
    // Validate length prefix
    let expected_len = u16::from_be_bytes([raw_bytes[0], raw_bytes[1]]);
    let actual_len = raw_bytes.len() - 2;

    if expected_len as usize != actual_len {
        return Err(ParseError::LengthMismatch);
    }

    // Parse JSON (serde_json is 20-50x faster than Python)
    let json_data = &raw_bytes[2..];
    let parsed: StampData = serde_json::from_slice(json_data)?;

    Ok(parsed)
}
```

**Performance Impact**:
- Full chain sync (genesis → block 900,000): 3 hours (Rust) vs 48 hours (pure Python)
- Real-time block processing: <100ms per block (Rust) vs 1-3 seconds (Python)

### 7.4.2 Database Indexing

```sql
-- Critical indexes for query performance
CREATE INDEX idx_balances_address ON balances(address);
CREATE INDEX idx_balances_asset ON balances(asset);
CREATE INDEX idx_transfers_block_height ON transfers(block_height);
CREATE INDEX idx_stamps_txid ON stamps(txid);
CREATE INDEX idx_stamps_creator ON stamps(creator_address);

-- Composite indexes for common queries
CREATE INDEX idx_transfers_asset_block ON transfers(asset, block_height);
CREATE INDEX idx_balances_address_asset ON balances(address, asset);
```

### 7.4.3 Caching Strategy

```python
# In-memory cache for hot data
from functools import lru_cache

@lru_cache(maxsize=10000)
def get_asset_info(asset_name):
    """Cache asset metadata (rarely changes)"""
    return db.query("SELECT * FROM assets WHERE asset_name = $1", asset_name)

@lru_cache(maxsize=100000)
def stamp_exists(stamp_id):
    """Cache stamp existence checks"""
    return db.query("SELECT 1 FROM stamps WHERE stamp_id = $1", stamp_id).scalar()

# Invalidate cache on state updates
def update_state(tx, stamp_data, block_height):
    # ... update database ...

    # Clear affected cache entries
    if stamp_data['op'] == 'deploy':
        get_asset_info.cache_clear()  # New asset added
```

## 7.5 API Layer

### 7.5.1 REST Endpoints

```python
# Example API endpoints (stampchain.io)

@app.get("/api/v1/balance/{address}")
def get_balance(address: str, asset: str = None, block: int = None):
    """Get address balance(s) at specific block height"""
    if block:
        # Historical balance query
        return query_balance_at_block(address, asset, block)
    else:
        # Current balance
        return query_current_balance(address, asset)

@app.get("/api/v1/asset/{tick}")
def get_asset_info(tick: str):
    """Get asset metadata"""
    return {
        "tick": tick,
        "deploy_block": assets[tick].deploy_block,
        "max_supply": assets[tick].max_supply,
        "current_supply": get_total_supply(tick),
        "holders": count_holders(tick),
        "transfers": count_transfers(tick)
    }

@app.get("/api/v1/stamp/{stamp_id}")
def get_stamp(stamp_id: int):
    """Get stamp metadata and image data"""
    stamp = db.query("SELECT * FROM stamps WHERE stamp_id = $1", stamp_id)
    return {
        "stamp_id": stamp.stamp_id,
        "txid": stamp.txid,
        "block_height": stamp.block_height,
        "creator": stamp.creator_address,
        "image_url": stamp.stamp_url,
        "encoding": stamp.encoding
    }
```

### 7.5.2 WebSocket Real-Time Updates

```python
import asyncio
from websockets import serve

async def stream_new_stamps(websocket):
    """Stream newly confirmed stamps to connected clients"""
    while True:
        new_stamp = await stamp_queue.get()
        await websocket.send(json.dumps({
            "type": "new_stamp",
            "stamp_id": new_stamp.stamp_id,
            "txid": new_stamp.txid,
            "block_height": new_stamp.block_height
        }))

# Client usage:
# ws = new WebSocket("wss://stampchain.io/ws/stamps")
# ws.onmessage = (event) => { console.log("New stamp:", event.data) }
```

---

## 7.6 Implementation Summary

**Architecture**: Off-chain indexers parse Bitcoin blockchain and maintain asset state in deterministic, verifiable manner.

**Consensus**: No on-chain enforcement—indexers independently validate and must agree on state through deterministic rules.

**Activation Lead Time**: Protocol upgrades (SIPs) require 4+ weeks notice, specified as activation block height.

**Performance**: Hybrid Python/Rust implementation achieves full chain sync in ~3 hours; real-time processing <100ms per block.

**Redundancy**: Multiple independent indexer implementations prevent single point of failure; community checkpoints ensure consensus.

---

**References**:
- [stampchain.io Indexer Source Code](https://github.com/stampchain-io/btc_stamps)
- [OpenStamps Independent Implementation](https://github.com/openstamps/indexer)
- [Bitcoin Core RPC Documentation](https://developer.bitcoin.org/reference/rpc/)
- [ZMQ Block Notifications](https://github.com/bitcoin/bitcoin/blob/master/doc/zmq.md)

---

**Next**: [Security Analysis →](./security.md)
**Previous**: [← SIPs](./improvement-proposals.md)
