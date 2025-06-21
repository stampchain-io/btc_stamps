# Node Health Bug Fix

## Problem

There's a bug in the node health checking logic where nodes get stuck in an "unhealthy" state even when they're actually working fine.

The issue is in `src/index_core/node_health.py` in the `update_healthy_nodes()` function around lines 627-633:

```python
# Only exclude nodes with significant persistent issues
# Allow 1-2 consecutive failures if they just passed a health check
if node_health.consecutive_failures >= 3 or node_health.minor_failures >= 5:
    logger.warning(
        f"Node {node_name} passed health check but has persistent issues "
        f"(consecutive: {node_health.consecutive_failures}, minor: {node_health.minor_failures}). "
        f"Excluding from healthy nodes list."
    )
    is_healthy = False
```

The problem is that when a node passes the health check, its failure counters should be reset BEFORE checking if it should be excluded. Currently, the `mark_success()` is called after this check, so healthy nodes remain excluded.

## Temporary Workaround

Run the reset script:
```bash
poetry run python tools/reset_node_health.py
```

This will reset the failure counters for all nodes.

## Proper Fix

In `node_health.py`, the `update_healthy_nodes()` function should be modified to reset counters when a node passes health checks:

```python
if is_healthy:
    # Reset the node's failure counters since it's healthy
    node_health = node_health_tracker.get(node_name)
    if node_health:
        # Reset counters first
        node_health.mark_success()
        
        # Now check if we should still exclude it (this check becomes unnecessary)
        if not node_health.can_retry():
            logger.debug(f"Node {node_name} is in backoff period, excluding from healthy nodes")
            is_healthy = False
```

## Root Cause

The Counterparty API workaround works fine, but the node health system was incorrectly marking healthy nodes as failed due to accumulated failure counts that weren't being reset properly.

## Testing

After applying the fix or workaround:
1. Check that `counterparty-primary` appears in the healthy nodes list
2. The indexer should resume normal operation
3. No more "No healthy nodes found" errors should appear