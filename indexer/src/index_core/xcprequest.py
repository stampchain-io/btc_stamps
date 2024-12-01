import concurrent.futures
import json
import logging
import sys
import time
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional

import requests
from tqdm import tqdm

import config
import index_core.util as util

logger = logging.getLogger(__name__)

url = config.CP_RPC_URL
auth = config.CP_AUTH

healthy_nodes_lock = Lock()
healthy_nodes: List[Dict[str, Any]] = []


def _create_payload(method, params):
    base_payload = {"method": "", "params": {}, "jsonrpc": "2.0", "id": 0}
    base_payload["method"] = method
    base_payload["params"] = params
    return base_payload


def fetch_cp_concurrent(block_index, block_tip, indicator=None):
    """testing with this method because we were initially getting invalid results
    when using the get_blocks[xxx,yyyy,zzz] method to the CP API
    FIXME: now with version 10.x the concurrent method has been fixed so we can pull multiple blocks at once
            will need to check CP version first to validate this will work, and fallback to this method"""
    with concurrent.futures.ThreadPoolExecutor() as executor:

        blocks_to_fetch = 1000
        futures = []
        results_dict = {}

        if block_tip > block_index + blocks_to_fetch:
            block_tip = block_index + blocks_to_fetch
        else:
            blocks_to_fetch = block_tip - block_index + 1

        pbar = tqdm(
            total=blocks_to_fetch,
            desc=f"Fetching CP Trx [{block_index}..{block_tip}]",
            leave=True,
        )

        while block_index <= block_tip:
            future = executor.submit(get_xcp_block_data, block_index, indicator=indicator)
            future.block_index = block_index
            futures.append(future)
            block_index += 1

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results_dict[future.block_index] = result
            pbar.update(1)

        pbar.close()

        sorted_results = dict(sorted(results_dict.items(), key=lambda x: x[0]))
    return sorted_results


def _handle_cp_call_with_retry(func, params, block_index, indicator=None):
    if indicator is not None:
        pbar = tqdm(
            desc="Waiting for CP block {} to be parsed...".format(block_index),
            leave=True,
            bar_format="{desc}: {elapsed} {bar} [{postfix}]",
        )

    while util.CP_BLOCK_COUNT is None or block_index > util.CP_BLOCK_COUNT:
        try:
            util.CP_BLOCK_COUNT = _get_cp_block_count()
            logger.info("Current block count: {}".format(util.CP_BLOCK_COUNT))
            if util.CP_BLOCK_COUNT is not None and block_index <= util.CP_BLOCK_COUNT:
                if indicator is not None:
                    pbar.close()
                break
            else:
                if indicator is not None:
                    pbar.refresh()
                time.sleep(config.BACKEND_POLL_INTERVAL)
        except Exception as e:
            logger.warning("Error getting CP block count: {}".format(e))
            time.sleep(config.BACKEND_POLL_INTERVAL)

    try:
        data = func(params=params)
        if data is not None and len(data) > 0:
            return data
        else:
            logger.warning("Received empty data from CP.")
            return None
    except Exception as e:
        logger.warning("Error in CP call: {}".format(e))
        return None


def get_cp_version():
    try:
        logger.warning(f"""Connecting to CP Node: {config.CP_RPC_URL}""")
        payload = _create_payload("get_running_info", {})
        headers = {"content-type": "application/json"}
        response = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth, timeout=10)
        result = json.loads(response.text)["result"]
        version_major = result["version_major"]
        version_minor = result["version_minor"]
        version_revision = result["version_revision"]
        version = ".".join([str(version_major), str(version_minor), str(version_revision)])
        return version
    except Exception as e:
        logger.warning("Error getting version info: {}".format(e))
        return None


def _get_cp_block_count():
    result = None
    try:
        payload = _create_payload("get_running_info", {})
        headers = {"content-type": "application/json"}
        response = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth, timeout=10)
        logger.info("get_block_count response: {}".format(response.text))
        result = json.loads(response.text)["result"]
        if result["last_block"] is None:
            return None
        return result["last_block"]["block_index"]
    except Exception as e:
        print(result)
        logger.warning("Error getting CP block count: {}".format(e))
        return None


def _get_block(params={}):
    payload = _create_payload("get_blocks", params)
    headers = {"content-type": "application/json"}
    response = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth, timeout=10)
    return json.loads(response.text)["result"]


def _get_all_tx_by_block(block_index, indicator=None):
    return _handle_cp_call_with_retry(
        func=_get_block,
        params={"block_indexes": [block_index]},
        block_index=block_index,
        indicator=indicator,
    )


def get_xcp_block_data(block_index: int, indicator=None):
    max_retries = 25
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        block_data_from_xcp = _handle_cp_call_with_retry(
            func=_get_block,
            params={"block_indexes": [block_index]},
            block_index=block_index,
            indicator=indicator,
        )

        if block_data_from_xcp is not None:
            try:
                parsed_block_data = _parse_issuances_from_block(block_data=block_data_from_xcp)
                return parsed_block_data["issuances"]
            except (TypeError, IndexError, KeyError) as e:
                sys.exit(f"Error parsing block data for block {block_index}: {e}")

        if attempt < max_retries - 1:
            logger.warning(f"Failed to get block data for block {block_index}, attempt {attempt + 1}/{max_retries}")
            time.sleep(retry_delay)

    sys.exit(f"Failed to get block data for block {block_index} after {max_retries} attempts")


def _parse_issuances_from_block(block_data):
    if not block_data or not isinstance(block_data, list) or len(block_data) == 0:
        raise ValueError("Invalid block data format")
    issuances = []
    block_data = json.loads(json.dumps(block_data[0]))
    for tx in block_data["_messages"]:
        tx_data = json.loads(tx.get("bindings"))
        tx_data["msg_index"] = tx.get("message_index")
        tx_data["block_index"] = tx.get("block_index")
        if tx.get("command") == "insert" and tx.get("category") == "issuances":
            if tx_data.get("status", "invalid") == "valid":
                stamp_issuance = _check_for_stamp_issuance(issuance=tx_data)
                if stamp_issuance is not None:
                    issuances.append(stamp_issuance)
    return {
        "block_index": block_data["block_index"],
        "issuances": issuances,
    }


def parse_base64_from_description(description):
    if description is not None and description.lower().find("stamp:") != -1:
        stamp_search = description[description.lower().find("stamp:") + 6 :]
        stamp_search = stamp_search.strip()
        if ";" in stamp_search:
            stamp_mimetype, stamp_base64 = stamp_search.split(";", 1)
            stamp_mimetype = stamp_mimetype.strip() if len(stamp_mimetype) <= 255 else ""  # db limit
            stamp_base64 = stamp_base64.strip() if len(stamp_base64) > 1 else None
        else:
            stamp_mimetype = ""
            stamp_base64 = stamp_search.strip() if len(stamp_search) > 1 else None

        return stamp_base64, stamp_mimetype
    else:
        return None, None


def _check_for_stamp_issuance(issuance):
    description = issuance["description"]

    if description is not None and description.lower().find("stamp:") != -1:
        _, stamp_mimetype = parse_base64_from_description(description)

        quantity = issuance["quantity"]  # + prev_qty
        # logger.warning(f"CPID: {issuance['asset']} qty: {quantity}")
        if issuance["status"] == "valid":
            filtered_issuance = {
                # we are not adding the base64 string to the json string
                # in issuances, this is parsed when going to StampTable
                "cpid": issuance["asset"],  # Rename 'asset' to 'cpid'
                "quantity": quantity,
                "divisible": issuance["divisible"],
                "locked": issuance["locked"],
                "source": issuance["source"],
                "issuer": issuance["issuer"],
                "transfer": issuance["transfer"],
                "description": issuance["description"],
                "reset": issuance["reset"],
                "status": issuance["status"],
                "asset_longname": (issuance["asset_longname"] if "asset_longname" in issuance else ""),  # TODO change to NULL
                "tx_hash": issuance["tx_hash"],
                "message_index": issuance["msg_index"],
                "stamp_mimetype": stamp_mimetype,
            }
        return filtered_issuance
    return None


def filter_issuances_by_tx_hash(issuances, tx_hash):
    filtered_issuances = [issuance for issuance in issuances if issuance["tx_hash"] == tx_hash]
    return filtered_issuances[0] if filtered_issuances else None


def fetch_xcp_v2(
    endpoint: str, params: Optional[Dict[str, Any]] = None, node: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    global healthy_nodes

    if not healthy_nodes:
        update_healthy_nodes()

    nodes_to_try = [node] if node else healthy_nodes.copy()

    for node in nodes_to_try:
        url = f"{node['url']}{endpoint}"
        try:
            logger.info(f"Attempting to fetch from URL: {url}")
            response = requests.get(url, params=params, timeout=10)
            logger.info(f"Response status from {node['name']}: {response.status_code}")

            if response.ok:
                data = response.json()
                logger.info(f"Successful response from {node['name']}")
                return data
            else:
                error_body = response.text
                logger.warning(f"Error response body from {node['name']}: {error_body}")
        except Exception as e:
            logger.error(f"Fetch error for {url}: {e}")
            # Remove the failed node from healthy_nodes
            with healthy_nodes_lock:
                if node in healthy_nodes:
                    healthy_nodes.remove(node)
                    logger.warning(f"Node {node['name']} removed from healthy nodes.")
                    if not healthy_nodes:
                        update_healthy_nodes()
        # Continue to the next node if the current one fails
        continue

    logger.error("Failed to fetch data from available nodes.")
    return {
        "result": [],
        "next_cursor": None,
        "result_count": 0,
    }


def get_xcp_asset(cpid: str, node: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Get details of a single CP asset by its CPID.
    """
    endpoint = f"/assets/{cpid}"
    logger.info(f"Fetching XCP asset for CPID: {cpid} using node {node['name'] if node else 'default nodes'}")
    try:
        response = fetch_xcp_v2(endpoint, node=node)
        if not response or not isinstance(response, dict) or "result" not in response:
            logger.error(f"Invalid response for asset {cpid}: {response}")
            return None

        logger.info(f"Fetched XCP asset for CPID: {cpid}")
        return response["result"]
    except Exception as e:
        logger.error(f"Error fetching asset info for cpid {cpid}: {e}")
        return None


def chunks(lst: List[Any], n: int) -> Iterator[List[Any]]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def get_xcp_assets_by_cpids(
    cpids: List[str], chunk_size: int = 200, delay_between_chunks: int = 6, max_workers: int = 5
) -> List[Dict[str, Any]]:
    assets_details = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for cpid_chunk in chunks(cpids, chunk_size):
            future = executor.submit(fetch_assets_details, cpid_chunk)
            futures.append(future)
            time.sleep(delay_between_chunks)

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                assets_details.extend(result)

    return assets_details


def fetch_assets_details(cpid_chunk: List[str]) -> List[Dict[str, Any]]:
    assets_details = []
    for cpid in cpid_chunk:
        logger.info(f"Fetching asset detail for CPID: {cpid}")
        asset_detail = get_xcp_asset(cpid)
        if asset_detail:
            assets_details.append(asset_detail)
        else:
            logger.warning(f"No asset detail found for CPID: {cpid}")
    return assets_details


def check_node_health(node: Dict[str, Any]) -> bool:
    """
    Check the health of a node by querying its /healthz endpoint.

    Args:
        node (Dict[str, Any]): The node to check.

    Returns:
        bool: True if the node is healthy, False otherwise.
    """
    health_url = f"{node['url']}/healthz"
    try:
        response = requests.get(health_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("result", {}).get("status") == "Healthy"
    except Exception as e:
        logger.warning(f"Health check failed for node {node['name']}: {e}")
    return False


def update_healthy_nodes():
    global healthy_nodes
    with healthy_nodes_lock:
        healthy_nodes = [node for node in config.XCP_V2_NODES if check_node_health(node)]
    if not healthy_nodes:
        logger.error("No healthy nodes available.")
    else:
        logger.info(f"Healthy nodes: {[node['name'] for node in healthy_nodes]}")
