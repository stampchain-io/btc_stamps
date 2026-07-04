# SRC-721 Recursive Collections Implementation Summary

## Overview
Successfully implemented support for SRC-721 Recursive Collections (version "r0") as specified in GitHub issue #437. The implementation allows HTML/SVG stamps containing `/s/<CPID>` references to be automatically detected as SRC-721 mints and associated with their parent collections.

## Key Changes

### 1. Detection Functions (src721.py)
- **`is_recursive_src721_mint()`**: Detects HTML/SVG content containing `/s/<CPID>` pattern
  - Strict CPID validation: `A` followed by exactly 20 digits
  - Works with both HTML (`text/html`) and SVG (`image/svg+xml`) content
  
- **`is_recursive_src721_deploy()`**: Identifies deploy transactions with `"v": "r0"`
  - Case-insensitive version checking (both "r0" and "R0" work)
  - Only triggers for DEPLOY operations

### 2. Processing Logic (models.py)
- **Early detection in `check_decoded_data_fetch_ident_mime()`**:
  - Checks HTML/SVG content for recursive pattern before standard processing
  - Sets `ident = "SRC-721"` and stores referenced CPID
  
- **Enhanced `process_src721()`**:
  - Handles recursive mints specially by looking up parent collection
  - Preserves original HTML/SVG content (no conversion to SVG)
  - Falls back to cursed status if parent collection not found
  - Stores minimal JSON metadata indicating recursive mint

### 3. Backward Compatibility
- Only `"v": "r0"` triggers recursive behavior
- All other SRC-721 versions (v1, v2, or no version) work unchanged
- Standard JSON-based mints continue to function normally
- Collections can have both standard and recursive mints

## Test Coverage

### Recursive SRC-721 Tests (test_src721_recursive.py)
- Pattern detection in HTML/SVG content
- Deploy transaction identification
- Processing with deploy in same block
- Processing with deploy from database
- Handling missing deploy references
- Edge cases and invalid patterns

### Backward Compatibility Tests (test_src721_backward_compatibility.py)
- Standard deploys without version remain unaffected
- v1/v2 format collections work normally
- Standard trait-based mints continue to function
- HTML without recursive pattern is not treated as SRC-721
- Mixed collections (with both standard and recursive mints)
- Strict CPID pattern validation

## Example Transactions
- **Deploy**: `dbe23d8623963a433a9c455416c2af1cbb11274d182b5166ffad95582c9a308f`
  - Creates collection with `"v": "r0"`
- **Mint**: `7ed3d9d67c7cbbfd3dc62fcb789240a5b9fcc30c887bf81fed6678f324a88057`
  - HTML containing `/s/A17785882525351975000` reference

## Database Impact
- Recursive mints are flagged with `ident = "SRC-721"`
- Collection association through existing `collection_name` field
- `src_data` contains minimal JSON: `{"p": "src-721", "v": "r0", "op": "mint", "ref": "<CPID>"}`
- Original HTML/SVG content preserved in `stamp_base64`

## Performance Considerations
- Pattern matching is efficient with compiled regex
- Collection lookups use existing caching mechanisms
- No significant performance impact expected

## Future Considerations
- Monitor for any edge cases in production
- Consider adding metrics for recursive vs standard mints
- Potential for UI enhancements to distinguish recursive mints