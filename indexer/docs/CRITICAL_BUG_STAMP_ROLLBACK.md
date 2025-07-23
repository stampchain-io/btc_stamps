# Critical Bug: Stamp Number Gaps During Rollback

## Issue Summary
A critical bug was discovered in production where stamp numbers 1172757-1172766 are missing (a gap of 10 stamps with no associated data). This occurred during a rollback operation around block 906456.

## Root Cause
The bug was caused by incorrect ordering of operations in the `purge_block_db` function:

1. **Before Fix**: 
   - `clear_all_caches()` was called FIRST
   - Then database stamps were deleted
   - When new stamps were processed, `get_next_stamp_number()` queried MAX(stamp) from database
   - But the stamps being rolled back were still in the database!
   - This caused the stamp counter to continue from the wrong (higher) number

2. **The Problem Flow**:
   ```
   1. Database has stamps 1-1000
   2. Rollback initiated to remove stamps 991-1000
   3. clear_all_caches() called - stamp counter cache cleared
   4. New stamp requested - queries MAX(stamp) = 1000 (stamps not deleted yet!)
   5. New stamp assigned number 1001
   6. Database stamps 991-1000 finally deleted
   7. Result: Gap of stamps 991-1000 with no data
   ```

## Fix Applied
The fix reorders operations in `purge_block_db`:
1. Delete stamps from database FIRST
2. Clear caches AFTER all database operations complete

This ensures the stamp counter is recalculated from the correct database state.

## Files Changed
- `src/index_core/database.py`: Moved `clear_all_caches()` to end of `purge_block_db()`
- `src/index_core/blocks.py`: Removed duplicate `clear_all_caches()` call
- `tests/test_rollback_stamp_numbering.py`: Added comprehensive tests

## Test Coverage
Three test cases were added:
1. `test_stamp_counter_after_rollback`: Verifies stamp numbers continue correctly after rollback
2. `test_cache_cleared_after_database_operations`: Ensures proper operation ordering
3. `test_cursed_stamp_counter_after_rollback`: Tests cursed stamp numbering

## Prevention
- Always clear caches AFTER database state changes, never before
- Test rollback scenarios with stamp number continuity checks
- Monitor for gaps in stamp numbers as an early warning sign

## Impact
This bug could cause:
- Gaps in stamp numbers (stamps with no data)
- Consensus issues between nodes
- Data integrity problems in production

## Deployment Notes
After deploying this fix:
1. Monitor stamp number allocation closely
2. Check for any new gaps forming
3. Consider a one-time audit of existing stamp number gaps
4. The existing gap (1172757-1172766) in production will remain and needs separate handling