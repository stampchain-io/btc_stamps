import asyncio
import concurrent.futures
import json
import logging
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union, cast

import aiohttp
import requests
from ratelimit import limits, sleep_and_retry

import config
from index_core.base64_utils import parse_base64_from_description
from index_core.node_health import (
    get_healthy_nodes,
    is_shutdown_requested,
    node_health_tracker,
    update_healthy_nodes,
)

logger = logging.getLogger(__name__)


#########################################################################
# RATE LIMITING
#########################################################################


# Rate limiter functionality
class RateLimiter:
    def __init__(self, calls_per_second: float = 2.0):
        """Initialize the rate limiter."""
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second if calls_per_second > 0 else 0
        self.last_call_time = 0.0
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> float:
        """
        Acquire permission to proceed, with rate limiting.

        Args:
            tokens: Number of tokens to acquire (affects wait time proportionally)

        Returns:
            The time waited in seconds before being allowed to proceed
        """
        wait_time = 0.0
        with self._lock:
            current_time = time.time()
            time_since_last = current_time - self.last_call_time
            required_wait = (tokens * self.min_interval) - time_since_last

            if required_wait > 0:
                wait_time = required_wait
                time.sleep(required_wait)
                self.last_call_time = current_time + required_wait
            else:
                self.last_call_time = current_time

        return wait_time


@sleep_and_retry
@limits(calls=config.CP_RATE_LIMIT, period=1)
def rate_limited_request(url: str, method: str = "GET", **kwargs) -> requests.Response:
    """Make a rate-limited request to the given URL."""
    return requests.request(method, url, **kwargs)


#########################################################################
# UTILITY FUNCTIONS
#########################################################################


def find_issuance_by_tx_hash(issuances, tx_hash):
    """Find an issuance by transaction hash."""
    if not issuances:
        return None
    for issuance in issuances:
        if issuance and issuance.get("tx_hash") == tx_hash:
            return issuance
    return None


def split_into_chunks(lst: List[Any], n: int) -> Iterator[List[Any]]:
    """Split a list into chunks of size n."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def calculate_batch_size(current_index: int, tip: int, min_size: int = 3, max_size: int = 100) -> int:
    """
    Calculate batch size for block fetching.
    Dynamically sizes batch based on how close we are to the tip of the chain.
    """
    if tip is None or current_index is None:
        return min_size

    # Determine how far we are from the tip
    blocks_remaining = max(0, tip - current_index)

    if blocks_remaining <= 0:
        # At or past the tip, use minimum batch size
        return min_size

    if blocks_remaining < 10:
        # Very close to tip, use small batch size
        return min_size

    if blocks_remaining < 50:
        # Somewhat close to tip, use moderate batch size
        return min(max_size // 4, blocks_remaining)

    if blocks_remaining < 200:
        # Moderately far from tip, use medium batch size
        return min(max_size // 2, blocks_remaining)

    # Far from tip, use large batch size but not exceeding max_size
    return min(max_size, blocks_remaining)


#########################################################################
# NODE VERSION FUNCTIONS (NEW)
#########################################################################


def fetch_node_version_v2(node_url: str, timeout: int = 5) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """
    Get Counterparty node version information from the V2 endpoint.

    Args:
        node_url: The base URL of the V2 endpoint (e.g., http://host:port/v2).
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (version_string, version_info_dict)
        version_string is in format "major.minor.revision"
        version_info_dict contains detailed version information from the V2 endpoint
    """
    if not isinstance(node_url, str) or not node_url.endswith("/v2"):
        logger.warning(f"Invalid node URL provided for V2 version check: {node_url}")
        return None, None

    try:
        logger.debug(f"Fetching V2 version info from: {node_url}")
        response = requests.get(node_url, timeout=timeout)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        # Extract info from headers
        header_version = response.headers.get("X-Counterparty-Version")
        backend_height_header = response.headers.get("X-Bitcoin-Height")
        cp_height_header = response.headers.get("X-Counterparty-Height")
        cp_ready_header = response.headers.get("X-Counterparty-Ready")
        ledger_state_header = response.headers.get("X-Ledger-State")

        # Extract info from JSON body
        body_data = response.json().get("result", {})
        body_version = body_data.get("version")
        network = body_data.get("network")
        backend_height_body = body_data.get("backend_height")
        cp_height_body = body_data.get("counterparty_height")
        ledger_state_body = body_data.get("ledger_state")
        server_ready = body_data.get("server_ready")

        # Prioritize body version, fallback to header
        version_string = body_version
        if not version_string:
            version_string = header_version
            if version_string:
                logger.info(f"Using header version '{version_string}' as body version is missing for {node_url}")
            else:
                logger.error(f"Could not extract version from header or body for {node_url}")
                return None, None
        elif header_version and version_string != header_version:
            # Log mismatch only if header exists and differs, but still proceed with body version
            logger.debug(
                f"Header version '{header_version}' differs from body version '{version_string}' for {node_url}. Using body version."
            )

        # Parse version string
        version_parts = {}
        if version_string:
            parts = version_string.split(".")

            if len(parts) < 3:
                logger.error(
                    f"Version string '{version_string}' is expected to have at least 3 dot-separated parts for Major.Minor.Revision."
                )
                return None, None

            try:
                version_major = int(parts[0])
                version_minor = int(parts[1])

                # Process the third part for revision and initial suffix
                revision_part_str = parts[2]
                parsed_revision_numeric_str = ""
                suffix_after_revision_numeric = ""
                for char_idx, char_val in enumerate(revision_part_str):
                    if char_val.isdigit():
                        parsed_revision_numeric_str += char_val
                    else:
                        suffix_after_revision_numeric = revision_part_str[char_idx:]
                        break

                if not parsed_revision_numeric_str:
                    # This means parts[2] (e.g., "alpha") did not start with a number.
                    logger.error(
                        f"Numeric revision not found at the start of the third part ('{revision_part_str}') of version string: {version_string}"
                    )
                    return None, None

                version_revision = int(parsed_revision_numeric_str)

                # Construct the full suffix from suffix_after_revision_numeric and any further parts (parts[3:])
                raw_suffix_components = []
                if suffix_after_revision_numeric:  # Add if not empty, e.g., "-rc" or "alpha"
                    raw_suffix_components.append(suffix_after_revision_numeric)

                if len(parts) > 3:  # If there are parts like ".1" or ".beta.4" after the third main part
                    raw_suffix_components.extend(parts[3:])

                final_suffix = None
                if raw_suffix_components:
                    # Join components: e.g., ["-rc", "1"] -> "-rc.1"; ["beta", "4"] -> "beta.4"
                    final_suffix = raw_suffix_components[0]
                    if len(raw_suffix_components) > 1:
                        final_suffix += "." + ".".join(raw_suffix_components[1:])

                version_parts = {
                    "version_major": version_major,
                    "version_minor": version_minor,
                    "version_revision": version_revision,
                    "version_suffix": final_suffix,  # Will be None if no suffix was found
                }

            except ValueError:  # Handles errors from int() conversion for major, minor, or revision
                logger.error(
                    f"Could not parse numeric components (Major, Minor, or Revision) from version string: {version_string}"
                )
                return None, None
        # If version_string was None or empty, version_parts remains {} and downstream code handles it.

        # Consolidate information (prefer body where available, fallback to headers)
        cp_height = cp_height_body if cp_height_body is not None else cp_height_header
        backend_height = backend_height_body if backend_height_body is not None else backend_height_header
        ledger_state = ledger_state_body if ledger_state_body else ledger_state_header
        db_caught_up = server_ready if server_ready is not None else (str(cp_ready_header).lower() == "true")

        version_info = {
            **version_parts,
            "last_block": int(cp_height) if cp_height else None,  # Counterparty height represents the last processed block
            "last_message_index": None,  # Not directly available in V2
            "api_url": node_url,
            "running_mode": network,  # Use network as running mode
            "last_block_time": None,  # Not available in V2
            "db_caught_up": db_caught_up,
            "bitcoin_block_count": (
                int(backend_height) if backend_height else None
            ),  # Backend height is the Bitcoin block count
            "ledger_state": ledger_state,
            "header_version": header_version,  # Keep original header/body values for debugging
            "body_version": body_version,
            "cp_ready_header": cp_ready_header,
        }

        return version_string, version_info

    except requests.exceptions.RequestException as e:
        logger.warning(f"Error fetching V2 version info from {node_url}: {e}")
        return None, None
    except json.JSONDecodeError as e:
        logger.warning(f"Error decoding JSON response from {node_url}: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error fetching V2 version info from {node_url}: {e}")
        return None, None


#########################################################################
# XCP ASSET FUNCTIONS
#########################################################################


def get_xcp_asset(cpid: str, node: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Get information about a single XCP asset."""
    # Get asset from API
    endpoint = f"/assets/{cpid}"
    try:
        asset_data = fetch_xcp(endpoint, node=node)
        return asset_data.get("result")
    except Exception as e:
        logger.error(f"Error getting XCP asset data for {cpid}: {e}")
        return None


def get_xcp_assets_by_cpids(
    cpids: List[str], chunk_size: int = 200, delay_between_chunks: int = 6, max_workers: int = 5
) -> List[Dict[str, Any]]:
    """Get information about multiple XCP assets using concurrent requests."""
    all_assets = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for cpid_chunk in split_into_chunks(cpids, chunk_size):
            futures.append(executor.submit(fetch_xcp_assets_details, cpid_chunk))
            # Add delay between submissions to avoid rate limits
            time.sleep(delay_between_chunks / max_workers)

        for future in concurrent.futures.as_completed(futures):
            try:
                chunk_assets = future.result()
                if chunk_assets:
                    all_assets.extend(chunk_assets)
            except Exception as e:
                logger.error(f"Error processing assets chunk: {e}")

    return all_assets


def fetch_xcp_assets_details(cpid_chunk: List[str]) -> List[Dict[str, Any]]:
    """Fetch asset details for a chunk of CPIDs."""
    assets = []
    for cpid in cpid_chunk:
        try:
            asset = get_xcp_asset(cpid)
            if asset:
                assets.append(asset)
        except Exception as e:
            logger.error(f"Error fetching asset {cpid}: {e}")
    return assets


#########################################################################
# XCP BLOCK FUNCTIONS - ASYNC
#########################################################################


async def get_xcp_transactions_async(
    block_index: int, cursor: Optional[str] = None, limit: int = 100
) -> Tuple[int, Optional[Dict[str, Any]]]:
    """Get transactions for a specific XCP block using async API."""
    # Create parameters for the API call
    endpoint = f"/blocks/{block_index}/transactions"
    params = {"limit": limit, "show_unconfirmed": "false"}
    if cursor:
        params["cursor"] = cursor

    try:
        # Make async API call
        response = await fetch_xcp_async(endpoint, params)
        if not response or not isinstance(response, dict):
            logger.error(f"Invalid response format for block {block_index} transactions")
            # Return None along with block_index on error
            return block_index, None

        result = response.get("result")
        next_cursor = response.get("next_cursor")

        if not isinstance(result, list):
            logger.error(f"No transactions found in response for block {block_index}")
            # Return empty result dict with block_index
            return block_index, {"result": [], "next_cursor": None, "result_count": 0}

        # Return block_index along with the result dictionary
        return block_index, {"result": result, "next_cursor": next_cursor, "result_count": len(result)}

    except Exception as e:
        logger.error(f"Error getting transactions via XCP V2: {e}")
        # Return None along with block_index on exception
        return block_index, None


async def get_all_xcp_transactions(start_block: int, limit: int = 100) -> Optional[List[Dict[str, Any]]]:
    """Get transactions for multiple XCP blocks."""
    try:
        logger.debug(f"get_all_xcp_transactions started for blocks {start_block} to {start_block + limit - 1}")
        complete_blocks = []
        # Adaptive chunk size based on node type
        healthy_nodes = get_healthy_nodes()
        if healthy_nodes:
            primary_node_url = healthy_nodes[0].get("url", "")
            if "127.0.0.1" in primary_node_url or "localhost" in primary_node_url:
                chunk_size = 10  # Local node can handle larger chunks
            else:
                chunk_size = 5  # External API - moderate chunks
        else:
            chunk_size = 5  # Default to moderate
        max_retries = 3
        base_chunk_timeout = 30  # Increased base timeout
        empty_blocks_count = 0  # Track empty blocks to detect potential API issues

        async def process_chunk(chunk_tasks_map: Dict[asyncio.Task, int], attempt=0):
            """Process a chunk of tasks with retry logic"""
            nonlocal empty_blocks_count
            logger.debug(f"Processing chunk of {len(chunk_tasks_map)} tasks, attempt {attempt + 1}")
            chunk_timeout = base_chunk_timeout * (2**attempt)
            tasks_to_process = list(chunk_tasks_map.keys())

            try:
                # Use as_completed to get results as they finish
                for task_done_future in asyncio.as_completed(tasks_to_process, timeout=chunk_timeout):
                    # Cast the Future to Task before using as dict key to satisfy mypy
                    task_done = cast(asyncio.Task, task_done_future)
                    block_index = chunk_tasks_map.get(task_done)  # Get block index using the task map
                    if block_index is None:
                        logger.error(f"Could not find block index for completed task: {task_done}")
                        continue

                    try:
                        # Get result (now a tuple: block_index, result_dict_or_none)
                        returned_block_index, result_data = await task_done

                        # Verify returned block index matches expected
                        if returned_block_index != block_index:
                            logger.error(
                                f"Block index mismatch for task {task_done}: expected {block_index}, got {returned_block_index}"
                            )
                            continue

                        if result_data and isinstance(result_data, dict) and "result" in result_data:
                            # Success path - got transactions
                            transactions = result_data["result"]
                            if transactions:
                                logger.debug(f"Got {len(transactions)} transactions for block {block_index}")
                                complete_blocks.append({"block_index": block_index, "transactions": transactions})
                            else:
                                logger.debug(f"No transactions for block {block_index}")
                                empty_blocks_count += 1
                                # Still count as completed even if empty
                                complete_blocks.append({"block_index": block_index, "transactions": []})
                        else:
                            logger.warning(f"Invalid result format or None returned for block {block_index}: {result_data}")
                            # Consider adding an empty entry if None was explicitly returned due to fetch error
                            complete_blocks.append({"block_index": block_index, "transactions": []})
                    except Exception as e:
                        logger.error(f"Error processing task result for block {block_index}: {e}")
                        # Add empty entry on error processing result
                        complete_blocks.append({"block_index": block_index, "transactions": []})

            except asyncio.TimeoutError:
                # Handle timeout by retrying with longer timeout if not too many retries
                logger.warning(f"Timeout processing chunk after {chunk_timeout}s, attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    # Retry with longer timeout
                    return await process_chunk(chunk_tasks_map, attempt + 1)
                else:
                    logger.error("Max retries reached processing chunk, some blocks may be missing")
                    # Add empty entries for timed out tasks
                    for task, idx in chunk_tasks_map.items():
                        if not task.done():
                            complete_blocks.append({"block_index": idx, "transactions": []})
                    return None

            except Exception as e:
                logger.error(f"Error in process_chunk: {e}")
                if attempt < max_retries - 1:
                    # Retry on generic error too
                    return await process_chunk(chunk_tasks_map, attempt + 1)
                else:
                    # Add empty entries for failed tasks
                    for task, idx in chunk_tasks_map.items():
                        if not task.done():
                            complete_blocks.append({"block_index": idx, "transactions": []})

            return None

        # Create tasks for each block in chunks to manage concurrency
        for i in range(0, limit, chunk_size):
            blocks_remaining = min(chunk_size, limit - i)
            chunk_tasks_map: Dict[asyncio.Task, int] = {}

            for j in range(blocks_remaining):
                block_index = start_block + i + j
                # Create a task for fetching transactions for this block
                task = asyncio.create_task(get_xcp_transactions_async(block_index))
                # Map task to its block index
                chunk_tasks_map[task] = block_index

            logger.debug(
                f"Created chunk of {len(chunk_tasks_map)} tasks for blocks {start_block + i} to {start_block + i + blocks_remaining - 1}"
            )

            # Process this chunk before moving to the next
            await process_chunk(chunk_tasks_map)

            # Check for shutdown after each chunk
            if is_shutdown_requested():
                logger.info("Shutdown requested, stopping transaction fetching")
                break

        blocks_count = len(complete_blocks)
        logger.info("get_all_xcp_transactions completed with " + str(blocks_count) + " blocks processed")
        return complete_blocks

    except Exception as e:
        logger.error(f"Error in get_all_xcp_transactions: {e}")
        return None


async def fetch_xcp_async(
    endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10
) -> Optional[Dict[str, Any]]:
    """Async version of fetch_xcp to get data from XCP V2 API."""
    healthy_nodes = get_healthy_nodes()
    if not healthy_nodes:
        logger.error("No healthy nodes available for async fetch")
        update_healthy_nodes()
        healthy_nodes = get_healthy_nodes()
        if not healthy_nodes:
            logger.error("Still no healthy nodes after update")
            return None

    for node in healthy_nodes:
        try:
            url = f"{node['url'].rstrip('/')}{endpoint}"
            logger.debug(f"Async fetch from {node['name']} at URL: {url} with params: {params}")

            try:
                # Create timeout and connector configuration for aiohttp
                timeout_obj = aiohttp.ClientTimeout(total=timeout, connect=5)
                connector = aiohttp.TCPConnector(
                    limit=20,  # Reduced total connection pool size
                    limit_per_host=10,  # Reduced connections per host for external APIs
                    ttl_dns_cache=300,  # DNS cache TTL
                    use_dns_cache=True,
                    keepalive_timeout=30,  # Keep connections alive
                    enable_cleanup_closed=True,
                )

                async with aiohttp.ClientSession(
                    timeout=timeout_obj, connector=connector, headers={"Connection": "keep-alive"}
                ) as session:
                    async with session.get(url, params=params) as response:
                        logger.debug(f"Response status from {node['name']}: {response.status}")
                        if response.status == 200:
                            data = await response.json()
                            health_tracker = node_health_tracker.get(node["name"])
                            if health_tracker:
                                health_tracker.mark_success()
                            return data
                        else:
                            error_text = await response.text()
                            logger.warning(f"Error from {node['name']}: HTTP {response.status}, {error_text}")
                            health_tracker = node_health_tracker.get(node["name"])
                            if health_tracker:
                                health_tracker.mark_failure(f"HTTP {response.status}: {error_text}")

            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching from {node['name']} (during session.get for {url})")
                health_tracker = node_health_tracker.get(node["name"])
                if health_tracker:
                    health_tracker.mark_failure("Timeout during session.get")
            except aiohttp.ServerDisconnectedError as sde:
                logger.warning(f"Server disconnected from {node['name']} for {url}: {sde}")
                health_tracker = node_health_tracker.get(node["name"])
                if health_tracker:
                    health_tracker.mark_failure(f"ServerDisconnectedError: {sde}")
            except Exception as inner_get_exc:
                logger.error(
                    f"Exception during session.get for {url}. Error: {type(inner_get_exc).__name__}: {inner_get_exc}",
                    exc_info=True,
                )
                health_tracker = node_health_tracker.get(node["name"])
                if health_tracker:
                    health_tracker.mark_failure(f"Exception during session.get: {type(inner_get_exc).__name__}")

        except Exception as e:
            logger.error(f"Outer exception for node {node['name']} in fetch_xcp_async: {type(e).__name__}: {e}", exc_info=True)
            health_tracker = node_health_tracker.get(node["name"])
            if health_tracker:
                health_tracker.mark_failure(str(e))

    logger.error("All nodes failed in async fetch")
    return None


#########################################################################
# XCP BLOCK FUNCTIONS - SYNC
#########################################################################


def get_xcp_block_hash(block_index: int, limit: Optional[int] = None) -> Optional[Union[str, Dict[int, Optional[str]]]]:
    """
    Get the XCP block hash for a specific block or range of blocks.

    Args:
        block_index: The block index to get the hash for, or the starting block
                    if limit is provided
        limit: Optional number of blocks to get hashes for

    Returns:
        If limit is None, returns a single hash string or None
        If limit is provided, returns a dict mapping block_index -> hash (or None for blocks with no hash)
    """
    try:
        # Handle single block case
        if limit is None:
            endpoint = f"/blocks/{block_index}"
            block_data = fetch_xcp(endpoint)
            if not block_data or "result" not in block_data:
                return None
            return block_data["result"].get("block_hash")

        # Handle multiple blocks case
        results = {}
        for idx in range(block_index, block_index + limit):
            endpoint = f"/blocks/{idx}"
            block_data = fetch_xcp(endpoint)
            hash_value = None
            if block_data and "result" in block_data:
                hash_value = block_data["result"].get("block_hash")
            results[idx] = hash_value
        return results

    except Exception as e:
        logger.error(f"Error getting XCP block hash for block {block_index}: {e}")
        if limit is None:
            return None
        return {idx: None for idx in range(block_index, block_index + limit)}


def fetch_xcp(endpoint: str, params: Optional[Dict[str, Any]] = None, node: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fetch data from XCP V2 API."""
    # Get healthy nodes or use provided node
    nodes_to_try = []
    if node:
        nodes_to_try = [node]
    else:
        healthy_nodes = get_healthy_nodes()
        if not healthy_nodes:
            logger.error("No healthy nodes available for fetch")
            update_healthy_nodes()  # Try updating nodes
            healthy_nodes = get_healthy_nodes()
            if not healthy_nodes:
                logger.error("Still no healthy nodes after update")
                return {"result": [], "next_cursor": None, "result_count": 0}
        nodes_to_try = healthy_nodes

    # Try each node until success
    last_error = None
    tried_nodes = []

    for node in nodes_to_try:
        url = f"{node['url'].rstrip('/')}{endpoint}"
        try:
            logger.debug(f"Fetching from {node['name']} at URL: {url}")
            response = requests.get(url, params=params, timeout=10)
            logger.debug(f"Response status from {node['name']}: {response.status_code}")

            if response.ok:
                data = response.json()
                logger.debug(f"Successful response from {node['name']}")
                # Mark node as healthy
                health_tracker = node_health_tracker.get(node["name"])
                if health_tracker:
                    health_tracker.mark_success()
                return data
            else:
                error_body = response.text
                logger.warning(f"Error response from {node['name']}: {error_body}")
                last_error = f"HTTP {response.status_code}: {error_body}"
                # Mark node failure
                health_tracker = node_health_tracker.get(node["name"])
                if health_tracker:
                    health_tracker.mark_failure(f"HTTP {response.status_code}: {error_body}")
        except Exception as e:
            logger.error(f"Fetch error for {node['name']} at {url}: {e}")
            last_error = str(e)
            # Mark node failure
            health_tracker = node_health_tracker.get(node["name"])
            if health_tracker:
                health_tracker.mark_failure(str(e))

        tried_nodes.append(node["name"])

    # If we get here, all nodes failed
    nodes_tried = ", ".join(tried_nodes)
    logger.error(f"Failed to fetch data from all available nodes ({nodes_tried}). Last error: {last_error}")
    return {"result": [], "next_cursor": None, "result_count": 0}


def verify_cp_block_hash(block_index: int, expected_hash: str | None = None, max_retries: int = 5) -> bool:
    """
    Verify that a block hash from CP matches the expected hash.
    If expected_hash is None, verifies that the CP node has any hash for this block.

    Args:
        block_index: Block index to verify
        expected_hash: Expected hash (optional)
        max_retries: Number of retries for fetching hash

    Returns:
        True if verified, False otherwise
    """
    retries = 0
    while retries < max_retries:
        try:
            # Get hash from CP node
            cp_hash = get_xcp_block_hash(block_index)
            if cp_hash is None:
                logger.warning(f"Block {block_index} has no hash in XCP")
                retries += 1
                time.sleep(1)
                continue

            # If no expected hash, any non-None hash is valid
            if expected_hash is None:
                logger.debug(f"Block {block_index} has hash {cp_hash} in XCP (no expected hash)")
                return True

            # Compare actual to expected
            if cp_hash == expected_hash:
                logger.debug(f"Block {block_index} hash {cp_hash} matches expected hash")
                return True
            else:
                logger.warning(f"Block {block_index} hash mismatch: expected {expected_hash}, got {cp_hash}")
                return False

        except Exception as e:
            retries += 1
            logger.error(f"Error verifying block hash: {e}")
            time.sleep(1)

    # If we get here, we've exhausted all retries
    logger.error(f"Failed to verify block {block_index} hash after {max_retries} attempts")
    return False


#########################################################################
# XCP BLOCK FUNCTIONS - PAGINATION AND BATCH FETCHING
#########################################################################


async def fetch_block_transactions_with_pagination(
    block_index: int, node_url: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Fetch all transactions for a specific block from CP API with pagination support."""
    logger.debug(f"Fetching block {block_index} transactions with pagination")
    endpoint = f"/blocks/{block_index}/transactions"
    all_transactions: List[Dict[str, Any]] = []
    next_cursor = None
    page_count = 0
    max_retries = 3
    page_size = 1000

    while True:
        page_count += 1
        params = {"verbose": "true", "limit": str(page_size), "show_unconfirmed": "false"}
        if next_cursor:
            params["cursor"] = next_cursor
        logger.debug(f"Fetching page {page_count} of transactions for block {block_index}, cursor: {next_cursor}")

        data = None
        for retry_attempt in range(max_retries):
            try:
                timeout = 15 if page_count > 1 else 10
                data = await fetch_xcp_async(endpoint, params, timeout=timeout)
                if data:
                    break
                if retry_attempt < max_retries - 1:
                    logger.warning(
                        f"Retrying page {page_count} for block {block_index} (attempt {retry_attempt+1}/{max_retries})"
                    )
                    await asyncio.sleep(1 * (retry_attempt + 1))
            except Exception as e:
                logger.error(
                    f"Error fetching page {page_count} for block {block_index} (attempt {retry_attempt+1}): {e}", exc_info=True
                )
                if retry_attempt < max_retries - 1:
                    await asyncio.sleep(1 * (retry_attempt + 1))

        if not data:
            logger.error(f"Failed to fetch data for block {block_index}, page {page_count} after {max_retries} retries")
            if page_count == 1:
                return None
            break

        page_transactions = data.get("result", [])
        if page_transactions is None:  # Should not happen if data.get has a default, but good practice
            logger.error(f"Received None for result field in block {block_index}, page {page_count}. Data was: {data}")
            page_transactions = []  # Ensure it's a list

        # Check for duplicates before adding
        tx_hashes_before = {tx.get("tx_hash") for tx in all_transactions if tx.get("tx_hash")}
        tx_hashes_page = {tx.get("tx_hash") for tx in page_transactions if tx.get("tx_hash")}
        duplicate_hashes = tx_hashes_before.intersection(tx_hashes_page)

        if duplicate_hashes:
            logger.warning(f"Found {len(duplicate_hashes)} duplicate transactions in page {page_count}")
            # Filter out duplicates to avoid adding the same transaction twice
            page_transactions = [tx for tx in page_transactions if tx.get("tx_hash") not in tx_hashes_before]
            logger.debug(f"After removing duplicates, adding {len(page_transactions)} transactions from page {page_count}")

        # Append transactions from this page
        transaction_count_before = len(all_transactions)
        all_transactions.extend(page_transactions)
        transaction_count_after = len(all_transactions)

        # If we didn't add the expected number, log a warning about possible duplicates
        expected_new_transactions = len(page_transactions)
        actual_new_transactions = transaction_count_after - transaction_count_before
        if actual_new_transactions != expected_new_transactions:
            logger.warning(
                f"Expected to add {expected_new_transactions} transactions but only added {actual_new_transactions} - possible duplicates detected"
            )

        # Log detailed info
        logger.debug(
            f"Added {len(page_transactions)} transactions from page {page_count}, total now: {transaction_count_after}"
        )

        # Check if there are more pages
        if "next_cursor" in data and data["next_cursor"]:
            next_cursor = data["next_cursor"]
            logger.debug(f"Found next cursor: {next_cursor}, continuing to next page")
        else:
            logger.debug(f"No more pages to fetch for block {block_index}")
            break

    # Create the final result
    if not all_transactions and page_count > 0:
        logger.debug(f"No issuance transactions found for block {block_index} after {page_count} pages")

    # Parse issuances
    issuances = []
    for tx in all_transactions:
        tx_type = tx.get("transaction_type")
        if tx_type in ["issuance", "fairminter"]:
            # Check for events in the transaction
            events = tx.get("events", [])
            for event in events:
                if event.get("event") in ["ASSET_ISSUANCE", "NEW_FAIRMINT"]:
                    # Use the proper issuance parsing function
                    issuance_data = parse_issuance_from_transaction(tx, event)
                    if issuance_data:
                        # This is a valid STAMP issuance
                        issuances.append(issuance_data)
                        # break  # Only need to add the tx once

    # Get block hash from the transactions if available
    block_hash = None
    if all_transactions:
        block_hash = all_transactions[0].get("block_hash")

    # Create block data structure
    block_data = {
        "block_index": block_index,
        "xcp_block_hash": block_hash,
        # "transactions": all_transactions,
        "issuances": issuances,
    }

    return block_data


def fetch_xcp_blocks_concurrent(
    start_block: int, end_block: int, progress_indicator: bool = False
) -> Dict[int, Dict[str, Any]]:
    """
    Fetch a range of blocks from the CP API with concurrent processing.

    This function provides data in the exact format expected by blocks.py:
    - Returns a dict mapping block indices to block data dictionaries
    - Each block data dict contains:
        - "block_index": The block index
        - "xcp_block_hash": The block hash from XCP
        - "transactions": List of all transactions in original order
        - "issuances": List of issuance transactions (sorted by tx_index)

    Args:
        start_block: First block to fetch
        end_block: Last block to fetch (inclusive)
        progress_indicator: Whether to show progress indicators for blocks

    Returns:
        Dictionary mapping block indices to block data
    """
    if end_block < start_block:
        logger.warning(f"Invalid block range: start_block {start_block} > end_block {end_block}")
        return {}

    logger.info(f"Fetching blocks {start_block} to {end_block} concurrently from CP API")

    # Check for large ranges
    num_blocks = end_block - start_block + 1
    if num_blocks > 100:
        logger.warning(f"Attempting to fetch a large range of {num_blocks} blocks, this may take some time")

    # Create an async event loop and run the collection
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_fetch_blocks_range_async(start_block, end_block, progress_indicator))
    finally:
        loop.close()


async def _fetch_blocks_range_async(
    start_block: int, end_block: int, progress_indicator: bool = False
) -> Dict[int, Dict[str, Any]]:
    """
    Async implementation to fetch a range of blocks.

    Args:
        start_block: First block to fetch
        end_block: Last block to fetch (inclusive)
        progress_indicator: Whether to show progress indicators

    Returns:
        Dictionary mapping block indices to block data
    """
    # Initialize result and counters
    results = {}

    # Adaptive concurrency based on node type
    healthy_nodes = get_healthy_nodes()
    if healthy_nodes:
        primary_node_url = healthy_nodes[0].get("url", "")
        # Use higher concurrency for local nodes, moderate for external APIs
        if "127.0.0.1" in primary_node_url or "localhost" in primary_node_url:
            max_concurrent_semaphore = 3  # Local node can handle more
        else:
            max_concurrent_semaphore = 2  # External API - still concurrent but gentle
    else:
        max_concurrent_semaphore = 2  # Default to moderate

    logger.debug(f"Using concurrency limit of {max_concurrent_semaphore} for block fetching")
    # Create a semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent_semaphore)

    # Create tasks for each block to fetch
    async def fetch_block_with_semaphore(block_idx):
        async with semaphore:
            try:
                block_data = await fetch_block_transactions_with_pagination(block_idx)
                if block_data:
                    if progress_indicator and block_idx % 10 == 0:
                        logger.info(f"Progress: Fetched block {block_idx}")
                    return block_idx, block_data
                else:
                    # Ensure a consistent structure for blocks that might fail to fetch or have no data
                    logger.warning(
                        f"No block data returned from fetch_block_transactions_with_pagination for block {block_idx}"
                    )
                    return block_idx, {
                        "block_index": block_idx,
                        "error": "Failed to fetch block or no data",
                        "issuances": [],
                        "transactions": [],
                    }
            except Exception as e:
                logger.error(f"Error fetching block {block_idx} in _fetch_blocks_range_async: {e}", exc_info=True)
                return block_idx, {"block_index": block_idx, "error": str(e), "issuances": [], "transactions": []}

    # Create tasks for each block
    tasks = [fetch_block_with_semaphore(i) for i in range(start_block, end_block + 1)]

    # Wait for all tasks to complete
    blocks_data_results = await asyncio.gather(*tasks)

    # Process the results
    for block_idx, block_data_item in blocks_data_results:
        results[block_idx] = block_data_item

    logger.info(f"Completed fetching {len(results)} blocks from {start_block} to {end_block}")
    return results


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
            # Handle potential None value for description before stripping
            raw_description = params.get("description")
            description = raw_description.strip() if raw_description is not None else ""
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
            return None

    except Exception as e:
        logger.error(f"Error parsing issuance for tx {tx.get('tx_hash')}: {e}")
        return None
