import json
import logging
from typing import Dict, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

logger = logging.getLogger(__name__)

# Headers for quick operations like version checks
QUICK_HEADERS = {
    "content-type": "application/json",
    "Connection": "keep-alive",
    "Keep-Alive": "timeout=10, max=1000",
}


def create_session_with_retries(
    retries: int = 3,
    backoff_factor: float = 0.3,
    status_forcelist: tuple = (500, 502, 503, 504),
) -> requests.Session:
    """
    Create a requests Session with retry capabilities.

    Args:
        retries: Number of retries to attempt
        backoff_factor: Backoff factor for retry delay calculation
        status_forcelist: HTTP status codes that should trigger a retry

    Returns:
        requests.Session: Session object with retry configuration
    """
    session = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _create_payload(method, params):
    base_payload = {"method": "", "params": {}, "jsonrpc": "2.0", "id": 0}
    base_payload["method"] = method
    base_payload["params"] = params
    return base_payload


def get_cp_version(node_url: Optional[str] = None, log_connection: bool = False) -> Tuple[Optional[str], Optional[Dict]]:
    """
    Get Counterparty node version information.

    Args:
        node_url: Optional URL to check. If None, uses default CP_RPC_URL.
                 URL should end with /api/ for v1 endpoint.
        log_connection: Whether to log connection details

    Returns:
        Tuple of (version_string, version_info_dict)
        version_string is in format "major.minor.revision"
        version_info_dict contains detailed version information
    """
    try:
        # Ensure URL is a valid string
        if node_url is not None and not isinstance(node_url, str):
            node_url = None  # Silently fall back to default URL

        # Get base URL and ensure it's a string
        url_to_use = node_url if node_url else config.CP_RPC_URL
        if not isinstance(url_to_use, str):
            return None, None

        # Clean and format the URL
        url_to_use = url_to_use.strip().rstrip("/")

        # If URL ends with /v2, replace with /api for version check
        if url_to_use.endswith("/v2"):
            url_to_use = url_to_use[:-3] + "/api"
        elif "/api" not in url_to_use:
            url_to_use = f"{url_to_use}/api"

        if not url_to_use.endswith("/api/"):
            url_to_use = f"{url_to_use}/"

        if log_connection:
            logger.debug(f"Connecting to Counterparty node: {url_to_use}")

        payload = _create_payload("get_running_info", {})
        response = requests.post(url_to_use, data=json.dumps(payload), headers=QUICK_HEADERS, auth=config.CP_AUTH, timeout=10)

        if not response.ok:
            logger.debug(f"Error response from {url_to_use}: {response.status_code} - {response.text}")
            return None, None

        try:
            result = response.json()["result"]
        except (KeyError, json.JSONDecodeError) as e:
            logger.debug(f"Invalid JSON response from {url_to_use}: {e}")
            return None, None

        version_info = {
            "version_major": result["version_major"],
            "version_minor": result["version_minor"],
            "version_revision": result["version_revision"],
            "last_block": result.get("last_block", None),
            "last_message_index": result.get("last_message_index", None),
            "api_url": url_to_use,
            "running_mode": result.get("running_mode", "unknown"),
            "last_block_time": result.get("last_block_time", None),
            "db_caught_up": result.get("db_caught_up", False),
            "bitcoin_block_count": result.get("bitcoin_block_count", None),
        }

        version_string = ".".join(
            [str(version_info["version_major"]), str(version_info["version_minor"]), str(version_info["version_revision"])]
        )

        return version_string, version_info

    except Exception as e:
        logger.debug(f"Error getting version info: {e}")
        return None, None
