# KEVIN Token Background Image Issue Analysis

## Problem Summary
The KEVIN token (tick) SVG image on S3 shows the default gradient background instead of the custom background from the srcbackground table.

## Root Cause
1. **S3 Cache Issue**: The `config.S3_OBJECTS` cache contains the old MD5 hash
2. **Database Issue**: The `update_s3_db_objects` function uses `INSERT IGNORE` which doesn't update existing records
3. **MD5 Comparison**: When the file already exists with a different MD5, it should upload the new version, but the cache might be stale

## Current State
- S3 File: Shows default gradient background
- MD5: 0da065b55cfa52d09332186f7c3fc8aa
- Expected: Should show custom background from srcbackground table

## Issue in Code

### aws.py line 100-102:
```python
cursor.execute(
    "INSERT IGNORE INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s)",
    (id, s3_file_path, file_obj_md5),
)
```

The `INSERT IGNORE` means if a record already exists, it won't update the MD5 hash.

### Solution Needed
Change to use `INSERT ... ON DUPLICATE KEY UPDATE` or `REPLACE INTO`:

```python
cursor.execute(
    "INSERT INTO s3objects (id, path_key, md5) VALUES (%s, %s, %s) "
    "ON DUPLICATE KEY UPDATE md5 = VALUES(md5)",
    (id, s3_file_path, file_obj_md5),
)
```

## Immediate Fix Steps
1. Fix the `update_s3_db_objects` function to update MD5 on conflict
2. Clear the S3_OBJECTS cache or restart the indexer
3. Re-process stamps that need background updates
4. Verify CloudFront invalidation happens for updated files

## Files Affected
- `/indexer/src/index_core/aws.py` - update_s3_db_objects function
- `/indexer/src/index_core/async_upload.py` - same cache check logic