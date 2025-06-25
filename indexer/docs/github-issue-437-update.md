# GitHub Issue #437 Update: SRC-721 Recursive Collections Implementation Details

## Summary

After analyzing the codebase and the example transactions, here's a comprehensive breakdown of what needs to be implemented to support SRC-721 Recursive Collections (version "r0").

## Current State

### ✅ What's Working
- **Deploy transactions** are correctly processed
  - Example: `dbe23d8623963a433a9c455416c2af1cbb11274d182b5166ffad95582c9a308f`
  - Correctly creates CPID: `A17785882525351975000`
  - Properly flagged with ident: `SRC-721`
  - Generates collection SVG as expected

### ❌ What's Not Working
- **Mint transactions** are not being processed correctly
  - Example: `7ed3d9d67c7cbbfd3dc62fcb789240a5b9fcc30c887bf81fed6678f324a88057`
  - Not associated with the parent collection
  - Not flagged with `SRC-721` ident
  - HTML content with `/s/<CPID>` references not recognized as SRC-721 mints

## Technical Analysis

### Recursive SRC-721 Format Specification

#### Deploy Transaction Structure
```json
{
  "p": "src-721",
  "v": "r0",              // Key identifier for recursive format
  "op": "deploy",
  "t0": ["A17785882525351975000"],  // Template/trait references
  "max": "150",
  "name": "HNFT Pepe Cash",
  "tick": "HNFTPEPECASH",
  "type": "data:text/html",
  "price": "45000",
  "recipient": "1Drqz87TjYJgEBArDZgynLVbr6MdRRmkW3",
  "description": "First HNFT Pepe Recursive collection EVER!"
}
```

#### Mint Transaction Structure
- **Content**: HTML or SVG file containing `/s/<CPID_OF_THE_DEPLOY>` reference
- **Example**: `<script src=/s/A17785882525351975000 id=1234></script>`
- **Key Difference**: No JSON data in the transaction, only HTML/SVG content

### Code Flow Analysis

1. **Transaction Processing Flow**:
   ```
   blocks.py → stamp.py → models.py → src721.py
   ```

2. **Current Issue**: When a recursive mint transaction is processed:
   - It lacks JSON data with `"p": "src-721"`
   - The system doesn't recognize HTML/SVG with `/s/<CPID>` as SRC-721
   - Falls through to be processed as a regular STAMP instead

## Implementation Requirements

### 1. Detection Logic Updates

#### In `stamp.py` - Update `get_src_or_img_from_data()`
Need to add logic to detect recursive mints that have no JSON but contain HTML/SVG with `/s/` references.

#### In `models.py` - Update `check_decoded_data_fetch_ident_mime()`
Add pattern detection for `/s/<CPID>` in HTML/SVG content to set `ident = "SRC-721"`.

### 2. New Functions Required

#### In `src721.py`:
```python
def is_recursive_src721_mint(decoded_content, stamp_mimetype):
    """
    Detect recursive SRC-721 mints by checking for /s/<CPID> pattern.
    Returns: (is_recursive_mint: bool, referenced_cpid: str|None)
    """

def process_recursive_src721_mint(decoded_content, referenced_cpid, db):
    """
    Process a recursive SRC-721 mint by:
    1. Fetching the deploy transaction data
    2. Extracting collection information
    3. Associating the mint with the collection
    """
```

### 3. Processing Logic Updates

#### In `models.py` - `process_src721()`:
- Check if content is HTML/SVG with `/s/` reference
- If yes, process as recursive mint
- Fetch deploy transaction data
- Set collection metadata
- Keep original HTML/SVG content (don't convert to SVG)

### 4. Database Considerations

- Recursive mints must be associated with their parent collection
- Store original HTML/SVG content, not converted SVG
- `src_data` field should indicate it's a recursive mint

## Implementation Steps

### Phase 1: Basic Detection (Priority: High)
1. Add regex pattern matching for `/s/(A\d{20})` in HTML/SVG content
2. Update ident detection to recognize these as SRC-721
3. Ensure mints are associated with correct collection

### Phase 2: Proper Processing (Priority: High)
1. Fetch and cache deploy transaction data
2. Extract collection metadata
3. Store HTML/SVG content correctly
4. Update database with proper associations

### Phase 3: Validation (Priority: Medium)
1. Validate referenced CPIDs exist
2. Ensure referenced CPID is a valid SRC-721 deploy with `v: r0`
3. Handle edge cases (invalid references, missing deploys)

### Phase 4: Optimization (Priority: Low)
1. Implement caching for deploy lookups
2. Batch process recursive mints
3. Add performance monitoring

## Testing Checklist

- [ ] Deploy transaction creates collection correctly
- [ ] Mint transaction is recognized as SRC-721
- [ ] Mint is associated with correct collection
- [ ] HTML/SVG content is preserved
- [ ] Collection metadata is properly set
- [ ] Reorg handling works correctly
- [ ] Invalid CPID references are handled gracefully

## Important Notes

1. **Version Specificity**: Only transactions with `"v": "r0"` should use recursive logic
2. **Backward Compatibility**: Must not affect existing SRC-721 processing
3. **Content Types**: Only HTML and SVG files can be recursive mints
4. **Pattern Matching**: Must contain `/s/<VALID_CPID>` pattern where CPID matches `A\d{20}` format

## Example Transactions for Testing

- **Deploy**: `dbe23d8623963a433a9c455416c2af1cbb11274d182b5166ffad95582c9a308f`
  - CPID: `A17785882525351975000`
  - Collection: "HNFT Pepe Cash"
  
- **Mint**: `7ed3d9d67c7cbbfd3dc62fcb789240a5b9fcc30c887bf81fed6678f324a88057`
  - Should reference: `A17785882525351975000`
  - Contains HTML with `/s/` reference

## Test Requirements

### Current Test Coverage Analysis

The existing `test_src721.py` covers:
- Basic SRC-721 deploy and mint operations
- SVG generation and validation
- Base64 image validation
- Collection fetching with caching
- Symbol to tick conversion
- Stacked SVG building with layer limits

### Pre-Implementation Tests (Baseline)

Before implementing recursive SRC-721, ensure all existing tests pass:

```bash
pytest tests/test_src721.py -v
```

Key tests to verify:
- `test_validate_src721_and_process_deploy` - Standard deploy processing
- `test_create_src721_mint_svg` - Standard mint SVG creation
- `test_fetch_src721_collection` - Collection data fetching

### New Tests Required for Recursive SRC-721

#### 1. Unit Tests (`tests/test_src721_recursive.py`)

```python
def test_is_recursive_src721_mint():
    """Test detection of recursive SRC-721 mints."""
    # Test HTML with /s/<CPID> pattern
    # Test SVG with /s/<CPID> pattern
    # Test content without pattern (should return False)
    # Test invalid CPID formats

def test_process_recursive_src721_mint():
    """Test processing of recursive mints."""
    # Test fetching deploy data
    # Test collection association
    # Test HTML/SVG preservation

def test_validate_src721_recursive_deploy():
    """Test validation of recursive deploy with v:r0."""
    # Test with valid v:r0 deploy
    # Test without version field
    # Test with different version

def test_recursive_mint_without_json():
    """Test mints that only have HTML/SVG content."""
    # Test detection in stamp.py flow
    # Test ident assignment
```

#### 2. Integration Tests (`tests/test_src721_recursive_integration.py`)

```python
def test_recursive_src721_full_flow():
    """Test complete flow from deploy to mint."""
    # Process deploy transaction
    # Process mint transaction
    # Verify collection association
    # Verify file storage

def test_recursive_mint_collection_lookup():
    """Test mint referencing existing deploy."""
    # Create deploy in DB
    # Process mint with reference
    # Verify correct association

def test_recursive_mint_invalid_reference():
    """Test mint with invalid CPID reference."""
    # Process mint with non-existent CPID
    # Verify graceful handling
```

#### 3. Block Processing Tests

Add to `tests/test_integration_block_processing.py`:

```python
def test_block_with_recursive_src721():
    """Test processing block with recursive SRC-721 transactions."""
    # Mock block with deploy and mints
    # Process block
    # Verify all mints associated correctly
```

#### 4. Test Fixtures

Create new fixtures in `tests/fixtures/src721_recursive/`:

- `deploy_recursive.json` - Example recursive deploy transaction
- `mint_recursive_html.json` - HTML mint referencing deploy
- `mint_recursive_svg.json` - SVG mint referencing deploy
- `invalid_mint_recursive.json` - Mint with invalid reference

### Post-Implementation Tests

After implementation, run comprehensive test suite:

```bash
# Run all SRC-721 tests
pytest tests/test_src721*.py -v

# Run with coverage
pytest tests/test_src721*.py --cov=index_core.src721 --cov-report=html

# Integration tests
pytest tests/test_integration_block_processing.py -k "src721" -v
```

### Performance Tests

```python
def test_recursive_mint_performance():
    """Test performance with multiple recursive mints."""
    # Create deploy
    # Process 100+ mints referencing same deploy
    # Verify caching effectiveness
    # Measure processing time
```

### Edge Case Tests

1. **Circular References**: Mint referencing another mint
2. **Missing Deploy**: Mint without corresponding deploy
3. **Mixed Versions**: Collection with both standard and recursive mints
4. **Reorg Handling**: Rollback with recursive mints
5. **Large HTML/SVG**: Content size limits
6. **Invalid Pattern**: Malformed /s/ references

### Regression Tests

Ensure no impact on existing functionality:
- Standard SRC-721 deploys/mints still work
- Other protocols (SRC-20, SRC-101) unaffected
- STAMP processing unchanged
- File storage and retrieval works

### Manual Testing Checklist

- [ ] Deploy recursive SRC-721 collection
- [ ] Mint with HTML referencing deploy
- [ ] Mint with SVG referencing deploy
- [ ] View mints on stampchain.io
- [ ] Verify collection page shows all mints
- [ ] Test with mainnet data
- [ ] Monitor performance metrics

## References

- Original PR draft: https://github.com/DerpHerpenstein/src-721/tree/draft_version_r
- Deploy transaction: https://stampchain.io/stamps/dbe23d8623963a433a9c455416c2af1cbb11274d182b5166ffad95582c9a308f.svg
- Mint transaction: https://stampchain.io/stamps/7ed3d9d67c7cbbfd3dc62fcb789240a5b9fcc30c887bf81fed6678f324a88057.html