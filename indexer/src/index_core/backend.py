import collections
import concurrent.futures
import json
import logging
import time

import requests
from bitcoin.core import CBlock, CTransaction, x
from requests.exceptions import ConnectionError, Timeout

import config
import index_core.util as util
from exceptions import BackendRPCError
from index_core.parser import RUST_PARSER_AVAILABLE, Parser

logger = logging.getLogger(__name__)

# Standard cache sizes
raw_transactions_cache = util.DictCache(size=config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE)
deserialized_tx_cache = util.DictCache(size=config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE)

# Initialize Rust parser if available
_parser = None
if RUST_PARSER_AVAILABLE:
    try:
        _parser = Parser()
        logger.info("Using high-performance Rust parser")
    except Exception as e:
        logger.warning(f"Failed to initialize Rust parser: {e}. Falling back to Python parser")


def rpc_call(payload):
    """Calls to bitcoin core and returns the response"""
    url = config.RPC_URL
    response = None
    TRIES = 12

    # Add validation and debug logging for Quicknode
    if config.QUICKNODE_ENDPOINT and config.QUICKNODE_API_KEY:
        logger.debug(f"Making Quicknode RPC call to: {util.clean_url_for_log(url)}")
    else:
        logger.debug(f"Making RPC call to: {util.clean_url_for_log(url)}")

    if isinstance(payload, list):
        logger.debug(f"Batch request with {len(payload)} items")
    else:
        logger.debug(f"Method: {payload.get('method')}")
        logger.debug(f"Params: {payload.get('params')}")

    for i in range(TRIES):
        try:
            headers = {"content-type": "application/json"}

            # Authentication is handled via API key in URL path
            logger.debug(f"Attempt {i + 1}/{TRIES} to connect to {util.clean_url_for_log(url)}")

            response = requests.post(
                url,
                data=json.dumps(payload),
                headers=headers,
                verify=(not config.BACKEND_SSL_NO_VERIFY),
                timeout=config.REQUESTS_TIMEOUT,
            )
            if response.status_code != 200:
                logger.debug(f"Response status code: {response.status_code}")
                logger.debug(f"Response text: {response.text}")
            if i > 0:
                logger.debug("Successfully connected.")
            break
        except (Timeout, ConnectionError) as e:
            logger.debug(
                f"Could not connect to backend at `{util.clean_url_for_log(url)}`. Error: {str(e)} (Try {i + 1}/{TRIES})"
            )
            time.sleep(5)
        except requests.exceptions.InvalidURL as e:
            logger.error(f"Invalid URL format: {str(e)}")
            logger.error(f"URL being used: {util.clean_url_for_log(url)}")
            raise BackendRPCError(f"Invalid URL format for RPC connection: {str(e)}")

    if response is None:
        if config.TESTNET:
            network = "testnet"
        elif config.REGTEST:
            network = "regtest"
        else:
            network = "mainnet"
        raise BackendRPCError(
            f"Cannot communicate with backend at `{util.clean_url_for_log(url)}`. (server is set to run on {network})"
        )
    elif response.status_code in (401,):
        raise BackendRPCError(
            "Authorization error connecting to {}: {} {}".format(
                util.clean_url_for_log(url), response.status_code, response.reason
            )
        )
    elif response.status_code not in (200, 500, 503):
        raise BackendRPCError(f"{response.status_code} {response.reason}")

    # Handle json decode errors
    try:
        response_json = response.json()
    except json.decoder.JSONDecodeError as e:
        raise BackendRPCError(
            f"Received invalid JSON from backend with a response of: {response.status_code} {response.reason} {e}"
        )

    # For batch requests, return the full response array
    if isinstance(payload, list):
        if not isinstance(response_json, list):
            raise BackendRPCError("Expected array response for batch request")
        return response_json

    # For single requests, process as before
    if "error" not in response_json.keys() or response_json["error"] is None:
        return response_json["result"]
    elif response_json["error"]["code"] == -5:  # RPC_INVALID_ADDRESS_OR_KEY
        raise BackendRPCError("{} Is `txindex` enabled in {} Core?".format(response_json["error"], config.BTC_NAME))
    elif response_json["error"]["code"] in [-28, -8, -2]:
        # "Verifying blocks..." or "Block height out of range" or "The network does not appear to fully agree!"
        logger.debug("Backend not ready. Sleeping for ten seconds.")
        time.sleep(10)
        return rpc_call(payload)
    else:
        raise BackendRPCError("Error connecting to {}: {}".format(util.clean_url_for_log(url), response_json["error"]))


def rpc(method, params):
    payload = {
        "method": method,
        "params": params,
        "jsonrpc": "2.0",
        "id": 0,
    }
    return rpc_call(payload)


def rpc_batch(request_list):
    responses = collections.deque()

    def make_call(chunk):
        try:
            logger.debug(f"Making RPC batch call with {len(chunk)} requests")
            batch_responses = rpc_call(chunk)  # This will now return the full response array

            if not batch_responses:
                logger.error("Received empty response from RPC batch call")
                return

            logger.debug(f"Received {len(batch_responses)} responses")

            for response in batch_responses:
                if not isinstance(response, dict):
                    logger.error(f"Invalid response format: {type(response)}")
                    continue

                if "error" in response and response["error"] is not None:
                    logger.error(f"RPC error in response: {response['error']}")
                    continue

                if "result" not in response:
                    logger.error(f"Missing 'result' in response: {response}")
                    continue

                responses.append(response)

            logger.debug(f"Successfully processed {len(batch_responses)} responses")

        except Exception as e:
            logger.error(f"Error in RPC batch call: {str(e)}")
            logger.debug("Exception details:", exc_info=True)
            raise

    chunks = util.chunkify(request_list, config.RPC_BATCH_SIZE)
    logger.debug(f"Split {len(request_list)} requests into {len(chunks)} chunks")

    with concurrent.futures.ThreadPoolExecutor(max_workers=config.BACKEND_RPC_BATCH_NUM_WORKERS) as executor:
        try:
            futures = [executor.submit(make_call, chunk) for chunk in chunks]
            concurrent.futures.wait(futures)

            # Check for exceptions in futures
            for future in futures:
                if future.exception():
                    logger.error(f"Thread pool error: {future.exception()}")
                    raise future.exception()
        except Exception as e:
            logger.error(f"Thread pool execution error: {str(e)}")
            logger.debug("Thread pool exception details:", exc_info=True)
            raise

    logger.debug(f"Completed batch RPC calls. Got {len(responses)} total responses")
    return list(responses)


def getblockcount():
    return rpc("getblockcount", [])


def getblockhash(blockcount):
    return rpc("getblockhash", [blockcount])


def getblock(block_hash, verbosity=False):
    return rpc("getblock", [block_hash, verbosity])


def getcblock(block_hash):
    block_hex = getblock(block_hash)
    return CBlock.deserialize(bytes.fromhex(block_hex))


def getblockheader(block_hash):
    """Fetches the block header for a given block hash."""
    return rpc("getblockheader", [block_hash])


def getrawtransaction(tx_hash, verbose=False, skip_missing=False):
    return getrawtransaction_batch([tx_hash], verbose=verbose, skip_missing=skip_missing)[tx_hash]


def deserialize(tx_hex):
    """
    Deserialize a transaction hex string into a CTransaction object.
    Uses Rust parser if available for better performance.
    """
    if tx_hex in deserialized_tx_cache:
        return deserialized_tx_cache[tx_hex]

    if _parser is not None:
        try:
            # Use Rust parser for better performance
            tx = _parser.deserialize_transaction(tx_hex)
            deserialized_tx_cache[tx_hex] = tx
            return tx
        except Exception as e:
            logger.warning(f"Rust parser failed: {e}. Falling back to Python parser")

    # Fallback to Python parser
    ctx = CTransaction.deserialize(x(tx_hex))
    deserialized_tx_cache[tx_hex] = ctx
    return ctx


def serialize(ctx):
    return CTransaction.serialize(ctx)


def get_tx_list(block_hash):
    """Get transaction list from block using Rust parser if available."""
    if _parser is not None:
        try:
            block_data = rpc("getblock", [block_hash, 0])  # Get raw block hex
            return _parser.parse_block(block_data)
        except Exception as e:
            logger.warning(f"Rust block parser failed: {e}. Falling back to Python parser")

    # Fallback to original implementation
    block_data = rpc("getblock", [block_hash, 2])

    tx_hash_list = []
    raw_transactions = {}

    for tx in block_data["tx"]:
        tx_hash = tx["txid"]
        tx_hash_list.append(tx_hash)
        raw_transactions[tx_hash] = tx["hex"]

    return (
        tx_hash_list,
        raw_transactions,
        block_data["time"],
        block_data.get("previousblockhash"),
        block_data.get("difficulty"),
    )


GETRAWTRANSACTION_MAX_RETRIES = 2
monotonic_call_id = 0


def getrawtransaction_batch(txhash_list, verbose=False, skip_missing=False, _retry=0):
    _logger = logger.getChild("getrawtransaction_batch")

    txhash_list = list(set(txhash_list))
    _logger.debug(f"Processing {len(txhash_list)} transactions")

    if len(txhash_list) > config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE:
        chunk_size = min(500, config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE)
        txhash_list_chunks = util.chunkify(txhash_list, chunk_size)
        txes = {}
        for txhash_list_chunk in txhash_list_chunks:
            txes.update(getrawtransaction_batch(txhash_list_chunk, verbose=verbose, skip_missing=skip_missing))
        return txes

    tx_hash_call_id = {}
    payload = []
    noncached_txhashes = []  # Use list instead of set since we need to iterate once

    # Pre-check cache in single pass
    for tx_hash in txhash_list:
        if tx_hash not in raw_transactions_cache:
            global monotonic_call_id
            monotonic_call_id += 1
            call_id = str(monotonic_call_id)
            payload.append(
                {
                    "method": "getrawtransaction",
                    "params": [tx_hash, 1],
                    "jsonrpc": "2.0",
                    "id": call_id,
                }
            )
            noncached_txhashes.append(tx_hash)
            tx_hash_call_id[call_id] = tx_hash
        else:
            try:
                raw_transactions_cache.refresh(tx_hash)
            except Exception:
                noncached_txhashes.append(tx_hash)

    _logger.debug(
        f"Batch stats: cache_size={len(raw_transactions_cache)}, to_fetch={len(payload)}, total_requested={len(txhash_list)}"
    )

    # Fetch missing transactions
    if payload:
        try:
            batch_responses = rpc_batch(payload)
            for response in batch_responses:
                tx_hash = tx_hash_call_id.get(response.get("id", "??"), "??")
                if "error" not in response or response["error"] is None:
                    if "result" in response:
                        raw_transactions_cache[tx_hash] = response["result"]
                elif skip_missing and "error" in response and response["error"]["code"] == -5:
                    raw_transactions_cache[tx_hash] = None
                else:
                    if not skip_missing:
                        raise BackendRPCError(f"Error fetching tx {tx_hash}: {response.get('error')}")
        except Exception as e:
            _logger.error(f"Failed to fetch transactions: {str(e)}")
            raise

    result = {}
    missing_txs = []
    for tx_hash in txhash_list:
        try:
            cached_tx = raw_transactions_cache[tx_hash]
            if cached_tx is None:
                result[tx_hash] = None
            else:
                result[tx_hash] = cached_tx["hex"] if not verbose else cached_tx
        except KeyError:
            missing_txs.append(tx_hash)

    # Handle missing transactions with single retry
    if missing_txs and _retry < GETRAWTRANSACTION_MAX_RETRIES:
        time.sleep(0.05 * (_retry + 1))
        retry_results = getrawtransaction_batch(missing_txs, verbose=verbose, skip_missing=skip_missing, _retry=_retry + 1)
        result.update(retry_results)
    elif missing_txs and skip_missing:
        for tx_hash in missing_txs:
            result[tx_hash] = None
    elif missing_txs:
        raise BackendRPCError(f"Failed to fetch transactions after retries: {missing_txs}")

    return result
