# SRC-721 Recursive Collections Implementation Notes

## Overview

This document provides detailed implementation notes for supporting SRC-721 Recursive Collections (version "r0") as described in GitHub issue #437. This new format allows for more efficient storage of generative NFT collections by storing the base template once and referencing it in subsequent mints.

## Key Differences: Standard vs Recursive SRC-721

### Standard SRC-721 Format
```json
{
  "p": "src-721",
  "op": "mint",
  "c": "A9286823293586848000",
  "ts": [3, 3, 3, 0, 4, 2, 0]
}
```
- Contains trait selection data (`ts`) in the mint transaction
- References collection CPID (`c`) and trait indices

### Recursive SRC-721 Format (v: r0)

#### Deploy Transaction
```json
{
  "p": "src-721",
  "v": "r0",
  "op": "deploy",
  "t0": ["A17785882525351975000"],
  "max": "150",
  "name": "HNFT Pepe Cash",
  "tick": "HNFTPEPECASH",
  "type": "data:text/html",
  "price": "45000",
  "recipient": "1Drqz87TjYJgEBArDZgynLVbr6MdRRmkW3",
  "description": "First HNFT Pepe Recursive collection EVER!"
}
```

#### Mint Transaction
- **JSON Data**: None or minimal (potentially just `{"p":"src-721","v":"r0","op":"mint"}`)
- **HTML/SVG Content**: Contains reference to parent deploy via `/s/<CPID>` pattern
- Example HTML: `<script src=/s/A17785882525351975000 id=1234></script>`

## Implementation Requirements

### 1. Deploy Transaction Processing (Already Working)
The deploy transaction (dbe23d8623963a433a9c455416c2af1cbb11274d182b5166ffad95582c9a308f) is already being processed correctly:
- CPID: A17785882525351975000
- Ident: SRC-721
- Creates standard SRC-721 collection SVG

### 2. Mint Transaction Processing (Needs Implementation)

#### Current Issue
Mint transactions like 7ed3d9d67c7cbbfd3dc62fcb789240a5b9fcc30c887bf81fed6678f324a88057 are not being:
1. Associated with the correct collection
2. Flagged with SRC-721 ident

#### Required Changes

##### A. Pattern Detection in `stamp.py`
In the `get_src_or_img_from_data` function (line 145-177), add detection for recursive SRC-721 mints:

```python
def get_src_or_img_from_data(stamp, block_index):
    # ... existing code ...
    
    # Check for recursive SRC-721 pattern without JSON
    if "description" not in stamp:
        if (("p" in stamp or "P" in stamp) and 
            stamp.get("p").upper() == "SRC-721" and 
            stamp.get("v", "").lower() == "r0" and 
            stamp.get("op", "").upper() == "MINT"):
            # Minimal JSON for recursive mint
            return stamp, None, None, 1
        # ... existing protocol checks ...
    else:
        # For recursive SRC-721, check if HTML/SVG contains /s/ reference
        stamp_description = stamp.get("description")
        if stamp_description is None:
            return None, None, None, None
            
        base64_string, stamp_mimetype = parse_base64_from_description(stamp_description)
        decoded_base64, is_valid_base64 = decode_base64(base64_string, block_index)
        
        # For recursive SRC-721 mints, we need to check the content
        # This will be handled in the validation phase
        return decoded_base64, base64_string, stamp_mimetype, is_valid_base64
```

##### B. Enhanced Recursive Mint Detection in `src721.py`
Add a new function to detect and process recursive mints:

```python
def is_recursive_src721_mint(decoded_content, stamp_mimetype):
    """
    Check if content is a recursive SRC-721 mint by looking for /s/<CPID> pattern.
    
    Args:
        decoded_content: The decoded content (HTML/SVG)
        stamp_mimetype: The MIME type of the content
        
    Returns:
        tuple: (is_recursive_mint, referenced_cpid)
    """
    if not decoded_content or stamp_mimetype not in ["text/html", "image/svg+xml"]:
        return False, None
    
    try:
        # Convert bytes to string if needed
        if isinstance(decoded_content, bytes):
            content_str = decoded_content.decode('utf-8', errors='ignore')
        else:
            content_str = str(decoded_content)
        
        # Look for /s/<CPID> pattern
        import re
        pattern = r'/s/(A\d{20})'
        matches = re.findall(pattern, content_str)
        
        if matches:
            # Return the first CPID found
            return True, matches[0]
            
    except Exception as e:
        logger.debug(f"Error checking for recursive mint: {e}")
    
    return False, None
```

##### C. Modify `validate_src721_and_process` function
Update the function to handle recursive mints:

```python
def validate_src721_and_process(src721_json, valid_stamps_in_block, db, lock=None):
    try:
        # ... existing code ...
        
        # Check if this might be a recursive mint (no JSON data)
        if src721_json is None or (isinstance(src721_json, dict) and not src721_json):
            # This could be a recursive mint - will be handled differently
            return (None, "html", None, None, None, None)
        
        src721_json = convert_to_dict(src721_json)
        op_val = src721_json.get("op", "").upper()
        
        # ... rest of existing code ...
```

##### D. Modify `models.py` to Handle Recursive Mints
In the `process_src721` method (line 632), add handling for recursive mints:

```python
def process_src721(self, valid_stamps_in_block, db):
    # Check if this is a recursive mint (HTML/SVG with /s/ reference)
    if self.decoded_base64 and self.stamp_mimetype in ["text/html", "image/svg+xml"]:
        from index_core.src721 import is_recursive_src721_mint
        is_recursive, referenced_cpid = is_recursive_src721_mint(
            self.decoded_base64, self.stamp_mimetype
        )
        
        if is_recursive and referenced_cpid:
            # Find the deploy transaction in valid_stamps_in_block or database
            deploy_data = None
            
            # First check in current block's stamps
            for stamp in valid_stamps_in_block:
                if stamp.get("cpid") == referenced_cpid:
                    deploy_data = stamp.get("src_data")
                    break
            
            # If not found, fetch from database
            if not deploy_data:
                from index_core.src721 import fetch_collection_details
                deploy_data = fetch_collection_details(referenced_cpid, db)
            
            if deploy_data:
                # Parse deploy data to get collection info
                deploy_json = json.loads(deploy_data) if isinstance(deploy_data, str) else deploy_data
                
                # Set collection information
                self.collection_name = deploy_json.get("name")
                self.collection_description = deploy_json.get("description")
                self.collection_website = deploy_json.get("website")
                self.collection_onchain = 1
                
                # Mark as valid SRC-721
                self.is_btc_stamp = True
                self.src_data = json.dumps({
                    "p": "src-721",
                    "v": "r0",
                    "op": "mint",
                    "ref": referenced_cpid
                })
                
                # Keep original content as-is (HTML/SVG)
                # Don't convert to SVG like standard SRC-721
                return
    
    # Fall back to standard SRC-721 processing
    # ... existing code ...
```

##### E. Update `check_decoded_data_fetch_ident_mime` in `models.py`
This function needs to recognize recursive SRC-721 mints:

```python
def check_decoded_data_fetch_ident_mime(self):
    # ... existing code ...
    
    # Check for recursive SRC-721 mint pattern in HTML/SVG
    if self.stamp_mimetype in ["text/html", "image/svg+xml"] and self.decoded_base64:
        from index_core.src721 import is_recursive_src721_mint
        is_recursive, referenced_cpid = is_recursive_src721_mint(
            self.decoded_base64, self.stamp_mimetype
        )
        
        if is_recursive and referenced_cpid:
            self.ident = "SRC-721"
            # Don't change the content - keep HTML/SVG as-is
            return
    
    # ... rest of existing code ...
```

### 3. Database Considerations

1. **Collection Association**: Recursive mints need to be associated with the collection from the deploy transaction
2. **File Storage**: HTML/SVG files should be stored as-is, not converted to SVG
3. **Metadata**: The `src_data` field should store minimal JSON indicating it's a recursive mint

### 4. Validation Rules

1. **Version Check**: Only process as recursive if `"v": "r0"` in deploy
2. **CPID Validation**: Ensure referenced CPID exists and is a valid SRC-721 deploy
3. **Content Type**: Only HTML and SVG files can be recursive mints
4. **Pattern Matching**: Must contain `/s/<VALID_CPID>` pattern

## Testing Considerations

1. **Deploy Transaction**: dbe23d8623963a433a9c455416c2af1cbb11274d182b5166ffad95582c9a308f
   - Should create collection with CPID A17785882525351975000
   - Should have ident = "SRC-721"

2. **Mint Transaction**: 7ed3d9d67c7cbbfd3dc62fcb789240a5b9fcc30c887bf81fed6678f324a88057
   - Should be associated with collection "HNFT Pepe Cash"
   - Should have ident = "SRC-721"
   - Should store HTML content as-is
   - Should reference CPID A17785882525351975000

3. **Edge Cases**:
   - Invalid CPID references
   - Non-existent deploy transactions
   - Mixed version formats in same collection
   - Reorg handling for recursive mints

## Backward Compatibility

- Changes must not affect existing SRC-721 processing
- Only transactions with `"v": "r0"` should use recursive logic
- Standard SRC-721 (without version or with other versions) must continue working as before

## Performance Considerations

1. **Caching**: Deploy transaction data should be cached to avoid repeated DB lookups
2. **Pattern Matching**: Use compiled regex for `/s/<CPID>` pattern detection
3. **Batch Processing**: When processing blocks, group recursive mints by referenced CPID

## Security Considerations

1. **CPID Validation**: Must validate that referenced CPIDs are legitimate SRC-721 deploys
2. **Content Validation**: Ensure HTML/SVG content is safe and doesn't contain malicious scripts
3. **Circular References**: Prevent recursive mints from referencing other recursive mints

## Implementation Priority

1. **Phase 1**: Basic recursive mint detection and association
2. **Phase 2**: Proper file storage and display
3. **Phase 3**: Performance optimizations and caching
4. **Phase 4**: Advanced validation and security checks