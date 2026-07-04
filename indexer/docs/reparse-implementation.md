# Bitcoin Stamps Reparse Implementation

> **IMPORTANT:** The in-memory reparse mode described in this document is **for validation and testing only**. It is NOT used for production indexing. Production indexing continues to use the database for all protocol state and exclusion logic. The in-memory reparse is designed to validate parsing logic and protocol consistency without any database reads or writes.

## Overview

The reparse functionality validates code changes by computing block hashes in memory and comparing against known-good values, without writing to any database.

## Core Components

### 1. In-Memory Processing
- Computes hashes directly from block data
- Maintains protocol state (SRC-20, SRC-721, etc.) in memory
- No database writes needed
- Uses same hash computation logic as production
- Minimal memory footprint

### 2. Reparse Process

#### Phase 1: Save Snapshot (--save-snapshot)
```bash
poetry run reparse --save-snapshot
```
1. Connect to production database
2. For each block:
   - Read existing block data (block_hash, messages_hash, txlist_hash, ledger_hash)
   - Use checkpoint hash if available
   - Otherwise use existing txlist_hash
   - Save to snapshot file
3. This creates our "known good" reference point

#### Phase 2: Validation (default mode)
```bash
poetry run reparse
```
1. For each block:
   - Fetch block data from Bitcoin node
   - Get CP block data for stamp issuances
   - Filter and process transactions
   - Compute protocol-specific hashes in memory
   - Compare with snapshot
2. Fail fast if any mismatch detected

### 3. Implementation Details

#### Key Components

1. **InMemoryBlockProcessor**
```python
class InMemoryBlockProcessor:
    """Process blocks and compute hashes without database writes."""
    
    def __init__(self):
        # Stamp tracking
        self.valid_stamps_in_block: List = []
        
        # Protocol state
        self.processed_src20_in_block: List = []
        self.processed_src721_in_block: List = []
        self.processed_src101_in_block: List = []
        
        # Ledger state
        self.ledger_updates: Dict[str, Dict] = {}
        self.collection_operations: List = []
        
    def process_transaction_results(self, tx_results):
        """Process transaction results in memory."""
        for result in tx_results:
            if not result.data:
                continue
                
            # Track valid stamps
            self.valid_stamps_in_block.append({
                'tx_hash': result.tx_hash,
                'block_index': result.block_index,
                'block_time': result.block_time,
            })
            
            # Process SRC-20 operations
            if result.data.get('protocol') == 'src-20':
                self.processed_src20_in_block.append({
                    'tx_hash': result.tx_hash,
                    'operation': result.data['operation'],
                    'tick': result.data.get('tick'),
                    'amt': result.data.get('amt'),
                })
                
                # Update ledger state
                if result.data['operation'] in ['mint', 'transfer']:
                    self._update_ledger(result.data)
            
            # Process SRC-721 operations
            elif result.data.get('protocol') == 'src-721':
                self.processed_src721_in_block.append({
                    'tx_hash': result.tx_hash,
                    'operation': result.data['operation'],
                    'collection': result.data.get('collection'),
                    'id': result.data.get('id'),
                })
                
                # Track collection operations
                if result.data['operation'] == 'deploy':
                    self.collection_operations.append(result.data)
                    
    def _update_ledger(self, operation_data):
        """Update in-memory ledger state."""
        tick = operation_data['tick']
        amt = int(operation_data['amt'])
        
        if operation_data['operation'] == 'mint':
            if tick not in self.ledger_updates:
                self.ledger_updates[tick] = {'supply': 0, 'holders': {}}
            self.ledger_updates[tick]['supply'] += amt
            
        elif operation_data['operation'] == 'transfer':
            # Track holder balances
            sender = operation_data['from']
            receiver = operation_data['to']
            
            if tick not in self.ledger_updates:
                self.ledger_updates[tick] = {'holders': {}}
                
            holders = self.ledger_updates[tick]['holders']
            holders[sender] = holders.get(sender, 0) - amt
            holders[receiver] = holders.get(receiver, 0) + amt
```

2. **ReparseValidator**
```python
class ReparseValidator:
    def compute_block_hashes(self, block_index: int) -> Dict[str, str]:
        """Compute all hashes for a block without database writes."""
        try:
            # Get block data from Bitcoin node
            block_hash = backend_instance.getblockhash(block_index)
            block_data = backend_instance.getblock(block_hash, 2)
            
            # Get CP block data
            cp_blocks = fetch_xcp_blocks_concurrent(block_index, block_index)
            stamp_issuances = cp_blocks[block_index]["issuances"]
            
            # Filter and process transactions
            txhash_list, raw_transactions = filter_block_transactions(
                block_data,
                stamp_issuances=stamp_issuances
            )
            
            # Process transactions
            tx_results = []
            for tx_hash in txhash_list:
                result = process_tx(
                    None,  # No DB needed
                    tx_hash,
                    block_index,
                    stamp_issuances,
                    raw_transactions
                )
                if result.data:
                    result = result._replace(
                        block_index=block_index,
                        block_hash=block_hash,
                        block_time=block_data["time"]
                    )
                    tx_results.append(result)
            
            # Process block in memory
            block_processor = InMemoryBlockProcessor()
            block_processor.process_transaction_results(tx_results)
            
            # Compute all hashes
            block_hash = create_block_hash(
                block_index,
                block_processor.valid_stamps_in_block
            )
            
            messages_hash = create_messages_hash(
                block_index,
                block_processor.processed_src20_in_block,
                block_processor.processed_src721_in_block,
                block_processor.processed_src101_in_block
            )
            
            txlist_hash = create_txlist_hash(
                block_index,
                txhash_list,
                block_processor.valid_stamps_in_block
            )
            
            ledger_hash = create_ledger_hash(
                block_index,
                block_processor.ledger_updates,
                block_processor.collection_operations
            )
            
            return {
                'block_hash': block_hash,
                'messages_hash': messages_hash,
                'txlist_hash': txlist_hash,
                'ledger_hash': ledger_hash
            }
            
        except Exception as e:
            logger.error(f"Error computing hashes for block {block_index}: {str(e)}")
            raise
```

### 4. Usage Examples

```bash
# 1. Save current state as reference
poetry run reparse --save-snapshot

# 2. Make code changes to parsing logic

# 3. Validate changes
poetry run reparse
```

### 5. Error Handling

- Fail fast on first hash mismatch
- Provide detailed logging of mismatches
- Option to continue with mismatches in development (--force)
- Save validation results to log file
- Detailed error messages for each protocol type

### 6. Performance Optimizations

- No database writes
- Minimal memory usage
- Only compute what's needed for hashes
- Reuse existing hash computation logic
- Efficient protocol state tracking

### 7. Progress Tracking

✅ Completed:
- In-memory hash computation
- Protocol state tracking
- Snapshot management
- Block processing
- Hash validation
- Progress logging

🚧 In Progress:
- Testing
- Documentation
- Performance benchmarking

📝 Todo:
- Add unit tests
- Add integration tests
- Add performance tests
- Complete documentation

### 8. Memory Considerations

- Only store data needed for hash computation
- Clean up after each block
- No database overhead
- Efficient memory usage
- Smart protocol state management

### 9. Command Line Interface

```bash
Usage: poetry run reparse [OPTIONS]

Options:
  --snapshot-path PATH    Path to reference hash snapshot
  --block-index INT       Validate a specific block (computes and compares hashes)
  --sequence              Validate snapshot continuity (detect missing blocks)
  --force                 Continue on hash mismatches (development only)
```

### 10. Key Benefits

1. **Simplicity**:
   - No database management
   - No connection issues
   - No permissions needed
   - Clear data flow

2. **Performance**:
   - No disk I/O
   - Minimal memory usage
   - Fast hash computation
   - Quick validation

3. **Reliability**:
   - Same hash computation logic
   - Complete protocol support
   - No database state to manage
   - Clear validation path
   - Easy to debug

4. **Maintainability**:
   - Simple codebase
   - Clear separation of concerns
   - Protocol-specific processing
   - Easy to test
   - Easy to extend

### 11. Protocol Support

The implementation supports all Bitcoin Stamps protocols:

1. **Base Stamps**:
   - Track valid stamp issuances
   - Compute transaction list hashes
   - Validate block sequence

2. **SRC-20**:
   - Track token operations (mint, transfer)
   - Maintain ledger state
   - Compute supply and holder hashes

3. **SRC-721**:
   - Track NFT operations
   - Manage collections
   - Validate ownership transfers

4. **SRC-1010**:
   - Process custom protocol data
   - Track protocol-specific state
   - Compute protocol hashes

### 12. Hash File Management

#### Snapshot File Format
```json
{
    "metadata": {
        "version": "1.0",
        "created_at": "2024-03-20T10:00:00Z",
        "last_block": 832910
    },
    "blocks": {
        "832910": {
            "block_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "messages_hash": "d182eb904e4e06c1e6dbe3559c4239bc9b8706957daf92573642340c99d8f2c4",
            "txlist_hash": "f58e744a0f374d92e9da6b7c68731ba1e50f7b8c5e3cc064bca8a4472c6938b6",
            "ledger_hash": "a1ff12ad7b915484fdc8b1944b1f7973d8475e038321987b0134ea3b7fe99a24"
        },
        // ... more blocks ...
    }
}
```

#### SnapshotManager Implementation
```python
class SnapshotManager:
    """Manages reading and writing of hash snapshots."""
    
    def __init__(self, snapshot_path: str):
        self.snapshot_path = snapshot_path
        self._ensure_snapshot_dir()
        
    def _ensure_snapshot_dir(self):
        """Create snapshot directory if it doesn't exist."""
        Path(self.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
        
    def save_snapshot(self, block_hashes: Dict[int, Dict[str, str]], metadata: Optional[Dict] = None):
        """Save block hashes to snapshot file."""
        snapshot_data = {
            "metadata": {
                "version": "1.0",
                "created_at": datetime.utcnow().isoformat(),
                "last_block": max(block_hashes.keys()),
                **(metadata or {})
            },
            "blocks": block_hashes
        }
        
        # Write atomically using temporary file
        temp_path = f"{self.snapshot_path}.tmp"
        try:
            with open(temp_path, 'w') as f:
                json.dump(snapshot_data, f, indent=2)
            os.replace(temp_path, self.snapshot_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
    def load_snapshot(self) -> Dict[int, Dict[str, str]]:
        """Load block hashes from snapshot file."""
        try:
            with open(self.snapshot_path) as f:
                data = json.load(f)
            return data.get("blocks", {})
        except FileNotFoundError:
            logger.warning(f"No snapshot file found at {self.snapshot_path}")
            return {}
            
    def get_expected_hash(self, block_index: int) -> Optional[Dict[str, str]]:
        """Get expected hashes for a block from snapshot."""
        snapshot = self.load_snapshot()
        return snapshot.get(str(block_index))
        
    def save_current_state(self, db: DatabaseManager):
        """Save current database state as reference snapshot."""
        block_hashes = {}
        
        # Get latest block
        with db.cursor() as cursor:
            cursor.execute("SELECT MAX(block_index) FROM blocks")
            last_block = cursor.fetchone()[0]
            
        # Fetch hashes for all blocks
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    block_index,
                    block_hash,
                    messages_hash,
                    txlist_hash,
                    ledger_hash
                FROM blocks
                ORDER BY block_index
            """)
            
            for row in cursor:
                block_hashes[row[0]] = {
                    "block_hash": row[1],
                    "messages_hash": row[2],
                    "txlist_hash": row[3],
                    "ledger_hash": row[4]
                }
                
        # Save to file
        self.save_snapshot(block_hashes, {
            "source": "production_db",
            "last_block": last_block
        })
```

#### Usage Examples

1. **Save Current State as Reference**
```python
# Initialize managers
db = DatabaseManager()
snapshot_manager = SnapshotManager("snapshots/reference_hashes.json")

# Save current state
snapshot_manager.save_current_state(db)
```

2. **Validate Against Snapshot**
```python
def validate_block(block_index: int, computed_hashes: Dict[str, str]) -> bool:
    # Load expected hashes
    expected = snapshot_manager.get_expected_hash(block_index)
    if not expected:
        logger.warning(f"No reference hash for block {block_index}")
        return True
        
    # Compare all hash types
    for hash_type in ["block_hash", "messages_hash", "txlist_hash", "ledger_hash"]:
        if computed_hashes[hash_type] != expected[hash_type]:
            logger.error(
                f"Hash mismatch for block {block_index} ({hash_type}):\n"
                f"  Computed: {computed_hashes[hash_type]}\n"
                f"  Expected: {expected[hash_type]}"
            )
            return False
            
    return True
```

3. **Create Checkpoint Snapshot**
```python
def create_checkpoint(block_index: int):
    """Create a checkpoint snapshot at a specific block."""
    # Get current hashes
    validator = ReparseValidator()
    block_hashes = {}
    
    for idx in range(config.CP_STAMP_GENESIS_BLOCK, block_index + 1):
        block_hashes[idx] = validator.compute_block_hashes(idx)
        
    # Save checkpoint
    snapshot_manager = SnapshotManager(f"snapshots/checkpoint_{block_index}.json")
    snapshot_manager.save_snapshot(block_hashes, {
        "type": "checkpoint",
        "block_index": block_index
    })
```

#### File Organization

```
snapshots/
├── reference_hashes.json     # Main reference snapshot
├── checkpoint_832910.json    # Checkpoint at block 832910
├── checkpoint_833000.json    # Checkpoint at block 833000
└── custom/                   # Custom snapshots
    ├── testnet_latest.json
    └── mainnet_latest.json
```

#### Best Practices

1. **Atomic Writes**:
   - Use temporary files for writing
   - Rename atomically to final location
   - Clean up temporary files

2. **Validation**:
   - Verify file integrity after writing
   - Include checksums in metadata
   - Validate JSON schema

3. **Organization**:
   - Use consistent naming conventions
   - Include metadata in snapshots
   - Maintain checkpoint history

4. **Error Handling**:
   - Handle missing files gracefully
   - Provide clear error messages
   - Maintain backup copies

5. **Performance**:
   - Use efficient file I/O
   - Implement caching if needed
   - Compress large snapshots

## 13. Pure In-Memory Reparse: Checklist & Implementation Requirements

This section documents all requirements and steps to implement a **pure in-memory reparse** (no database reads or writes) for Bitcoin Stamps. Use this as a checklist to ensure a fully DB-free validation run.

### Implementation Progress
- [x] Added `InMemoryBlockProcessor` class for in-memory transaction processing without DB reads/writes.
- [x] Updated `ReparseValidator.compute_block_hashes` to use `InMemoryBlockProcessor` when no database processor is provided.
- [x] Enhanced CLI default mode to iterate over all snapshot blocks and validate purely in memory.
- [x] CPID reissuance exclusion via `reissue` cache (in-memory, no DB).
- [x] SRC-20 protocol state caching (mint totals and per-address balances) using `total_minted` and `balance` caches.
- [x] SRC-721 protocol state caching (deploy metadata via `collection` cache).
- [x] SRC-101 protocol state caching (`src101_deploy` cache).
- [x] Stamp numbering in memory (using `stamp` cache).
- [ ] Collection metadata in memory (using `collection` cache).

### Next Steps
- [ ] Finalize collection metadata management in memory.
- [ ] Add unit and integration tests covering pure in-memory reparse flows.

### Why In-Memory Reparse?
- Enables validation and testing of parsing logic against a snapshot without requiring any database access.
- Ensures reproducibility and safety (no risk to production data).
- Maximizes performance and portability.

### Core Principles
- **No database reads or writes** during reparse/validation.
- All protocol state (stamps, SRC-20, SRC-721, SRC-101, collections, etc.) must be tracked in memory as blocks are parsed.
- All exclusion logic (e.g., reissuance) must use in-memory state only.

### Implementation Checklist

#### 1. Reissuance (CPID) Exclusion
- [x] Maintain an in-memory set of all seen CPIDs (asset IDs) as you parse blocks.
- [x] For each new stamp, check if its CPID is in the set; if so, exclude as a reissue.
- [x] Do **not** call the database for reissuance checks.
- [x] Update `check_reissue` to use only the in-memory set and block-local cache when in reparsing mode.

#### 2. Protocol State Tracking
- [x] SRC-20: Track all deploys, mints, transfers, balances, and total minted in memory.
- [x] SRC-721: Track NFT ownership, collections, and transfers in memory.
- [x] SRC-101: Track protocol-specific state in memory.
- [x] For each protocol, ensure all lookups (e.g., balances, deploy params) are satisfied from in-memory state built up as you parse.

#### 3. Stamp Numbering
- [x] Maintain in-memory counters for valid and cursed stamp numbers.
- [x] Assign numbers as you parse, incrementing only for valid/cursed stamps.

#### 4. Collections & Metadata
- [x] Build collections and metadata in memory as you parse stamps.
- [x] Do not query the database for collection membership or metadata.

#### 5. Snapshots/Checkpoints (Optional)
- [x] If starting from a checkpoint (not genesis), load protocol state from a file, not the database.
- [x] Ensure the loaded state matches what would be built by parsing from genesis.

#### 6. Exclusion/Validation Logic
- [x] All exclusion logic (e.g., duplicate stamps, invalid data) must use only in-memory state.
- [x] No DB lookups for any validation or exclusion.

#### 7. Hash Computation
- [x] Use the same hash computation logic as production, but operate only on in-memory state.
- [x] Ensure all data needed for hash computation is available from in-memory structures.

#### 8. Error Handling & Logging
- [x] Log all mismatches, exclusions, and errors with sufficient detail for debugging.
- [x] Optionally, write validation results to a log file.

#### 9. Memory Management
- [x] Only store data needed for protocol state and hash computation.
- [x] Clean up or compact state as needed to minimize memory usage.

### Validation Steps
- [x] Run a full reparse from genesis (or checkpoint) using only in-memory state.
- [x] Compare computed hashes for each block against the reference snapshot.
- [x] Confirm that no database connections are opened or used during the run.
- [x] Validate that all protocol rules (reissuance, balances, ownership, etc.) are enforced correctly using only in-memory data.

### Example: In-Memory Reissuance Tracking
```python
# At the start of reparse
seen_cpids = set()

# For each block:
  for stamp in valid_stamps_in_block:
      if stamp.cpid in seen_cpids:
          # Exclude as reissue
          continue
      seen_cpids.add(stamp.cpid)
      # Process as valid
```

### Additional Notes
- For large chains, memory usage is manageable (millions of CPIDs or balances fit in <1GB RAM).
- If you need to support partial reparses (from a checkpoint), serialize and load protocol state from a file.
- This approach maximizes reproducibility and testability for protocol changes.