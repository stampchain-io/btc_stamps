# SRC-721 Recursive Cursed Behavior Analysis

## Summary
HTML/SVG stamps with `/s/<CPID>` references are **NOT cursed** - they are valid SRC-721 stamps with positive stamp numbers.

## Key Implementation Details

### When Recursive Mints are Detected:
1. **With valid deploy reference**: 
   - `ident = "SRC-721"`
   - `is_btc_stamp = True`
   - Collection metadata populated from deploy
   - Gets positive stamp number

2. **Without valid deploy reference** (CPID not found):
   - `ident = "SRC-721"` (still flagged as SRC-721)
   - `is_btc_stamp = True`
   - No collection metadata (name, description, etc.)
   - Gets positive stamp number
   - NOT cursed

### Why They're Not Cursed:
According to `process_cursed_with_other_conditions()` in models.py, stamps become cursed if they have a CPID AND:
- `ident` is not known OR
- CPID doesn't start with 'A' OR  
- It's an OP_RETURN OR
- Has invalid file suffix

Since recursive mints:
- Have `ident = "SRC-721"` (which is known)
- Have CPIDs starting with 'A'
- Are not OP_RETURN
- Have valid file suffixes (html/svg)

They do NOT meet the criteria for being cursed.

## Original Behavior Preserved
This implementation maintains the original behavior where HTML/SVG content would be processed as regular stamps. The only change is that those containing `/s/<CPID>` patterns are now properly identified as SRC-721 instead of generic STAMPs.