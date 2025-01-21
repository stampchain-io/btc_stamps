# Data Deduplication for Bitcoin Stamps Files

## Overview

The Bitcoin Stamps Indexer stores files (primarily SVGs and images) in AWS S3, which are then served via Cloudflare CDN. Many of these files, especially SRC-20 mints, are identical in content but stored with different filenames based on their transaction hashes. This document outlines the implementation of content-based deduplication to optimize storage and delivery.

## Current Storage Pattern

Currently, files are stored in S3 with the following pattern:
- Path: `{AWS_S3_IMAGE_DIR}/{tx_hash}.{suffix}`
- Each unique transaction gets its own file, even if the content is identical
- File mapping is tracked in the `s3objects` table

## Deduplication Strategy

The new strategy uses content-based addressing while maintaining transaction-based access:
1. Store files using their MD5 hash as the filename
2. Use Cloudflare Workers to redirect requests from transaction-based URLs to content-based URLs
3. Store and maintain mappings in Cloudflare KV for fast lookups

### Benefits

- Reduced S3 storage costs
- Improved cache hit rates
- Better content organization
- Maintained backward compatibility
- Fast edge-based redirects

## Implementation Steps

### 1. Export Existing Mappings

Create a script to export tx_hash to MD5 mappings from the database:

```python
# tools/export_mappings.py
import json
from typing import Dict
import mysql.connector
from config import DB_CONFIG

def generate_mapping_data() -> Dict[str, str]:
    """
    Generate mapping data from s3objects table.
    Returns dict with {tx_hash.suffix: md5.suffix} format
    """
    db = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor()
    cursor.execute("""
        SELECT 
            SUBSTRING_INDEX(path_key, '/', -1) as filename,
            md5
        FROM s3objects
    """)
    
    mappings = {}
    for filename, md5 in cursor:
        if '.' in filename:
            tx_hash, suffix = filename.rsplit('.', 1)
            mappings[filename] = f"{md5}.{suffix}"
    
    cursor.close()
    db.close()
    return mappings

def export_mappings():
    """Export mappings to JSON file for Cloudflare KV import"""
    mappings = generate_mapping_data()
    with open('file_mappings.json', 'w') as f:
        json.dump(mappings, f)
    print(f"Exported {len(mappings)} mappings to file_mappings.json")

if __name__ == "__main__":
    export_mappings()
```

### 2. Set Up Cloudflare KV and Worker

```bash
# Install Wrangler CLI if not already installed
npm install -g wrangler

# Login to Cloudflare
wrangler login

# Create KV namespace
wrangler kv:namespace create "FILE_MAPPINGS"

# Bulk upload mappings
wrangler kv:bulk put --namespace-id=<your-namespace-id> file_mappings.json
```

### 3. Create Cloudflare Worker

```javascript
// workers/file-redirect/index.js
export default {
    async fetch(request, env) {
        const url = new URL(request.url)
        const filename = url.pathname.split('/').pop()
        
        // Skip if not a file request
        if (!filename || !filename.includes('.')) {
            return fetch(request)
        }
        
        // Look up canonical path in KV
        const canonicalPath = await env.FILE_MAPPINGS.get(filename)
        if (!canonicalPath) {
            return fetch(request)
        }
        
        // Construct new URL with content-addressed path
        const newUrl = new URL(url)
        newUrl.pathname = `/${env.S3_IMAGE_DIR}/${canonicalPath}`
        
        // Return permanent redirect
        return Response.redirect(newUrl.toString(), 301)
    }
}
```

### 4. Configure Worker

```toml
# wrangler.toml
name = "file-redirect"
main = "src/index.js"
compatibility_date = "2024-01-01"
kv_namespaces = [
    { binding = "FILE_MAPPINGS", id = "your-namespace-id" }
]
[vars]
S3_IMAGE_DIR = "your_image_dir"
```

### 5. Update File Upload Logic

```python:indexer/src/index_core/aws.py
def check_existing_and_upload_to_s3(db, filename, mime_type, file_obj, file_obj_md5):
    """Store files using content-based addressing"""
    try:
        # Extract suffix from filename
        suffix = filename.rsplit('.', 1)[1] if '.' in filename else ''
        
        # Use MD5 as filename
        content_path = f"{config.AWS_S3_IMAGE_DIR}{file_obj_md5}.{suffix}"
        
        # Check if content already exists
        if not content_exists_in_s3(content_path):
            upload_file_to_s3(
                file_obj,
                config.AWS_S3_BUCKETNAME,
                content_path,
                config.AWS_S3_CLIENT,
                content_type=mime_type
            )
        
        # Update KV mapping
        update_cloudflare_mapping(filename, f"{file_obj_md5}.{suffix}")
        
        return file_obj_md5, filename
        
    except Exception as e:
        logger.error(f"Error in S3 upload: {e}")
        raise
```

### 6. Add KV Update Function

```python:indexer/src/index_core/cloudflare.py
import asyncio
from typing import Optional
import aiohttp

async def update_cloudflare_mapping(
    tx_filename: str,
    content_filename: str,
    cf_account_id: str = config.CF_ACCOUNT_ID,
    cf_namespace_id: str = config.CF_KV_NAMESPACE_ID,
    cf_api_token: str = config.CF_API_TOKEN
) -> None:
    """
    Update Cloudflare KV mapping for a file
    Args:
        tx_filename: Original filename with tx_hash (e.g., "tx_hash.svg")
        content_filename: Content-addressed filename (e.g., "md5hash.svg")
    """
    url = f"https://api.cloudflare.com/client/v4/accounts/{cf_account_id}/storage/kv/namespaces/{cf_namespace_id}/values/{tx_filename}"
    headers = {
        "Authorization": f"Bearer {cf_api_token}",
        "Content-Type": "text/plain",
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.put(url, headers=headers, data=content_filename) as response:
            if response.status != 200:
                error_data = await response.text()
                logger.error(f"Failed to update Cloudflare KV: {error_data}")
                raise Exception(f"Cloudflare KV update failed: {response.status}")
```

## Migration Process

1. **Backup Current Data**
   ```bash
   # Backup s3objects table
   mysqldump -u user -p btc_stamps s3objects > s3objects_backup.sql
   ```

2. **Export Current Mappings**
   ```bash
   python tools/export_mappings.py
   ```

3. **Upload Mappings to Cloudflare KV**
   ```bash
   wrangler kv:bulk put --namespace-id=<your-namespace-id> file_mappings.json
   ```

4. **Deploy Cloudflare Worker**
   ```bash
   cd workers/file-redirect
   wrangler deploy
   ```

5. **Update DNS/Routes**
   - Configure your domain to route file requests through the worker

## Monitoring and Maintenance

### Monitoring Metrics
- Monitor Cloudflare Worker performance in the dashboard
- Track KV usage and limits
- Monitor S3 storage usage
- Track redirect response times

### Regular Maintenance
- Periodically clean up unused content-addressed files
- Verify KV mappings are in sync with database
- Monitor and update worker configuration as needed

## Troubleshooting

### Common Issues

1. **Missing Mappings**
   - Check if mapping exists in KV
   - Verify original file exists in S3
   - Check worker logs for errors

2. **Slow Redirects**
   - Monitor worker CPU time
   - Check KV response times
   - Verify Cloudflare caching settings

3. **Storage Issues**
   - Monitor S3 bucket size
   - Track duplicate content
   - Verify file cleanup processes

## Configuration

### Required Environment Variables
```env
CF_ACCOUNT_ID=your_account_id
CF_KV_NAMESPACE_ID=your_namespace_id
CF_API_TOKEN=your_api_token
AWS_S3_IMAGE_DIR=your_image_dir
```

### Batch Processing
- Implement batch updates for KV mappings
- Add bulk file migration tools

### Performance Optimization
- Cache frequently accessed mappings
- Optimize worker routing logic

### Monitoring
- Add detailed metrics tracking
- Implement automated testing

### Recovery
- Add automated backup procedures
- Implement failover mechanisms
```
