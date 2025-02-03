import asyncio
import concurrent.futures
import logging
import threading
import time
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional, Union

import aiohttp
import requests
from ratelimit import limits, sleep_and_retry

import config
import index_core.server as server
from index_core.backend import Backend
from index_core.base64_utils import parse_base64_from_description

logger = logging.getLogger(__name__)


# Initialize global variables
# Node health tracking
class NodeHealth:
    def __init__(self, name: str, url: str):
        """Initialize node health tracking."""
        self.name = name
        self.url = url
        self.failures = 0
        self.consecutive_failures = 0
        self.last_failure_time = 0
        self.backoff_until = 0
        self.version: Optional[str] = None
        self.version_info: Optional[Dict] = None
        self._lock = threading.Lock()

    @property
    def healthy(self) -> bool:
        """Return whether the node is currently considered healthy."""
        with self._lock:
            return self.consecutive_failures == 0 and self.can_retry()

    def mark_failure(self):
        """Mark a node failure and calculate backoff time."""
        with self._lock:
            current_time = time.time()
            self.failures += 1
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

    def mark_success(self):
        """Mark a successful node operation."""
        with self._lock:
            if self.consecutive_failures > 0:
                logger.info(f"Node {self.name} recovered after {self.consecutive_failures} failures")
            self.consecutive_failures = 0
            self.backoff_until = 0

    def can_retry(self) -> bool:
        """Check if enough time has passed to retry this node."""
        with self._lock:
            if self.backoff_until == 0:
                return True

            current_time = time.time()
            can_retry = current_time >= self.backoff_until

            if can_retry and self.consecutive_failures > 0:
                logger.debug(f"Node {self.name} backoff period ended, allowing retry")

            return can_retry

    def update_version(self, version: str, version_info: Dict):
        """Update node version information."""
        with self._lock:
            self.version = version
            self.version_info = version_info
            if version:
                logger.info(f"Node {self.name} version updated to {version}")

    def get_stats(self) -> Dict:
        """Get current node health statistics."""
        with self._lock:
            return {
                "name": self.name,
                "url": self.url,
                "total_failures": self.failures,
                "consecutive_failures": self.consecutive_failures,
                "last_failure": (
                    datetime.fromtimestamp(self.last_failure_time).strftime("%Y-%m-%d %H:%M:%S")
                    if self.last_failure_time
                    else None
                ),
                "backoff_until": (
                    datetime.fromtimestamp(self.backoff_until).strftime("%Y-%m-%d %H:%M:%S") if self.backoff_until else None
                ),
                "version": self.version,
                "status": "available" if self.can_retry() else "backoff",
            }


backend_instance = Backend()
healthy_nodes_lock = Lock()
node_health_tracker: Dict[str, NodeHealth] = {}
healthy_nodes = []


class CPBlocksPipeline:
    """Background worker to continuously fetch CP blocks ahead of time"""

    def __init__(self, max_queue_size=200):
        self.queue = {}  # Dictionary to store fetched blocks
        self.max_queue_size = max_queue_size
        self.current_block = None
        self.worker_thread = None
        self.shutdown_flag = threading.Event()
        self._lock = threading.Lock()
        self.last_fetch_time = 0
        self.fetch_interval = 2
        self.initial_blocks_ready = threading.Event()
        self.initial_batch_size = 25
        self.target_queue_size = 100
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.fetch_future = None

    def start(self, start_block):
        """Start the background worker thread"""
        if start_block is None:
            raise ValueError("start_block must be provided")

        if start_block < config.CP_STAMP_GENESIS_BLOCK:
            logger.warning(f"Start block {start_block} is before CP genesis block {config.CP_STAMP_GENESIS_BLOCK}")
            start_block = config.CP_STAMP_GENESIS_BLOCK

        self.current_block = start_block
        self.worker_thread = threading.Thread(target=self._fetch_blocks_worker, daemon=True)
        self.worker_thread.start()
        logger.debug(f"Started CP blocks pipeline from block {start_block}")

        # Wait for initial batch of blocks
        if not self.wait_for_initial_blocks(timeout=30):
            logger.warning("Timeout waiting for initial blocks, continuing anyway")

    def wait_for_initial_blocks(self, timeout=30):
        """Wait for the initial batch of blocks to be ready"""
        return self.initial_blocks_ready.wait(timeout=timeout)

    def stop(self):
        """Stop the background worker thread"""
        if self.worker_thread and self.worker_thread.is_alive():
            self.shutdown_flag.set()
            self.worker_thread.join(timeout=10)
            logger.info("Stopped CP blocks pipeline")

    def reset(self, new_start_block):
        """Reset the pipeline to start from a new block after reorg"""
        logger.info(f"Resetting CP blocks pipeline to block {new_start_block}")
        self.stop()
        with self._lock:
            self.queue.clear()
            self.current_block = new_start_block
            self.last_fetch_time = 0
        self.shutdown_flag.clear()
        self.initial_blocks_ready.clear()
        self.worker_thread = threading.Thread(target=self._fetch_blocks_worker, daemon=True)
        self.worker_thread.start()
        logger.info(f"Restarted CP blocks pipeline from block {new_start_block}")

        # Wait for initial batch of blocks after reset
        if not self.wait_for_initial_blocks(timeout=30):
            logger.warning("Timeout waiting for initial blocks after reset, continuing anyway")

    def get_block(self, block_index):
        """Get a block from the queue, returns None if not available"""
        with self._lock:
            block_data = self.queue.get(block_index)
            if block_data:
                # Ensure issuances are sorted by tx_index
                if "issuances" in block_data:
                    block_data["issuances"] = sorted(block_data["issuances"], key=lambda x: x.get("tx_index", 0) if x else 0)
                else:
                    block_data["issuances"] = []

                # Remove older blocks to prevent memory growth
                old_blocks = [k for k in self.queue.keys() if k < block_index]
                if old_blocks:
                    logger.debug(f"Removing {len(old_blocks)} older blocks from queue (before block {block_index})")
                    for old_block in old_blocks:
                        self.queue.pop(old_block, None)

                logger.debug(f"Retrieved block {block_index} from pipeline queue (queue size: {len(self.queue)})")
            else:
                logger.debug(f"Block {block_index} not found in pipeline queue (queue size: {len(self.queue)})")
                if self.queue:
                    queue_keys = sorted(self.queue.keys())
                    logger.debug(
                        f"Queue contains blocks: {queue_keys[:5]}{'...' if len(queue_keys) > 5 else ''} (showing first 5 of {len(queue_keys)})"
                    )
            return block_data

    def _fetch_blocks_worker(self):
        """Background worker that continuously fetches blocks"""
        initial_fetch = True
        consecutive_errors = 0
        max_consecutive_errors = 3

        # Ensure nodes are healthy before starting
        if not update_healthy_nodes():
            logger.error("No healthy nodes available, cannot start fetching")
            self.initial_blocks_ready.set()  # Set this to prevent hanging
            return

        while not self.shutdown_flag.is_set():
            try:
                current_time = time.time()

                # Rate limit fetching (except for initial batch)
                if not initial_fetch and current_time - self.last_fetch_time < self.fetch_interval:
                    time.sleep(0.1)
                    continue

                # Get current blockchain tip
                block_tip = backend_instance.getblockcount()
                if block_tip is None:
                    logger.warning("Could not get block tip, retrying in 5 seconds...")
                    time.sleep(5)
                    continue

                # Calculate how many blocks to fetch
                with self._lock:
                    queue_size = len(self.queue)
                    next_block = self.current_block

                    # For initial fetch, always get the first batch
                    if initial_fetch:
                        blocks_to_fetch = min(self.initial_batch_size, block_tip - next_block + 1)
                    else:
                        # For subsequent fetches, maintain the target queue size
                        blocks_needed = max(1, self.target_queue_size - queue_size)  # Always fetch at least 1 block
                        blocks_to_fetch = min(
                            blocks_needed, block_tip - next_block + 1, 50  # Increased from 25 to 50 for better throughput
                        )
                        logger.debug(
                            f"Continuous fetch - Need {blocks_needed} blocks, will fetch {blocks_to_fetch} "
                            f"(target: {self.target_queue_size}, current: {queue_size})"
                        )

                    # Only wait if we have enough blocks AND we're not in initial fetch
                    if not initial_fetch and queue_size >= self.target_queue_size:
                        logger.debug(f"Queue has sufficient blocks ({queue_size}/{self.target_queue_size}), waiting...")
                        time.sleep(self.fetch_interval)
                        continue

                if blocks_to_fetch <= 0:
                    logger.info(f"No blocks to fetch (current: {next_block}, tip: {block_tip})")
                    time.sleep(self.fetch_interval)
                    continue

                # Submit a background fetch if none is pending
                with self._lock:
                    if self.fetch_future is None:
                        self.fetch_future = self.executor.submit(
                            fetch_xcp_blocks_concurrent, next_block, next_block + blocks_to_fetch - 1
                        )

                # Check if the background fetch task is complete
                if self.fetch_future is not None:
                    if self.fetch_future.done():
                        blocks_data = self.fetch_future.result()
                        with self._lock:
                            self.fetch_future = None
                    else:
                        time.sleep(0.1)
                        continue

                if not blocks_data:
                    consecutive_errors += 1
                    logger.error(
                        f"No blocks data received for range {next_block} to {next_block + blocks_to_fetch - 1} "
                        f"(attempt {consecutive_errors}/{max_consecutive_errors})"
                    )
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Too many consecutive errors, reinitializing node health...")
                        update_healthy_nodes()
                        consecutive_errors = 0
                    time.sleep(self.fetch_interval)
                    continue

                # Reset error counter on successful fetch
                consecutive_errors = 0

                # Store fetched blocks in queue
                with self._lock:
                    blocks_added = 0
                    for block_index, block_data in sorted(blocks_data.items()):
                        if "issuances" in block_data:
                            block_data["issuances"] = sorted(
                                block_data["issuances"], key=lambda x: (x.get("message_index", 0) if x else 0)
                            )
                        else:
                            block_data["issuances"] = []

                        self.queue[block_index] = block_data
                        blocks_added += 1
                        logger.debug(f"Added block {block_index} to queue")

                    # Update current_block to the highest fetched block + 1
                    if self.queue:
                        self.current_block = max(self.queue.keys()) + 1
                    else:
                        self.current_block = next_block + 1

                    # Signal that initial blocks are ready if we have enough blocks
                    if initial_fetch and blocks_added > 0:
                        initial_fetch = False
                        self.initial_blocks_ready.set()
                        logger.info(f"Initial batch of {blocks_added} blocks ready")

                    # Trim queue if it exceeds max size
                    if len(self.queue) > self.max_queue_size:
                        excess = len(self.queue) - self.max_queue_size
                        oldest_blocks = sorted(self.queue.keys())[:excess]
                        for block in oldest_blocks:
                            del self.queue[block]
                        logger.info(f"Trimmed {excess} old blocks from queue")

                self.last_fetch_time = time.time()

            except Exception as e:
                logger.error(f"Error in CP blocks pipeline: {e}")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many consecutive errors, reinitializing node health...")
                    update_healthy_nodes()
                    consecutive_errors = 0
                if initial_fetch:
                    initial_fetch = False
                    self.initial_blocks_ready.set()
                time.sleep(self.fetch_interval)


class RateLimiter:
    def __init__(self, calls_per_second: float = 2.0):
        self.rate = calls_per_second
        self.last_check = time.time()
        self.tokens = calls_per_second
        self._lock = threading.Lock()
        self.min_interval = 1.0 / calls_per_second

    def acquire(self, tokens: float = 1.0) -> float:
        """
        Acquire tokens and return the time to wait (if any).
        Returns 0 if request can proceed immediately.
        """
        with self._lock:
            now = time.time()
            time_passed = now - self.last_check
            self.last_check = now

            # Add new tokens based on time passed
            self.tokens = min(self.rate, self.tokens + time_passed * self.rate)

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0
            else:
                # Calculate wait time needed to accumulate required tokens
                wait_time = (tokens - self.tokens) / self.rate
                self.tokens = 0
                return wait_time


# Global rate limiter instance
cp_rate_limiter = RateLimiter(calls_per_second=5.0)  # Increased rate limit to match config


# Rate limit decorator
@sleep_and_retry
@limits(calls=config.CP_RATE_LIMIT, period=1)
def rate_limited_request(url: str, method: str = "GET", **kwargs) -> requests.Response:
    """Make a rate-limited request to the specified URL."""
    wait_time = cp_rate_limiter.acquire()
    if wait_time > 0:
        logger.debug(f"Rate limit hit, waiting {wait_time:.2f}s before request to {url}")

    try:
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for {url}: {str(e)}")
        raise


def exponential_backoff(attempt: int) -> float:
    """Calculate exponential backoff time"""
    return min(300, config.CP_BASE_DELAY * (2**attempt))  # Cap at 5 minutes


def initialize_node_health():
    """Initialize health tracking for all nodes"""
    global node_health_tracker, healthy_nodes
    with healthy_nodes_lock:
        healthy_nodes = []  # Reset healthy nodes list
        for node in config.XCP_V2_NODES:
            if node["name"] not in node_health_tracker:
                node_health_tracker[node["name"]] = NodeHealth(node["name"], node["url"])
            if check_node_health(node):
                healthy_nodes.append(node)
                logger.info(f"Added {node['name']} to healthy nodes pool")


def check_node_health(node: Dict[str, Any]) -> bool:
    """Check if a node is healthy and can be used."""
    node_name = node.get("name", "unknown")
    node_url = node.get("url", "unknown")

    if node_name not in node_health_tracker:
        node_health_tracker[node_name] = NodeHealth(node_name, node_url)

    health = node_health_tracker[node_name]

    if not health.can_retry():
        logger.info(
            f"Node {node_name} is in cooldown period until {datetime.fromtimestamp(health.backoff_until).strftime('%H:%M:%S')}"
        )
        return False

    try:
        # Construct proper healthz URL
        base_url = node_url.rstrip("/")
        health_url = f"{base_url}/healthz"

        # Make a test request to check node health
        response = requests.get(health_url, timeout=5)
        response.raise_for_status()

        # Parse response
        data = response.json()
        is_healthy = data.get("result", {}).get("status") == "Healthy"

        if is_healthy:
            health.mark_success()
            logger.info(f"Node {node_name} health check passed")
            return True
        else:
            logger.warning(f"Node {node_name} reported unhealthy status")
            health.mark_failure()
            return False

    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning(f"Health check failed for node {node_name}: {str(e)}")
        health.mark_failure()
        return False


def check_node_versions():
    """Check and compare versions across all nodes and validate against required versions."""
    from index_core.xcprequest import get_cp_version

    versions = {}
    for node in config.XCP_V2_NODES:
        node_health = node_health_tracker[node["name"]]
        # For version checking we need the base URL without /v2 but with /api/
        base_url = node["url"]
        if isinstance(base_url, str):
            base_url = base_url.replace("/v2", "")
            if not base_url.endswith("/api/"):
                base_url = base_url.rstrip("/") + "/api/"
        else:
            logger.error(f"Invalid URL format for node {node['name']}: {base_url}")
            continue

        try:
            version, version_info = get_cp_version(base_url)

            if version and version_info:
                node_health.update_version(version, version_info)
                versions[node["name"]] = {"version": version, "info": version_info}
                logger.info(f"Node {node['name']} running Counterparty version {version}")
                logger.debug(
                    f"Version details for {node['name']}: Last block={version_info['last_block']}, "
                    f"Last message index={version_info['last_message_index']}"
                )

                # Check if this node meets minimum version requirements
                try:
                    # Set temporary version values for check
                    temp_version_major = version_info["version_major"]
                    temp_version_minor = version_info["version_minor"]
                    temp_version_revision = version_info["version_revision"]

                    # Check for protocol changes that require version updates
                    for protocol_change in config.PROTOCOL_CHANGES:
                        if (
                            temp_version_major < protocol_change["minimum_version_major"]
                            or (
                                temp_version_major == protocol_change["minimum_version_major"]
                                and temp_version_minor < protocol_change["minimum_version_minor"]
                            )
                            or (
                                temp_version_major == protocol_change["minimum_version_major"]
                                and temp_version_minor == protocol_change["minimum_version_minor"]
                                and temp_version_revision < protocol_change["minimum_version_revision"]
                            )
                        ):
                            logger.warning(
                                f"Node {node['name']} version {version} is below minimum required "
                                f"v{protocol_change['minimum_version_major']}."
                                f"{protocol_change['minimum_version_minor']}."
                                f"{protocol_change['minimum_version_revision']} "
                                f"(required as of block {protocol_change['block_index']})"
                            )
                            node_health.mark_failure()

                except Exception as e:
                    logger.error(f"Error checking version requirements for node {node['name']}: {e}")
                    node_health.mark_failure()

            else:
                logger.warning(f"Could not get version info for node {node['name']}")
                node_health.mark_failure()

        except Exception as e:
            logger.error(f"Error getting version info for node {node['name']}: {e}")
            node_health.mark_failure()

    # Compare versions between nodes
    if len(versions) > 1:
        version_set = {v["version"] for v in versions.values()}
        if len(version_set) > 1:
            logger.warning("Version mismatch detected between nodes:")
            for node_name, v in versions.items():
                logger.warning(
                    f"  - {node_name}: {v['version']} "
                    f"(Last block: {v['info']['last_block']}, "
                    f"Last message: {v['info']['last_message_index']})"
                )

            # Find highest version node
            highest_version = max(
                versions.items(),
                key=lambda x: (x[1]["info"]["version_major"], x[1]["info"]["version_minor"], x[1]["info"]["version_revision"]),
            )
            logger.info(
                f"Using highest version node as reference: {highest_version[0]} " f"(v{highest_version[1]['version']})"
            )

            # Mark nodes with significantly lower versions as unhealthy
            for node_name, v in versions.items():
                version_diff = (
                    highest_version[1]["info"]["version_major"] - v["info"]["version_major"],
                    highest_version[1]["info"]["version_minor"] - v["info"]["version_minor"],
                )
                if version_diff[0] > 0 or (version_diff[0] == 0 and version_diff[1] > 1):
                    logger.warning(
                        f"Node {node_name} version is significantly behind highest version node. " f"Marking as unhealthy."
                    )
                    node_health_tracker[node_name].mark_failure()

    return versions


def update_healthy_nodes():
    """Update the list of healthy nodes."""
    global healthy_nodes

    with healthy_nodes_lock:
        healthy_nodes = [node for node in config.XCP_V2_NODES if check_node_health(node)]

        if not healthy_nodes:
            logger.warning("No healthy nodes available! Will retry nodes after their cooldown periods.")
            # Force reset cooldown on all nodes if none are available
            for node_name, health in node_health_tracker.items():
                if health.consecutive_failures > 3:
                    logger.info(f"Resetting cooldown for node {node_name} due to no healthy nodes")
                    health.consecutive_failures = 3  # Reset to shorter backoff
                    health.backoff_until = time.time() + exponential_backoff(3)

    # Log healthy nodes status
    if not healthy_nodes:
        logger.error("No healthy nodes available. All configured nodes failed health check:")
        for node in config.XCP_V2_NODES:
            logger.error(f"  - {node['name']}: {node['url']}")
    else:
        total_nodes = len(config.XCP_V2_NODES)
        healthy_count = len(healthy_nodes)
        logger.info(f"Health check complete: {healthy_count}/{total_nodes} nodes healthy")
        logger.info(f"Healthy nodes: {[n['name'] for n in healthy_nodes]}")
        if healthy_nodes:
            primary_node = healthy_nodes[0]
            node_health = node_health_tracker[primary_node["name"]]
            version_info = f" (v{node_health.version})" if node_health.version else ""
            logger.info(f"Using primary node: {primary_node['name']}{version_info} ({primary_node['url']})")

    return len(healthy_nodes) > 0


def fetch_xcp(endpoint: str, params: Optional[Dict[str, Any]] = None, node: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch data from XCP V2 API."""
    global healthy_nodes

    if not healthy_nodes:
        update_healthy_nodes()

    nodes_to_try = [node] if node else healthy_nodes.copy()
    last_error = None
    tried_nodes = []

    for node in nodes_to_try:
        url = f"{node['url']}{endpoint}"
        try:
            logger.debug(f"Attempting to fetch from {node['name']} at URL: {url}")
            response = requests.get(url, params=params, timeout=10)
            logger.error(f"Response status from {node['name']}: {response.status_code}")

            if response.ok:
                data = response.json()
                logger.info(f"Successful response from {node['name']}")
                return data
            else:
                error_body = response.text
                logger.warning(f"Error response from {node['name']}: {error_body}")
                last_error = f"HTTP {response.status_code}: {error_body}"
        except Exception as e:
            logger.error(f"Fetch error for {node['name']} at {url}: {e}")
            last_error = str(e)
            with healthy_nodes_lock:
                if node in healthy_nodes:
                    healthy_nodes.remove(node)
                    logger.warning(f"Node {node['name']} removed from healthy nodes. Error: {e}")
                    if not healthy_nodes:
                        logger.warning("No healthy nodes remaining, updating node list...")
                        update_healthy_nodes()
        tried_nodes.append(node["name"])
        continue

    # If we get here, all nodes failed
    nodes_tried = ", ".join(tried_nodes)
    logger.error(f"Failed to fetch data from all available nodes ({nodes_tried}). Last error: {last_error}")
    return {
        "result": [],
        "next_cursor": None,
        "result_count": 0,
    }


def find_issuance_by_tx_hash(issuances, tx_hash):
    """Filter issuances by transaction hash and return the first match."""
    filtered_issuances = [issuance for issuance in issuances if issuance["tx_hash"] == tx_hash]
    return filtered_issuances[0] if filtered_issuances else None


def split_into_chunks(lst: List[Any], n: int) -> Iterator[List[Any]]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def get_xcp_asset(cpid: str, node: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Get details of a single CP asset by its CPID."""
    endpoint = f"/assets/{cpid}"
    logger.info(f"Fetching XCP asset for CPID: {cpid} using node {node['name'] if node else 'default nodes'}")
    try:
        response = fetch_xcp(endpoint, node=node)
        if not response or not isinstance(response, dict) or "result" not in response:
            logger.error(f"Invalid response for asset {cpid}: {response}")
            return None

        logger.info(f"Fetched XCP asset for CPID: {cpid}")
        return response["result"]
    except Exception as e:
        logger.error(f"Error fetching asset info for cpid {cpid}: {e}")
        return None


def get_xcp_assets_by_cpids(
    cpids: List[str], chunk_size: int = 200, delay_between_chunks: int = 6, max_workers: int = 5
) -> List[Dict[str, Any]]:
    """Get details for multiple CP assets by their CPIDs."""
    assets_details = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for cpid_chunk in split_into_chunks(cpids, chunk_size):
            future = executor.submit(fetch_xcp_assets_details, cpid_chunk)
            futures.append(future)
            time.sleep(delay_between_chunks)

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                assets_details.extend(result)

    return assets_details


def fetch_xcp_assets_details(cpid_chunk: List[str]) -> List[Dict[str, Any]]:
    """Fetch details for a chunk of CP assets."""
    assets_details = []
    for cpid in cpid_chunk:
        logger.info(f"Fetching asset detail for CPID: {cpid}")
        asset_detail = get_xcp_asset(cpid)
        if asset_detail:
            assets_details.append(asset_detail)
        else:
            logger.warning(f"No asset detail found for CPID: {cpid}")
    return assets_details


def calculate_batch_size(current_index: int, tip: int, min_size: int = 3, max_size: int = 100) -> int:
    """
    Calculate optimal batch size based on distance to tip.

    Args:
        current_index: Current block index
        tip: Target block index (tip)
        min_size: Minimum batch size
        max_size: Maximum batch size

    Returns:
        int: Optimal batch size for the current distance
    """
    distance = tip - current_index
    if distance <= min_size:
        return min_size
    elif distance <= 10:
        return min(distance, 5)
    elif distance <= 50:
        return min(distance, 10)
    elif distance <= 200:
        return min(distance, 25)
    else:
        return min(distance, max_size)


async def process_blocks(results_dict, current_block_index, block_tip, process_callback):
    """Process blocks in chunks with proper error handling and retries."""
    while current_block_index <= block_tip:
        if server.shutdown_flag.is_set():
            logger.info("Shutdown flag detected, stopping block processing")
            break

        blocks_to_fetch = calculate_batch_size(current_block_index, block_tip)
        end_block = min(current_block_index + blocks_to_fetch - 1, block_tip)

        try:
            start_time = time.time()
            blocks_data = await asyncio.wait_for(
                get_all_xcp_transactions(current_block_index, end_block - current_block_index + 1), timeout=30.0
            )
            elapsed_time = time.time() - start_time
            logger.debug(f"get_all_xcp_transactions completed in {elapsed_time:.2f} seconds")

            if blocks_data:
                for block in blocks_data:
                    if block:
                        block_idx = block["block_index"]
                        results_dict[block_idx] = block
                        if process_callback:
                            logger.debug(f"Running process_callback for block {block_idx}")
                            process_callback(block)
                            await asyncio.sleep(0)

            current_block_index = end_block + 1
            logger.debug(f"Advanced current_block_index to {current_block_index}")

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching blocks {current_block_index} to {end_block}, retrying with smaller batch")
            # Reduce batch size more aggressively
            blocks_to_fetch = max(1, blocks_to_fetch // 4)
            # Don't advance block_index on timeout
            await asyncio.sleep(2)  # Longer delay before retry
            continue
        except asyncio.CancelledError:
            logger.info("Block processing cancelled")
            raise
        except Exception as e:
            logger.error(f"Error processing blocks {current_block_index} to {end_block}: {e}")
            # On error, advance by 1 block instead of the whole batch
            current_block_index += 1
            await asyncio.sleep(1)
            continue
    return current_block_index


def fetch_xcp_blocks_concurrent(block_index, block_tip, indicator=None, process_callback=None):
    """
    Fetch XCP blocks using the V2 API with asynchronous concurrency using asyncio.
    This implementation fetches blocks individually to ensure we get the exact blocks we need.
    """
    try:
        logger.debug(f"Starting XCP block fetching from {block_index} to {block_tip}")

        # Create event loop if one doesn't exist
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        results_dict = {}
        current_block_index = block_index  # Create a mutable reference

        async def process_blocks(results_dict, current_block_index, block_tip, process_callback):
            """Process blocks in chunks with proper error handling and retries."""
            while current_block_index <= block_tip:
                if server.shutdown_flag.is_set():
                    logger.info("Shutdown flag detected, stopping block processing")
                    break

                blocks_to_fetch = calculate_batch_size(current_block_index, block_tip)
                end_block = min(current_block_index + blocks_to_fetch - 1, block_tip)

                try:
                    start_time = time.time()
                    blocks_data = await asyncio.wait_for(
                        get_all_xcp_transactions(current_block_index, end_block - current_block_index + 1), timeout=30.0
                    )
                    elapsed_time = time.time() - start_time
                    logger.debug(f"get_all_xcp_transactions completed in {elapsed_time:.2f} seconds")

                    if blocks_data:
                        logger.debug(f"Received {len(blocks_data)} blocks from get_all_xcp_transactions")
                        for block in blocks_data:
                            if block:
                                block_idx = block["block_index"]
                                results_dict[block_idx] = block
                                if process_callback:
                                    logger.debug(f"Running process_callback for block {block_idx}")
                                    process_callback(block)
                                    await asyncio.sleep(0)

                    current_block_index = end_block + 1
                    logger.debug(f"Advanced current_block_index to {current_block_index}")

                except asyncio.TimeoutError:
                    logger.warning(
                        f"Timeout fetching blocks {current_block_index} to {end_block}, retrying with smaller batch"
                    )
                    # Reduce batch size more aggressively
                    blocks_to_fetch = max(1, blocks_to_fetch // 4)
                    # Don't advance block_index on timeout
                    await asyncio.sleep(2)  # Longer delay before retry
                    continue
                except asyncio.CancelledError:
                    logger.info("Block processing cancelled")
                    raise
                except Exception as e:
                    logger.error(f"Error processing blocks {current_block_index} to {end_block}: {e}")
                    # On error, advance by 1 block instead of the whole batch
                    current_block_index += 1
                    await asyncio.sleep(1)
                    continue
            return current_block_index

        try:
            # Run the async processing with proper task cleanup
            main_task = loop.create_task(process_blocks(results_dict, current_block_index, block_tip, process_callback))
            loop.run_until_complete(main_task)
            return dict(sorted(results_dict.items()))

        except asyncio.CancelledError:
            logger.info("Block processing cancelled in main loop")
            raise
        except Exception as e:
            logger.error(f"Error in fetch_xcp_blocks_concurrent: {e}")
            raise
        finally:
            # Properly clean up all tasks
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    logger.debug(f"Cleaning up {len(pending)} pending tasks")
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    # Wait for cancellation to complete with timeout
                    loop.run_until_complete(asyncio.wait(pending, timeout=5, return_when=asyncio.ALL_COMPLETED))
            except Exception as cleanup_error:
                logger.error(f"Error during task cleanup: {cleanup_error}")

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        raise
    except Exception as e:
        logger.error(f"Error in fetch_xcp_blocks_concurrent: {e}")
        raise


def parse_xcp_block_transactions(block_data):
    """Parse transactions from XCP V2 API format into the expected issuances format."""
    if not block_data:
        return []

    issuances = []
    for block in block_data:
        transactions = block.get("transactions", [])

        # Sort transactions by message_index first, then by tx_hash for consistent ordering
        transactions.sort(key=lambda x: x.get("message_index", 0))

        for tx in transactions:
            tx_hash = tx.get("tx_hash")
            tx_type = tx.get("transaction_type")
            logger.debug(f"Processing transaction {tx_hash} of type {tx_type}")

            # Only process issuance transactions
            if tx_type not in ["issuance", "fairminter"]:
                continue

            # Find ASSET_ISSUANCE or FAIRMINT event
            issuance_event = None
            for event in tx.get("events", []):
                event_type = event.get("event")
                if event_type in ["ASSET_ISSUANCE", "FAIRMINT"]:
                    logger.debug(f"Found {event_type} event in tx {tx_hash}")
                    issuance_event = event
                    break

            if issuance_event:
                issuance = parse_issuance_from_transaction(tx, issuance_event)
                if issuance:
                    issuances.append(issuance)
                else:
                    logger.debug(f"Issuance parsed as None for tx {tx_hash}")
            else:
                logger.debug(f"No ASSET_ISSUANCE or FAIRMINT event found in tx {tx_hash}")

    # Sort issuances by message_index first, then by tx_hash for consistent ordering
    issuances.sort(key=lambda x: x.get("message_index", 0))
    return issuances


def parse_issuance_from_transaction(tx, issuance_event):
    """Parse issuance data from an XCP transaction."""
    try:
        tx_hash = tx.get("tx_hash")
        event_type = issuance_event.get("event")
        params = issuance_event.get("params", {})
        cpid = params.get("asset")

        # Handle FAIRMINT events differently
        if event_type == "NEW_FAIRMINT":
            description = "FAIRMINT"  # FAIRMINT events have a fixed description
            quantity = params.get("earn_quantity", 0)
            divisible = params.get("asset_info", {}).get("divisible")
            locked = params.get("asset_info", {}).get("locked")
            issuer = params.get("asset_info", {}).get("issuer")
        else:
            # Regular ASSET_ISSUANCE event
            description = params.get("description", "").strip()
            quantity = params.get("quantity")
            divisible = params.get("divisible")
            locked = params.get("locked")
            issuer = params.get("issuer")

        # Enhanced validation for stamp issuances
        if description is not None and description.lower().find("stamp:") != -1 and params.get("status") == "valid":
            # Extract base64 and mimetype
            _, stamp_mimetype = parse_base64_from_description(description)

            issuance_data = {
                "cpid": cpid,
                "quantity": quantity,
                "divisible": divisible,
                "locked": locked,
                "source": tx.get("source"),
                "issuer": issuer,
                "transfer": params.get("transfer"),
                "description": description,
                "reset": params.get("reset"),
                "status": params.get("status"),
                "asset_longname": params.get("asset_longname"),
                "tx_hash": tx_hash,
                "message_index": issuance_event.get("event_index"),
                "stamp_mimetype": stamp_mimetype,
                "event_type": event_type,
                "block_index": tx.get("block_index"),
                "block_time": tx.get("block_time"),
            }

            if event_type == "NEW_FAIRMINT":
                issuance_data.update(
                    {
                        "commission": params.get("commission", 0),
                        "earn_quantity": params.get("earn_quantity"),
                        "paid_quantity": params.get("paid_quantity", 0),
                        "fairminter_tx_hash": params.get("fairminter_tx_hash"),
                    }
                )

            return issuance_data
        else:
            logger.debug(f"STAMP validation failed for description: '{description}'")
            logger.debug(f"Description is None: {description is None}")
            if description is not None:
                logger.debug(f"STAMP: position: {description.lower().find('stamp:')}")
            return None

    except Exception as e:
        logger.error(f"Error parsing issuance for tx {tx.get('tx_hash')}: {e}")
        return None


def get_xcp_block_hash(block_index: int, limit: Optional[int] = None) -> Optional[Union[str, Dict[int, Optional[str]]]]:
    """Get block hash using XCP V2 API."""
    try:
        if limit is None or limit == 1:
            endpoint = f"/blocks/{block_index}"
            params = {"verbose": "true", "show_unconfirmed": "false"}
            response = fetch_xcp(endpoint, params=params)

            if not response or not isinstance(response, dict):
                logger.error(f"Invalid response format for block {block_index}")
                return None

            result = response.get("result")
            if not result or not isinstance(result, dict):
                logger.error(f"Block {block_index} not found in XCP V2 response")
                return None

            return result.get("block_hash")
        else:
            endpoint = "/blocks"
            params = {
                "cursor": str(block_index),
                "limit": str(limit) if limit is not None else None,
                "verbose": "true",
                "show_unconfirmed": "false",
            }
            response = fetch_xcp(endpoint, params=params)

            if not response or not isinstance(response, dict):
                logger.error(f"Invalid response format for blocks starting at {block_index} with limit {limit}")
                return None

            results = response.get("result")
            if not results or not isinstance(results, list):
                logger.error(f"No blocks found in response starting at {block_index} with limit {limit}")
                return None

            block_hashes = {}
            for block in results:
                idx = block.get("block_index")
                blk_hash = block.get("block_hash")
                if idx is not None:
                    block_hashes[idx] = blk_hash

            return block_hashes
    except Exception as e:
        logger.error(f"Error getting block hash via XCP V2: {e}")
        return None


def verify_cp_block_hash(block_index: int, expected_hash: str | None = None, max_retries: int = 5) -> bool:
    """Verify XCP node's block hash matches expected hash."""
    retry_count = 0
    base_delay = 2  # seconds

    while retry_count < max_retries:
        try:
            cp_hash = get_xcp_block_hash(block_index)
            if not cp_hash:
                logger.warning(f"Empty CP hash for block {block_index}, retrying...")
                raise ValueError("Empty hash from CP node")

            chain_hash = expected_hash if expected_hash is not None else backend_instance.getblockhash(block_index)

            if cp_hash != chain_hash:
                logger.error(f"Block hash mismatch at {block_index}")
                logger.error(f"CP Hash:    {cp_hash}")
                logger.error(f"Chain Hash: {chain_hash}")
                return False

            logger.debug(f"Hash verification passed for block {block_index}")
            return True

        except Exception as e:
            logger.warning(f"Block hash verification failed (attempt {retry_count+1}/{max_retries}): {str(e)}")
            retry_count += 1
            time.sleep(base_delay * (2**retry_count))

    logger.error("Max retries reached in block hash verification")
    return False


async def get_xcp_transactions_async(
    block_index: int, cursor: Optional[str] = None, limit: int = 1000
) -> Optional[Dict[str, Any]]:
    """Async version of get_xcp_transactions."""
    try:
        endpoint = f"/blocks/{block_index}/transactions"
        params = {"verbose": "true", "show_unconfirmed": "false", "limit": limit}

        if cursor:
            params["cursor"] = cursor

        response = await fetch_xcp_async(endpoint, params=params)

        if not response or not isinstance(response, dict):
            logger.error(f"Invalid response format for block {block_index} transactions")
            return None

        result = response.get("result")
        if not isinstance(result, list):
            logger.error(f"No transactions found in response for block {block_index}")
            return None

        return {"result": result, "next_cursor": response.get("next_cursor"), "result_count": len(result)}

    except Exception as e:
        logger.error(f"Error getting transactions via XCP V2: {e}")
        return None


async def get_all_xcp_transactions(start_block: int, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
    """Get transactions for multiple XCP blocks."""
    try:
        logger.debug(f"get_all_xcp_transactions started for blocks {start_block} to {start_block + limit - 1}")
        complete_blocks = []
        chunk_size = 10  # Increased chunk size for better throughput
        tasks = []
        max_retries = 3
        base_chunk_timeout = 15  # Increased base timeout

        async def process_chunk(chunk_tasks, attempt=0):
            """Process a chunk of tasks with retry logic"""
            logger.debug(f"Processing chunk of {len(chunk_tasks)} tasks, attempt {attempt + 1}")
            chunk_timeout = base_chunk_timeout * (2**attempt)  # Exponential backoff for timeouts
            try:
                # Create a task group for the chunk
                start_time = time.time()
                chunk_results = await asyncio.wait_for(
                    asyncio.gather(*chunk_tasks, return_exceptions=True), timeout=chunk_timeout
                )
                elapsed_time = time.time() - start_time
                logger.debug(f"Chunk tasks completed in {elapsed_time:.2f} seconds")

                # Process results immediately
                successful_results = []
                failed_count = 0
                for result in chunk_results:
                    if isinstance(result, Exception):
                        if not isinstance(result, asyncio.CancelledError):
                            logger.error(f"Error in block fetch: {result}")
                        failed_count += 1
                    elif result is not None:
                        successful_results.append(result)

                logger.debug(f"Chunk processed: {len(successful_results)} successful, {failed_count} failed")

                # Check if we need to retry due to too many failures
                if failed_count > len(chunk_results) / 2 and attempt < max_retries:
                    logger.warning(f"Too many failures in chunk ({failed_count}/{len(chunk_results)}), retrying...")
                    await asyncio.sleep(1 * (2**attempt))
                    return await process_chunk(chunk_tasks, attempt + 1)

                return successful_results

            except asyncio.TimeoutError:
                logger.error(f"Chunk processing timed out after {chunk_timeout}s, attempt {attempt + 1}/{max_retries}")
                # Cancel existing tasks
                for t in chunk_tasks:
                    if not t.done():
                        t.cancel()
                try:
                    await asyncio.gather(*chunk_tasks, return_exceptions=True)
                except Exception:
                    pass

                # Retry with increased timeout if not exceeded max retries
                if attempt < max_retries:
                    await asyncio.sleep(1 * (2**attempt))
                    return await process_chunk(chunk_tasks, attempt + 1)
                return []

            except asyncio.CancelledError:
                logger.info("Chunk processing cancelled")
                raise

            finally:
                # Ensure all tasks are properly cleaned up
                for t in chunk_tasks:
                    if not t.done():
                        t.cancel()

        # Process blocks in chunks
        current_block = start_block
        while current_block < start_block + limit:
            if server.shutdown_flag.is_set():
                logger.info("Shutdown flag detected, stopping block fetching")
                break

            # Create tasks for current chunk
            chunk_end = min(current_block + chunk_size, start_block + limit)
            tasks = [asyncio.create_task(fetch_single_block(idx)) for idx in range(current_block, chunk_end)]

            try:
                # Process current chunk
                chunk_results = await process_chunk(tasks)
                if chunk_results:
                    complete_blocks.extend(chunk_results)

                # Update progress
                current_block = chunk_end

                # Small delay between chunks to prevent overwhelming the nodes
                await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                logger.info("Block fetching tasks cancelled")
                # Cleanup any remaining tasks
                for t in tasks:
                    if not t.done():
                        t.cancel()
                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except Exception:
                    pass
                raise

            except Exception as e:
                logger.error(f"Error processing chunk starting at block {current_block}: {e}")
                # Move to next chunk even if current chunk failed
                current_block = chunk_end
                continue

        # Sort blocks by index before returning
        complete_blocks.sort(key=lambda x: x["block_index"])
        return complete_blocks

    except asyncio.CancelledError:
        logger.info("Block fetching cancelled")
        raise
    except Exception as e:
        logger.error(f"Error getting blocks via XCP V2: {e}")
        return None


async def fetch_xcp_async(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Async version of fetch_xcp."""
    global healthy_nodes

    try:
        logger.debug(f"fetch_xcp_async started for endpoint {endpoint}")
        start_time = time.time()

        # Initialize node health if not already done
        if not healthy_nodes:
            logger.info("Initializing node health in fetch_xcp_async")
            initialize_node_health()

        if not healthy_nodes:
            logger.warning("No healthy nodes available after initialization")
            return None

        tried_nodes = []
        last_error = None
        retry_count = 0
        max_retries = int(config.CP_MAX_RETRIES)  # Ensure integer
        base_timeout = float(config.CP_RPC_TIMEOUT)  # Ensure float

        for node in healthy_nodes:
            if node["name"] not in node_health_tracker:
                logger.warning(f"Node {node['name']} not in health tracker, initializing...")
                node_health_tracker[node["name"]] = NodeHealth(node["name"], node["url"])

            node_health = node_health_tracker[node["name"]]
            if not node_health.can_retry():
                logger.info(f"Skipping node {node['name']} (in cooldown period)")
                continue

            url = f"{node['url']}{endpoint}"
            current_timeout = float(base_timeout * (2**retry_count))  # Ensure float for timeout
            timeout = aiohttp.ClientTimeout(total=current_timeout)
            try:
                logger.debug(f"Attempting request to {url} with timeout {current_timeout}s")
                request_start = time.time()
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params) as response:
                        request_time = time.time() - request_start
                        logger.debug(f"Request to {url} completed in {request_time:.2f}s with status {response.status}")

                        if response.status == 200:
                            try:
                                json_response = await response.json()
                                node_health.mark_success()
                                elapsed_time = time.time() - start_time
                                logger.debug(f"fetch_xcp_async for {endpoint} completed successfully in {elapsed_time:.2f}s")
                                return json_response
                            except Exception as e:
                                logger.error(f"Error parsing JSON from {url}: {e}")
                                node_health.mark_failure()
                                last_error = e
                        else:
                            error_text = await response.text()
                            logger.error(f"Error response from {url}: {response.status} - {error_text}")
                            node_health.mark_failure()
                            last_error = RuntimeError(f"HTTP {response.status}: {error_text}")
            except asyncio.TimeoutError:
                logger.error(f"Timeout connecting to {url} after {current_timeout}s")
                node_health.mark_failure()
                last_error = asyncio.TimeoutError(f"Timeout connecting to {url}")
            except Exception as e:
                logger.error(f"Error connecting to {url}: {e}")
                node_health.mark_failure()
                last_error = e

            tried_nodes.append(node["name"])
            retry_count += 1

            if retry_count >= max_retries:
                logger.error(f"Exceeded maximum retries ({max_retries}) for endpoint {endpoint}")
                break

        # If we've tried all nodes and still failed, log the error
        if tried_nodes:
            logger.error(f"All nodes failed for endpoint {endpoint}: {', '.join(tried_nodes)}")

        elapsed_time = time.time() - start_time
        logger.error(f"fetch_xcp_async for {endpoint} failed after {elapsed_time:.2f}s")
        return None

    except asyncio.CancelledError:
        logger.info(f"fetch_xcp_async for {endpoint} was cancelled")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in fetch_xcp_async for {endpoint}: {e}")
        return None


async def fetch_single_block(idx):
    """Fetch a single block and its transactions from the XCP API"""
    try:
        if server.shutdown_flag.is_set():
            logger.debug(f"Skipping block {idx} due to shutdown signal")
            return None

        # Fetch block metadata and transactions concurrently
        async def fetch_block_data():
            logger.debug(f"Fetching block data for block {idx}")
            start_time = time.time()
            endpoint = f"/blocks/{idx}"
            params = {"verbose": "true", "show_unconfirmed": "false"}
            result = await fetch_xcp_async(endpoint, params=params)
            elapsed_time = time.time() - start_time
            logger.debug(f"Block data fetch for block {idx} completed in {elapsed_time:.2f} seconds")
            return result

        async def fetch_block_transactions():
            logger.debug(f"Fetching transactions for block {idx}")
            start_time = time.time()
            tx_endpoint = f"/blocks/{idx}/transactions"
            all_transactions = []
            next_cursor = None
            params = {"verbose": "true", "show_unconfirmed": "false", "limit": 1000}  # Increased limit

            while True:
                if next_cursor:
                    params["cursor"] = next_cursor

                logger.debug(f"Fetching transactions page for block {idx} with cursor: {next_cursor}")
                response = await fetch_xcp_async(tx_endpoint, params=params)
                if not response or not isinstance(response, dict):
                    logger.warning(f"Invalid response format for transactions in block {idx}")
                    break

                transactions = response.get("result", [])
                if not transactions:
                    logger.debug(f"No transactions found in page for block {idx}")
                    break

                logger.debug(f"Fetched {len(transactions)} transactions for block {idx}")
                all_transactions.extend(transactions)
                next_cursor = response.get("next_cursor")
                if not next_cursor:
                    logger.debug(f"No more pages for transactions in block {idx}")
                    break

                # Small delay between pagination requests
                await asyncio.sleep(0.1)

            elapsed_time = time.time() - start_time
            logger.debug(
                f"Transaction fetch for block {idx} completed in {elapsed_time:.2f} seconds with {len(all_transactions)} transactions"
            )
            return all_transactions

        # Fetch block data and transactions concurrently
        start_time = time.time()
        block_data_task = asyncio.create_task(fetch_block_data())
        transactions_task = asyncio.create_task(fetch_block_transactions())

        try:
            # Wait for both tasks with timeout
            block_response, transactions = await asyncio.wait_for(
                asyncio.gather(block_data_task, transactions_task, return_exceptions=True),
                timeout=30,  # 30 second timeout for the entire block fetch
            )
            elapsed_time = time.time() - start_time
            logger.debug(f"Concurrent fetch for block {idx} completed in {elapsed_time:.2f} seconds")
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching block {idx} data")
            for task in [block_data_task, transactions_task]:
                if not task.done():
                    task.cancel()
            return None

        # Check for exceptions in results
        if isinstance(block_response, Exception):
            logger.error(f"Error fetching block {idx} metadata: {block_response}")
            return None
        if isinstance(transactions, Exception):
            logger.error(f"Error fetching block {idx} transactions: {transactions}")
            return None

        if not block_response or not isinstance(block_response, dict):
            logger.error(f"Invalid response format for block {idx}")
            return None

        block_data = block_response.get("result")
        if not block_data:
            logger.error(f"No data found for block {idx}")
            return None

        if server.shutdown_flag.is_set():
            return None

        # Add transactions to block data
        block_data["transactions"] = transactions or []

        # Parse transactions for this block
        try:
            issuances = parse_xcp_block_transactions([block_data])
            logger.debug(f"Parsed {len(issuances)} issuances for block {idx}")

            # Sort issuances by message_index
            issuances = sorted(issuances, key=lambda x: (x.get("message_index", 0) if x else 0))

            return {"block_index": idx, "xcp_block_hash": block_data.get("block_hash"), "issuances": issuances}
        except Exception as e:
            logger.error(f"Error parsing transactions for block {idx}: {e}")
            return None

    except asyncio.CancelledError:
        logger.debug(f"Block {idx} fetch cancelled")
        raise
    except Exception as e:
        logger.error(f"Error fetching block {idx}: {e}")
        return None


def fetch_remaining_blocks_async(*args, **kwargs):
    """
    Launches fetch_xcp_blocks_concurrent in a daemon thread.
    """
    # Strip out any db parameter from kwargs since fetch_xcp_blocks_concurrent doesn't accept it
    if "db" in kwargs:
        del kwargs["db"]

    thread = threading.Thread(target=fetch_xcp_blocks_concurrent, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
