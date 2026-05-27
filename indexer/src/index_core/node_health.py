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
        self._last_health_update_time = 0.0  # Cooldown for health update thread spawning
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
        # 503 "Counterparty not ready" means node is catching up - treat as minor, not severe
        # The node just needs time to parse blocks
        if "503" in error_info or "Counterparty not ready" in error_info:
            return False  # Minor failure - will retry normally

        # 429 "Too Many Requests" means we're being rate limited - treat as minor
        # The node is healthy, we just need to slow down
        if "429" in error_info or "Too Many Requests" in error_info:
            return False  # Minor failure - progressive backoff, not exponential

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

        # IMPROVED TIMEOUT HANDLING: Treat timeouts as severe after 2 consecutive timeout failures
        # This enables proper failover when a node is persistently timing out
        if "timeout" in error_info.lower() or "Timeout" in error_info:
            # If we already have 2 or more minor failures (indicating persistent issues), treat as severe
            if self.minor_failures >= 2:
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
                    # Rate-limited to at most once per 30 seconds to prevent thread storms
                    if self.minor_failures >= 5:
                        now = time.time()
                        if now - self._last_health_update_time >= 30:
                            self._last_health_update_time = now
                            logger.warning(f"Node {self.name} has persistent issues, triggering health update")
                            try:
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

            # Check if this node should be tested (new or backoff expired)
            node_health = node_health_tracker.get(node_name)
            if not node_health:
                # Initialize health tracker for new node
                node_health_tracker[node_name] = NodeHealth(node_name, node_url)
                node_health = node_health_tracker[node_name]

            # IMPORTANT: Check if we should retry a failed node
            if node_health.consecutive_failures > 0:
                if not node_health.can_retry():
                    # Still in backoff period, skip checking
                    logger.debug(f"Node {node_name} still in backoff period, skipping health check")
                    continue
                else:
                    # Backoff expired - retry this node
                    logger.info(f"Node {node_name} backoff period expired, attempting recovery check")

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
                                # Check server_ready flag if present (backward compatible)
                                # If flag is explicitly False, node is not ready
                                # If flag is missing or True, assume node is ready
                                server_ready = data.get("result", {}).get("server_ready")
                                if server_ready is False:
                                    logger.debug(f"Node {node_name} responded but server_ready=False")
                                    is_healthy = False
                                else:
                                    is_healthy = True
                                    logger.debug(f"Node {node_name} is healthy via root V2 endpoint")
                        except Exception as e:
                            logger.debug(f"Error parsing root V2 response from {node_name}: {e}")
                    elif response.status_code == 503:
                        # Explicit handling of 503 "not ready" responses
                        logger.debug(f"Node {node_name} returned 503 Not Ready - marking as unhealthy")
                        is_healthy = False

                if is_healthy:
                    # Update the NodeHealth tracker FIRST if it exists
                    node_health = node_health_tracker.get(node_name)
                    if node_health:
                        # IMPORTANT: Always mark success when health check passes
                        # This resets failure counters and allows recovery
                        try:
                            node_health.mark_success()
                            logger.info(f"Node {node_name} health check succeeded - marked as healthy")
                        except Exception as e:
                            logger.debug(f"Error updating health tracker for {node_name}: {e}")
                    else:
                        # Initialize health tracker
                        node_health_tracker[node_name] = NodeHealth(node_name, node_url)
                        node_health = node_health_tracker[node_name]

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
        logger.debug(f"Health check summary: {nodes_healthy}/{nodes_checked} nodes are healthy")

        if healthy_nodes_local:
            # Try to acquire lock, but don't block
            lock_acquired = False
            try:
                lock_acquired = healthy_nodes_lock.acquire(timeout=1)
                if lock_acquired:
                    healthy_nodes = healthy_nodes_local
                    logger.debug(f"Updated healthy nodes: {[n['name'] for n in healthy_nodes_local]}")
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

    # Testing override: when FORCE_PUBLIC_CP_API is set, exclude every
    # local-loopback / private-network node so all traffic exercises the
    # public api.counterparty.io path. Used in non-prod environments to
    # validate rate-limit behavior against the real CDN.
    if config.FORCE_PUBLIC_CP_API:
        public_only = [n for n in config.XCP_V2_NODES if "api.counterparty.io" in n.get("url", "").lower()]
        if public_only:
            logger.debug(f"FORCE_PUBLIC_CP_API=true → routing to {len(public_only)} public node(s) only")
            return public_only
        logger.warning("FORCE_PUBLIC_CP_API=true but no public node configured — falling through to normal routing")

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
                        # Check if node can be retried (backoff period expired)
                        if not node_health.can_retry():
                            logger.debug(f"Excluding {node_name}: still in backoff period")
                            continue

                        # IMPORTANT: If backoff expired but node has failures,
                        # it should be included to give it a chance to recover
                        # Only exclude if it has very recent failures (within last minute)
                        if node_health.consecutive_failures > 0:
                            # Check how recent the last failure was
                            time_since_failure = time.time() - node_health.last_failure_time
                            if time_since_failure < 60:  # Less than 1 minute
                                logger.debug(f"Excluding {node_name}: recent failure {time_since_failure:.1f}s ago")
                                continue
                            else:
                                logger.debug(f"Including {node_name}: failures are old enough to retry")

                        # Allow minor failures as they might be transient
                        if node_health.minor_failures >= 5:  # Increased threshold
                            logger.debug(f"Excluding {node_name}: has {node_health.minor_failures} minor failures")
                            continue

                    # Node passed all health checks
                    result.append(node)

                logger.debug(f"Found {len(result)} healthy nodes after filtering (from {len(cached_nodes)} cached)")
            finally:
                healthy_nodes_lock.release()
    except Exception as e:
        logger.error(f"Error accessing healthy_nodes: {e}")

    # If no healthy nodes, try to update them (but respect backoff periods)
    if not result:
        logger.warning("No healthy nodes after filtering, forcing health update")

        # Only update, don't reset counters - let backoff periods expire naturally
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
        # Try up to len(nodes) times to find a truly healthy node
        attempts = 0
        max_attempts = len(nodes)

        while attempts < max_attempts:
            # Get current node
            current_index = _round_robin_index % len(nodes)
            node = nodes[current_index]
            node_name = node.get("name", "unknown")

            # Advance to next node for next iteration
            _round_robin_index = (_round_robin_index + 1) % len(nodes)
            attempts += 1

            # Double-check node health before returning
            node_health = node_health_tracker.get(node_name)
            if node_health:
                # Check if node is truly healthy (not in backoff, no severe failures)
                # Allow nodes with 1 minor failure to still be used
                if node_health.can_retry() and node_health.consecutive_failures == 0 and node_health.minor_failures < 2:
                    logger.debug(f"Round-robin selected healthy node: {node_name} (index: {current_index})")
                    return node
                else:
                    logger.debug(
                        f"Round-robin skipping unhealthy node: {node_name} (consecutive_failures={node_health.consecutive_failures}, minor_failures={node_health.minor_failures}, can_retry={node_health.can_retry()})"
                    )
                    continue
            else:
                # No health tracker, assume healthy
                logger.debug(f"Round-robin selected node without health tracker: {node_name} (index: {current_index})")
                return node

        # All nodes appear unhealthy
        logger.error("Round-robin: All nodes appear unhealthy after checking")
        return None


def persist_counterparty_versions():
    """Persist current Counterparty node versions to DB."""
    from index_core.database import upsert_node_version
    from index_core.database_manager import db_manager
    from index_core.fetch_utils import fetch_node_version_v2

    db = db_manager.connect()
    try:
        for node in config.NODES:
            node_name = node.get("name", "unknown")
            node_url = node.get("url", "")
            try:
                version, version_info = fetch_node_version_v2(node_url)
                if not version or not version_info:
                    logger.debug(f"Could not fetch version for CP node {node_name}")
                    continue

                upsert_node_version(
                    db,
                    component_name=f"counterparty:{node_name}",
                    version_string=version,
                    version_major=version_info.get("version_major"),
                    version_minor=version_info.get("version_minor"),
                    version_revision=version_info.get("version_revision"),
                    extra_info={
                        "last_block": version_info.get("last_block"),
                        "last_message_index": version_info.get("last_message_index"),
                        "network": version_info.get("network"),
                        "server_ready": version_info.get("server_ready"),
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to persist version for CP node {node_name}: {e}")
    finally:
        db.close()


def persist_bitcoin_core_version():
    """Persist current Bitcoin Core version to DB."""
    from index_core.database import upsert_node_version
    from index_core.database_manager import db_manager

    network_info = Backend().getnetworkinfo()
    if not network_info:
        logger.debug("Could not fetch Bitcoin Core network info")
        return

    version_int = network_info.get("version", 0)
    major = version_int // 10000
    minor = (version_int % 10000) // 100
    revision = version_int % 100
    version_string = f"{major}.{minor}.{revision}"

    db = db_manager.connect()
    try:
        upsert_node_version(
            db,
            component_name="bitcoin_core",
            version_string=version_string,
            version_major=major,
            version_minor=minor,
            version_revision=revision,
            extra_info={
                "subversion": network_info.get("subversion"),
                "protocolversion": network_info.get("protocolversion"),
                "connections": network_info.get("connections"),
            },
        )
    finally:
        db.close()


def persist_indexer_version():
    """Persist current indexer version to DB."""
    import re

    from index_core.database import upsert_node_version
    from index_core.database_manager import db_manager

    version_string = config.VERSION_STRING
    if not version_string:
        return

    match = re.match(r"(\d+)\.(\d+)\.(\d+)(?:\+(.+))?", version_string)
    if not match:
        logger.warning(f"Could not parse indexer version: {version_string}")
        return

    major, minor, revision, suffix = int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4)

    db = db_manager.connect()
    try:
        upsert_node_version(
            db,
            component_name="stamps_indexer",
            version_string=version_string,
            version_major=major,
            version_minor=minor,
            version_revision=revision,
            version_suffix=suffix,
        )
    finally:
        db.close()


def persist_all_versions():
    """Persist all component versions. Each component is independent — one failure won't block others."""
    for name, func in [
        ("bitcoin_core", persist_bitcoin_core_version),
        ("counterparty", persist_counterparty_versions),
        ("stamps_indexer", persist_indexer_version),
    ]:
        try:
            func()
        except Exception as e:
            logger.warning(f"Failed to persist {name} version: {e}")
