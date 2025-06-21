import logging
import threading
import time
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

import requests

import config
from index_core.backend import Backend

logger = logging.getLogger(__name__)

# Global shutdown flag for communication with other modules
_shutdown_requested = threading.Event()

# Registry for shutdown callbacks
_shutdown_callbacks: List[Callable] = []
_callbacks_lock = threading.Lock()


def register_shutdown_callback(callback: Callable) -> None:
    """
    Register a callback function to be called when shutdown is requested.
    The callback should accept no arguments and can return any value (which will be ignored).

    Args:
        callback: Function to call on shutdown
    """
    with _callbacks_lock:
        if callback not in _shutdown_callbacks:
            _shutdown_callbacks.append(callback)
            logger.debug(f"Registered shutdown callback: {callback.__name__}")

            # If shutdown was already requested, immediately call the callback
            if _shutdown_requested.is_set():
                logger.debug(f"Shutdown already in progress, immediately calling callback: {callback.__name__}")
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Error executing late shutdown callback {callback.__name__}: {e}")


def unregister_shutdown_callback(callback: Callable) -> None:
    """
    Unregister a previously registered callback function.

    Args:
        callback: Function to remove from callback list
    """
    with _callbacks_lock:
        if callback in _shutdown_callbacks:
            _shutdown_callbacks.remove(callback)
            logger.debug(f"Unregistered shutdown callback: {callback.__name__}")


def is_shutdown_requested():
    """Check if shutdown has been requested."""
    return _shutdown_requested.is_set()


def set_shutdown_flag():
    """
    Set the shutdown flag and notify all registered callbacks.
    Called from outside this module (e.g., blocks.py or signal_handlers.py)
    """
    if not _shutdown_requested.is_set():
        logger.info("Setting shutdown flag and notifying all components")
        _shutdown_requested.set()

        # Notify all registered callbacks
        callbacks_to_execute = []
        with _callbacks_lock:
            callbacks_to_execute = _shutdown_callbacks.copy()

        for callback in callbacks_to_execute:
            try:
                logger.debug(f"Executing shutdown callback: {callback.__name__}")
                callback()
            except Exception as e:
                logger.error(f"Error executing shutdown callback {callback.__name__}: {e}")


def clear_shutdown_flag():
    """Clear the shutdown flag - called from outside this module (e.g., blocks.py)"""
    _shutdown_requested.clear()


# Node health tracking
class NodeHealth:
    def __init__(self, name: str, url: str):
        """Initialize node health tracking."""
        self.name = name
        self.url = url
        self.failures = 0
        self.consecutive_failures = 0
        self.last_failure_time = 0.0  # Changed from int to float
        self.backoff_until = 0.0  # Changed from int to float
        self.version: Optional[str] = None
        self.version_info: Optional[Dict] = None
        self._lock = threading.Lock()
        self.minor_failures = 0  # Track less severe failures separately
        # Add missing attributes
        self.last_success = 0.0
        self.total_successes = 0
        self.total_failures = 0

    @property
    def healthy(self) -> bool:
        """Return whether the node is currently considered healthy."""
        # Make a thread-safe copy of values to avoid holding lock during evaluation
        with self._lock:
            consecutive_failures = self.consecutive_failures
            backoff_until = self.backoff_until

        current_time = time.time()
        # A node is healthy if it has no consecutive failures and is not in backoff
        return consecutive_failures == 0 and current_time >= backoff_until

    def is_severe_failure(self, error_info: str) -> bool:
        """
        Determine if an error should be counted as a severe failure.
        Some errors like 404 for recent blocks are expected and shouldn't trigger backoff.
        """
        # If the error is a 404 for a block at/near the chain tip, don't count it as severe
        if "404" in error_info and "Block not yet processed by XCP" in error_info:
            return False

        # If it's a 404 for a block somewhat near the tip (within 5 blocks), treat as minor
        if "404" in error_info and "despite being " in error_info:
            try:
                # Extract the number of blocks from tip from the error message
                blocks_from_tip = int(error_info.split("despite being ")[1].split(" blocks from tip")[0])
                if blocks_from_tip <= 5:
                    return False
            except Exception:
                # If parsing fails, default to treating it as severe
                pass

        # IMPROVED TIMEOUT HANDLING: Treat timeouts as severe after multiple consecutive timeout failures
        # This enables proper failover when a node is persistently timing out
        if "timeout" in error_info.lower() or "Timeout" in error_info:
            # If we already have multiple minor failures (indicating persistent issues), treat as severe
            if self.minor_failures >= 3:
                logger.warning(f"Node {self.name} has {self.minor_failures} timeout failures, treating as severe")
                return True
            return False

        # Treat connection errors as minor failures initially, but severe after multiple failures
        if "connection" in error_info.lower() or "Connection" in error_info:
            if self.minor_failures >= 2:
                logger.warning(f"Node {self.name} has {self.minor_failures} connection failures, treating as severe")
                return True
            return False

        # Treat server disconnection errors as minor failures initially
        if "serverdisconnectederror" in error_info.lower() or "server disconnected" in error_info.lower():
            if self.minor_failures >= 2:
                logger.warning(f"Node {self.name} has {self.minor_failures} disconnection failures, treating as severe")
                return True
            return False

        return True

    def mark_failure(self, error_info: str = ""):
        """
        Mark a node failure and calculate backoff time.

        Args:
            error_info: Information about the error to help determine severity
        """
        # Use a shorter timeout for lock acquisition
        lock_acquired = False
        try:
            lock_acquired = self._lock.acquire(timeout=1)
            if not lock_acquired:
                logger.warning(f"Could not acquire lock for {self.name} in mark_failure - operation skipped")
                return

            current_time = time.time()
            self.failures += 1
            self.total_failures += 1

            # Determine if this is a severe failure or a minor one
            if self.is_severe_failure(error_info):
                self.consecutive_failures += 1
                self.last_failure_time = current_time

                # Calculate backoff time using exponential backoff
                backoff = exponential_backoff(self.consecutive_failures)
                self.backoff_until = current_time + backoff

                logger.warning(
                    f"Node {self.name} marked as failed. "
                    f"Consecutive failures: {self.consecutive_failures}, "
                    f"Backoff until: {datetime.fromtimestamp(self.backoff_until).strftime('%H:%M:%S')}"
                )
            else:
                # For minor failures, increment counter and apply progressive backoff
                self.minor_failures += 1

                # Apply progressive backoff for persistent minor failures
                if self.minor_failures >= 3:
                    # Calculate progressive backoff: 5s, 15s, 30s, 60s, then cap at 120s
                    backoff_seconds = min(120, 5 * (self.minor_failures - 2) * 2)
                    self.backoff_until = current_time + backoff_seconds
                    logger.warning(
                        f"Node {self.name} has {self.minor_failures} minor failures. "
                        f"Progressive backoff of {backoff_seconds}s until: {datetime.fromtimestamp(self.backoff_until).strftime('%H:%M:%S')}"
                    )

                    # Trigger immediate health update to ensure other components use backup nodes
                    if self.minor_failures >= 5:
                        logger.warning(f"Node {self.name} has persistent issues, triggering health update")
                        try:
                            # Import here to avoid circular imports
                            import threading

                            # Update health in a separate thread to not block
                            threading.Thread(target=update_healthy_nodes, daemon=True).start()
                        except Exception as health_update_error:
                            logger.error(f"Failed to trigger health update: {health_update_error}")
        except Exception as e:
            logger.error(f"Error in mark_failure for {self.name}: {e}")
        finally:
            # Make sure we release the lock if we have it
            if lock_acquired:
                try:
                    self._lock.release()
                except Exception as e:
                    logger.error(f"Error releasing lock in mark_failure for {self.name}: {e}")

    def mark_success(self):
        """Mark a successful node operation."""
        lock_acquired = False
        try:
            lock_acquired = self._lock.acquire(timeout=1)
            if not lock_acquired:
                logger.warning(f"Could not acquire lock for {self.name} in mark_success - operation skipped")
                return

            if self.consecutive_failures > 0:
                logger.info(f"Node {self.name} recovered after {self.consecutive_failures} failures")
            self.consecutive_failures = 0
            self.minor_failures = 0  # Reset minor failures too
            self.backoff_until = 0
            # Update success counters
            self.last_success = time.time()
            self.total_successes += 1
        except Exception as e:
            logger.error(f"Error in mark_success for {self.name}: {e}")
        finally:
            # Make sure we release the lock if we have it
            if lock_acquired:
                try:
                    self._lock.release()
                except Exception as e:
                    logger.error(f"Error releasing lock in mark_success for {self.name}: {e}")

    def can_retry(self) -> bool:
        """Check if enough time has passed to retry this node."""
        # Read values outside of lock to avoid deadlock
        lock_acquired = False
        try:
            lock_acquired = self._lock.acquire(timeout=1)
            if not lock_acquired:
                logger.warning(f"Could not acquire lock for {self.name} in can_retry - assuming retry is possible")
                return True

            backoff_until = self.backoff_until
            consecutive_failures = self.consecutive_failures
        except Exception as e:
            logger.error(f"Error accessing node health data for {self.name}: {e}")
            # Default to allowing retry on error
            return True
        finally:
            if lock_acquired:
                try:
                    self._lock.release()
                except Exception as e:
                    logger.error(f"Error releasing lock in can_retry for {self.name}: {e}")

        if backoff_until == 0:
            return True

        current_time = time.time()
        can_retry = current_time >= backoff_until

        # Only log if node is coming out of backoff and had failures
        if can_retry and consecutive_failures > 0:
            logger.debug(f"Node {self.name} backoff period ended, allowing retry")

        return can_retry

    def update_version(self, version: str, version_info: Dict):
        """Update node version information."""
        lock_acquired = False
        try:
            lock_acquired = self._lock.acquire(timeout=1)
            if not lock_acquired:
                logger.warning(f"Could not acquire lock for {self.name} in update_version - operation skipped")
                return

            self.version = version
            self.version_info = version_info.copy()
            logger.debug(f"Updated version info for node {self.name} to {version}")
        except Exception as e:
            logger.error(f"Error in update_version for {self.name}: {e}")
        finally:
            if lock_acquired:
                try:
                    self._lock.release()
                except Exception as e:
                    logger.error(f"Error releasing lock in update_version for {self.name}: {e}")

    def get_stats(self) -> Dict:
        """Get statistics about this node's health"""
        stats = {
            "name": self.name,
            "url": self.url,
            "healthy": False,
            "version": None,
            "consecutive_failures": 0,
            "backoff_until": 0,
            "last_success": 0,
            "total_successes": 0,
            "total_failures": 0,
            "failures": 0,
            "minor_failures": 0,
        }

        lock_acquired = False
        try:
            lock_acquired = self._lock.acquire(timeout=1)
            if lock_acquired:
                try:
                    # Get all values while holding the lock to avoid deadlock with healthy property
                    consecutive_failures = self.consecutive_failures
                    backoff_until = self.backoff_until
                    current_time = time.time()

                    stats.update(
                        {
                            "consecutive_failures": consecutive_failures,
                            "backoff_until": backoff_until,
                            "version": self.version,
                            "last_success": self.last_success,
                            "total_successes": self.total_successes,
                            "total_failures": self.total_failures,
                            "failures": self.failures,
                            "minor_failures": self.minor_failures,
                            # Calculate healthy status without calling self.healthy to avoid deadlock
                            "healthy": consecutive_failures == 0 and current_time >= backoff_until,
                        }
                    )
                finally:
                    self._lock.release()

            # Add time remaining in backoff if applicable
            backoff_until = float(stats.get("backoff_until", 0))  # Get and convert in one step
            if backoff_until > 0:
                now = time.time()
                if backoff_until > now:
                    stats["backoff_remaining"] = backoff_until - now

            # Format timestamps for readability
            if backoff_until > 0:
                stats["backoff_until_str"] = datetime.fromtimestamp(backoff_until).strftime("%H:%M:%S")

            last_success = float(stats.get("last_success", 0))  # Get and convert in one step
            if last_success > 0:
                stats["last_success_str"] = datetime.fromtimestamp(last_success).strftime("%H:%M:%S")
        except Exception as e:
            logger.error(f"Error getting node stats: {e}")
            # Fix the lock ownership check
            if lock_acquired:
                try:
                    self._lock.release()
                except RuntimeError:
                    # Lock was already released
                    pass

        return stats


# Initialize global variables
backend_instance = Backend()
healthy_nodes_lock = Lock()
node_health_tracker: Dict[str, NodeHealth] = {}
healthy_nodes = []

# Round-robin node selection
_round_robin_index = 0
_round_robin_lock = Lock()


def exponential_backoff(attempt: int) -> float:
    """Calculate exponential backoff time"""
    # Cap at 2 minutes instead of 5 - shorter backoff times
    return min(120, config.CP_BASE_DELAY * (2**attempt))  # Cap at 2 minutes


def initialize_node_health():
    """Initialize health tracking for all nodes"""
    global node_health_tracker, healthy_nodes  # noqa: F824 - These are assigned to within this function

    # Try to acquire lock with timeout
    lock_acquired = False
    try:
        lock_acquired = healthy_nodes_lock.acquire(timeout=2)
        if not lock_acquired:
            logger.error("Could not acquire healthy_nodes_lock for initialization - trying direct method")
            return update_healthy_nodes()

        healthy_nodes = []  # Reset healthy nodes list
        for node in config.XCP_V2_NODES:
            if node["name"] not in node_health_tracker:
                node_health_tracker[node["name"]] = NodeHealth(node["name"], node["url"])

            # Check health without blocking the global lock
            healthy_nodes_lock.release()
            lock_acquired = False

            node_healthy = check_node_health(node)

            # Re-acquire lock to update the list
            lock_acquired = healthy_nodes_lock.acquire(timeout=2)
            if not lock_acquired:
                logger.error("Could not re-acquire healthy_nodes_lock - falling back to direct method")
                return update_healthy_nodes()

            if node_healthy:
                healthy_nodes.append(node)
                logger.info(f"Added {node['name']} to healthy nodes pool")

        return len(healthy_nodes) > 0
    except Exception as e:
        logger.error(f"Error in initialize_node_health: {e}")
        # Fall back to direct method on error
        return update_healthy_nodes()
    finally:
        if lock_acquired:
            healthy_nodes_lock.release()


def check_node_health(node: Dict[str, Any]) -> bool:
    """
    Check the health of a single node by attempting to fetch its version.

    Args:
        node: A dictionary containing node details ('name', 'url').

    Returns:
        True if the node is healthy, False otherwise.
    """
    node_name = node.get("name")
    node_health = node_health_tracker.get(node_name)

    if not node_health:
        logger.debug(f"No health tracker for node {node_name}")
        return True

    try:
        # Get a local copy of the health state to avoid race conditions
        with node_health._lock:
            consecutive_failures = node_health.consecutive_failures
            backoff_until = node_health.backoff_until

        # If the node has no consecutive failures, it's healthy
        if consecutive_failures == 0:
            return True

        # If the node is in backoff, check if we can retry
        current_time = time.time()
        if backoff_until > 0 and current_time < backoff_until:
            # Still in backoff
            remaining = backoff_until - current_time
            if remaining > 10:  # Only log for longer backoffs
                logger.debug(f"Node {node_name} in backoff for {remaining:.1f} more seconds")
            return False

        # Backoff period has passed, we can retry
        logger.debug(f"Node {node_name} exiting backoff, allowing retry")
        return True

    except Exception as e:
        logger.error(f"Error checking node health for {node_name}: {e}")
        # To be safe, try to release the lock if we acquired it
        try:
            if node_health._lock:
                node_health._lock.release()
        except (RuntimeError, AttributeError):
            # Lock wasn't acquired or doesn't exist
            pass
        return True  # Assume healthy on error


def check_node_versions():
    """
    Periodically checks the versions of all configured nodes.
    Updates the node health tracker with version information.
    Uses the V2 endpoint for fetching versions.
    """
    from index_core.fetch_utils import fetch_node_version_v2

    nodes = config.NODES
    for node in nodes:
        node_name = node.get("name")
        node_url = node.get("url")
        node_health = node_health_tracker.get(node_name)

        if not node_health:
            logger.debug(f"No health tracker for node {node_name}")
            continue

        try:
            # Call the new V2 function
            version, version_info = fetch_node_version_v2(node_url)

            if version and version_info:
                node_health.update_version(version, version_info)
                logger.info(f"Node {node_name} running Counterparty version {version}")
                logger.debug(
                    f"Version details for {node_name}: Last block={version_info['last_block']}, "
                    f"Last message index={version_info['last_message_index']}"
                )

                # Check for protocol changes that require version updates
                # Make sure PROTOCOL_CHANGES exists in config first
                if hasattr(config, "PROTOCOL_CHANGES"):
                    for protocol_change in config.PROTOCOL_CHANGES:
                        if (
                            version_info["version_major"] < protocol_change["minimum_version_major"]
                            or (
                                version_info["version_major"] == protocol_change["minimum_version_major"]
                                and version_info["version_minor"] < protocol_change["minimum_version_minor"]
                            )
                            or (
                                version_info["version_major"] == protocol_change["minimum_version_major"]
                                and version_info["version_minor"] == protocol_change["minimum_version_minor"]
                                and version_info["version_revision"] < protocol_change["minimum_version_revision"]
                            )
                        ):
                            logger.warning(
                                f"Node {node_name} version {version} is below minimum required "
                                f"v{protocol_change['minimum_version_major']}."
                                f"{protocol_change['minimum_version_minor']}."
                                f"{protocol_change['minimum_version_revision']} "
                                f"(required as of block {protocol_change['block_index']})"
                            )
                            node_health.mark_failure()
                else:
                    logger.warning("No PROTOCOL_CHANGES defined in config, skipping version requirement checks")

            else:
                logger.warning(f"Could not get version info for node {node_name}")
                node_health.mark_failure()

        except Exception as e:
            logger.error(f"Error getting version info for node {node_name}: {e}")
            node_health.mark_failure()


def update_healthy_nodes():
    """Update the list of healthy nodes using a simpler, more reliable approach."""
    global healthy_nodes

    logger.debug(f"Starting update_healthy_nodes with {len(config.XCP_V2_NODES)} configured nodes")

    if not config.XCP_V2_NODES:
        logger.error("No XCP nodes configured in config.XCP_V2_NODES")
        return False

    try:
        # Use a local list to avoid lock contention
        healthy_nodes_local = []
        nodes_checked = 0
        nodes_healthy = 0

        # Check each node directly
        for node in config.XCP_V2_NODES:
            node_name = node.get("name", "unknown")
            node_url = node.get("url", "unknown")
            nodes_checked += 1

            # Skip nodes without URLs
            if not node_url:
                logger.warning(f"Node {node_name} has no URL, skipping")
                continue

            try:
                # Try healthz endpoint first, fallback to root endpoint
                health_url = f"{node_url.rstrip('/')}/healthz"
                logger.debug(f"Checking health of node {node_name} at {health_url}")

                response = requests.get(health_url, timeout=15)
                is_healthy = False

                if response.status_code == 200:
                    try:
                        data = response.json()
                        is_healthy = data.get("result", {}).get("status") == "Healthy"
                        if is_healthy:
                            logger.debug(f"Node {node_name} is healthy via /healthz endpoint")
                    except Exception as e:
                        logger.debug(f"Error parsing healthz response from {node_name}: {e}")

                # If healthz failed, try the root V2 endpoint as fallback
                if not is_healthy:
                    logger.debug(f"Healthz failed for {node_name}, trying root V2 endpoint")
                    root_url = node_url.rstrip("/")
                    response = requests.get(root_url, timeout=15)

                    if response.status_code == 200:
                        try:
                            data = response.json()
                            # Check if it looks like a valid V2 API response
                            if "result" in data and isinstance(data["result"], dict):
                                is_healthy = True
                                logger.debug(f"Node {node_name} is healthy via root V2 endpoint")
                        except Exception as e:
                            logger.debug(f"Error parsing root V2 response from {node_name}: {e}")

                if is_healthy:
                    # Update the NodeHealth tracker FIRST if it exists
                    node_health = node_health_tracker.get(node_name)
                    if node_health:
                        # Check for persistent failures before marking success
                        with node_health._lock:
                            consecutive_failures = node_health.consecutive_failures

                        # Exclude nodes with too many consecutive failures (3+)
                        if consecutive_failures >= 3:
                            logger.debug(
                                f"Node {node_name} has {consecutive_failures} consecutive failures, excluding despite health check success"
                            )
                            is_healthy = False
                        else:
                            try:
                                # Mark success to reset failure counters
                                node_health.mark_success()
                                logger.debug(f"Reset failure counters for {node_name} after successful health check")
                            except Exception as e:
                                logger.debug(f"Error updating health tracker for {node_name}: {e}")
                    else:
                        # Initialize health tracker
                        node_health_tracker[node_name] = NodeHealth(node_name, node_url)
                        node_health = node_health_tracker[node_name]

                    # Now check if we should still exclude it (backoff period or was marked unhealthy above)
                    if is_healthy and node_health and not node_health.can_retry():
                        logger.debug(f"Node {node_name} is in backoff period, excluding from healthy nodes")
                        is_healthy = False

                    if is_healthy:
                        # Add to healthy nodes list
                        healthy_nodes_local.append(node)
                        nodes_healthy += 1
                        logger.debug(f"Node {node_name} is healthy")
                else:
                    logger.debug(f"Node {node_name} failed both health checks")
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout checking health of {node_name} after 15 seconds")
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error checking health of {node_name}")
            except Exception as e:
                logger.debug(f"Error checking health of {node_name}: {e}")

                # Mark node as failed in health tracker
                if node_name in node_health_tracker:
                    try:
                        node_health_tracker[node_name].mark_failure(str(e))
                    except Exception as health_err:
                        logger.error(f"Error marking node failure: {health_err}")

        # Update the global list (no locking to avoid deadlocks)
        logger.info(f"Health check summary: {nodes_healthy}/{nodes_checked} nodes are healthy")

        if healthy_nodes_local:
            # Try to acquire lock, but don't block
            lock_acquired = False
            try:
                lock_acquired = healthy_nodes_lock.acquire(timeout=1)
                if lock_acquired:
                    healthy_nodes = healthy_nodes_local
                    logger.info(f"Updated healthy nodes: {[n['name'] for n in healthy_nodes_local]}")
                else:
                    logger.warning("Could not acquire lock to update healthy_nodes list")
            finally:
                if lock_acquired:
                    healthy_nodes_lock.release()

            return True
        else:
            logger.error("No healthy nodes found")
            return False
    except Exception as e:
        logger.error(f"Error in update_healthy_nodes: {e}")
        return False


def get_healthy_nodes():
    """Get the list of healthy nodes with improved filtering and failover logic."""

    # Create a local copy to avoid lock contention
    result = []
    try:
        logger.debug("Fetching healthy nodes list")
        if healthy_nodes_lock.acquire(timeout=1):
            try:
                # Get the cached list
                cached_nodes = healthy_nodes.copy()

                # Apply additional filtering based on node health trackers
                for node in cached_nodes:
                    node_name = node.get("name", "unknown")
                    node_health = node_health_tracker.get(node_name)

                    if node_health:
                        # Skip nodes that are in backoff or have significant persistent issues
                        if not node_health.can_retry():
                            logger.debug(f"Excluding {node_name}: in backoff period")
                            continue
                        if node_health.consecutive_failures >= 3:
                            logger.debug(f"Excluding {node_name}: has {node_health.consecutive_failures} consecutive failures")
                            continue
                        if node_health.minor_failures >= 5:
                            logger.debug(f"Excluding {node_name}: has {node_health.minor_failures} minor failures")
                            continue

                    # Node passed all health checks
                    result.append(node)

                logger.debug(f"Found {len(result)} healthy nodes after filtering (from {len(cached_nodes)} cached)")
            finally:
                healthy_nodes_lock.release()
    except Exception as e:
        logger.error(f"Error accessing healthy_nodes: {e}")

    # If no healthy nodes, try to update them (more aggressive approach)
    if not result:
        logger.warning("No healthy nodes after filtering, forcing health update")

        # Reset ALL failure counters for nodes to give them another chance
        # This prevents nodes from getting permanently stuck in failed state
        for node_health in node_health_tracker.values():
            if node_health.consecutive_failures > 0 or node_health.minor_failures > 0:
                logger.info(
                    f"Resetting failure counters for {node_health.name} "
                    f"(consecutive: {node_health.consecutive_failures}, minor: {node_health.minor_failures}) "
                    f"to allow retry"
                )
                node_health.consecutive_failures = 0
                node_health.minor_failures = 0
                node_health.backoff_until = 0

        update_healthy_nodes()
        try:
            if healthy_nodes_lock.acquire(timeout=1):
                try:
                    result = healthy_nodes.copy()
                    logger.debug(f"After forced update: found {len(result)} healthy nodes")
                finally:
                    healthy_nodes_lock.release()
        except Exception as e:
            logger.error(f"Error accessing healthy_nodes after forced update: {e}")

    # Log node details
    if result:
        logger.debug(f"Healthy nodes: {[node.get('name', 'unknown') for node in result]}")
        for node in result:
            node_name = node.get("name", "unknown")
            node_url = node.get("url", "unknown")
            logger.debug(f"Node {node_name}: URL={node_url}")
    else:
        logger.error("⚠️  NO HEALTHY NODES AVAILABLE - this will cause fetch failures")

    return result


def get_next_healthy_node_round_robin():
    """
    Get the next healthy node using round-robin selection.
    This helps distribute load across multiple nodes.

    Returns:
        A single node dict or None if no healthy nodes available
    """
    global _round_robin_index

    nodes = get_healthy_nodes()
    if not nodes:
        return None

    # Use lock to ensure thread-safe index update
    with _round_robin_lock:
        # Get current node
        node = nodes[_round_robin_index % len(nodes)]

        # Advance to next node for next call
        _round_robin_index = (_round_robin_index + 1) % len(nodes)

        logger.debug(f"Round-robin selected node: {node.get('name', 'unknown')} (index: {_round_robin_index})")

    return node
