

To clear tables for a reindex, run the following SQL replacing the block_index with the block_index of the last block you want to keep.

```sql

SET @block_index = 854359;
SET FOREIGN_KEY_CHECKS = 0;

-- Core tables
DELETE FROM transactions WHERE block_index >= @block_index;
DELETE FROM blocks WHERE block_index >= @block_index;

-- Stamp related
DELETE FROM StampTableV4 WHERE block_index >= @block_index;

-- SRC20 related
DELETE FROM SRC20 WHERE block_index >= @block_index;
DELETE FROM SRC20Valid WHERE block_index >= @block_index;
DELETE FROM balances;  -- Will be rebuilt

-- SRC101 related
DELETE FROM SRC101 WHERE block_index >= @block_index;
DELETE FROM SRC101Valid WHERE block_index >= @block_index;
DELETE FROM src101price WHERE block_index >= @block_index;
DELETE FROM recipients WHERE block_index >= @block_index;
DELETE FROM owners;  -- Will be rebuilt

SET FOREIGN_KEY_CHECKS = 1;
```
