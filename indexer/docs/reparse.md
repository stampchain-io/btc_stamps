## Reparse Mode

The indexer includes a reparse mode that allows validation of data processing without modifying production data. This is useful for:
- Validating code changes
- Testing parsing logic
- Comparing results against known-good data
- Debugging discrepancies

### Usage

1. First, create a snapshot of known-good state:
```bash
poetry run reparse --save-snapshot
```
This reads current blocks from Bitcoin node and processes them using the same parsing logic as the indexer, saving the computed hashes to `snapshots/reference_hashes.json`

2. After making code changes, validate against snapshot:
```bash
poetry run reparse
```
This performs in-memory validation by:
- Fetching blocks from Bitcoin node
- Running them through the parsing logic
- Comparing computed hashes with snapshot
- Never modifies production data

3. For deeper validation with staging DB:
```bash
poetry run reparse --use-db
```
This allows writing to a staging database for detailed comparison

### Configuration

Set the following environment variables in your `.env` file:

REPARSE_MODE=false # Enable/disable reparse mode
SNAPSHOT_PATH=/app/snapshots/reference_hashes.json # Path to hash snapshot file
REPARSE_STAGING_DB=btc_stamps_staging # Optional staging DB for full comparison

### Features

- **Non-Destructive**: Never modifies production data
- **In-Memory Validation**: Fast comparison of computed hashes against known-good values
- **Snapshot Management**: Save and load reference states for comparison
- **Optional DB Comparison**: Can write to staging database for detailed comparison
- **Early Error Detection**: Fails fast when mismatches are detected
- **Detailed Logging**: Provides context for debugging when differences are found

### Implementation Details

The reparse functionality works by:

1. **Creating Snapshots**:
   - Fetches blocks from Bitcoin node
   - Gets CP block data for stamp issuances
   - Processes transactions using the same logic as the indexer
   - Computes block hashes (ledger_hash, txlist_hash, messages_hash)
   - Saves hashes to snapshot file

2. **Validation**:
   - Uses identical parsing logic as the indexer
   - Processes each block:
     - Fetches block data from Bitcoin node
     - Gets CP block data
     - Filters and processes transactions
     - Computes hashes
     - Compares with snapshot
   - Fails immediately on any mismatch

3. **Hash Computation**:
   - Uses same hash functions as production
   - Validates against known checkpoints
   - Ensures consistency with production data

### Integration with Development Workflow

1. Before making changes:
   ```bash
   poetry run reparse --save-snapshot
   ```
   Creates snapshot of current known-good state

2. Make code changes to parsing logic

3. Validate changes:
   ```bash
   poetry run reparse
   ```
   Fast in-memory validation against snapshot

3.5 Verify no missing blocks in snapshot:
   ```bash
   poetry run reparse --sequence
   ```
   Ensure snapshot continuity before deeper validation

4. If issues found:
   ```bash
   poetry run reparse --use-db
   ```
   Detailed comparison using staging database

5. Debug any differences before deploying

This ensures that changes to the parsing logic maintain consistency with existing data without risking production data.