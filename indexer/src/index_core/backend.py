import binascii
import collections
import concurrent.futures
import json
import logging
import time

import bitcoin as bitcoinlib
import requests
from bitcoin.core import CBlock
from requests.exceptions import ConnectionError, Timeout

import config
import index_core.util as util
from exceptions import BackendRPCError

logger = logging.getLogger(__name__)

raw_transactions_cache = util.DictCache(size=config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE)  # used in getrawtransaction_batch()


def rpc_call(payload):
    """Calls to bitcoin core and returns the response"""
    url = config.RPC_URL
    response = None
    TRIES = 12

    # Add validation and debug logging for Quicknode
    if config.QUICKNODE_URL and config.RPC_TOKEN:
        logger.debug(f"Making Quicknode RPC call to: {url.replace(config.RPC_TOKEN, '****')}")
    else:
        logger.debug(f"Making RPC call to: {util.clean_url_for_log(url)}")

    if isinstance(payload, list):
        logger.debug(f"Batch request with {len(payload)} items")
    else:
        logger.debug(f"Method: {payload.get('method')}")
        logger.debug(f"Params: {payload.get('params')}")

    for i in range(TRIES):
        try:
            logger.debug(f"Attempt {i + 1}/{TRIES} to connect to {util.clean_url_for_log(url)}")
            response = requests.post(
                url,
                data=json.dumps(payload),
                headers={"content-type": "application/json"},
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
    return bitcoinlib.core.CTransaction.deserialize(binascii.unhexlify(tx_hex))


def serialize(ctx):
    return bitcoinlib.core.CTransaction.serialize(ctx)


def get_tx_list(block_hash):
    block_data = getblock(block_hash, 2)

    tx_hash_list = []
    raw_transactions = {}
    for tx in block_data["tx"]:
        tx_hash = tx["txid"]
        tx_hash_list.append(tx_hash)
        raw_transactions[tx_hash] = tx["hex"]

    block_time = block_data["time"]
    previous_block_hash = block_data.get("previousblockhash", None)
    difficulty = block_data.get("difficulty", None)

    return tx_hash_list, raw_transactions, block_time, previous_block_hash, difficulty


GETRAWTRANSACTION_MAX_RETRIES = 2
monotonic_call_id = 0


def getrawtransaction_batch(txhash_list, verbose=False, skip_missing=False, _retry=0):
    _logger = logger.getChild("getrawtransaction_batch")

    if len(txhash_list) > config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE:
        # don't try to load in more than BACKEND_RAW_TRANSACTIONS_CACHE_SIZE entries in a single call
        txhash_list_chunks = util.chunkify(txhash_list, config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE)
        txes = {}
        for txhash_list_chunk in txhash_list_chunks:
            txes.update(getrawtransaction_batch(txhash_list_chunk, verbose=verbose, skip_missing=skip_missing))
        return txes

    tx_hash_call_id = {}
    payload = []
    noncached_txhashes = set()

    txhash_list = set(txhash_list)
    _logger.debug(f"Processing {len(txhash_list)} transactions")

    # payload for transactions not in cache
    for tx_hash in txhash_list:
        if tx_hash not in raw_transactions_cache:
            global monotonic_call_id
            monotonic_call_id = monotonic_call_id + 1
            call_id = "{}".format(monotonic_call_id)
            payload.append(
                {
                    "method": "getrawtransaction",
                    "params": [tx_hash, 1],
                    "jsonrpc": "2.0",
                    "id": call_id,
                }
            )
            noncached_txhashes.add(tx_hash)
            tx_hash_call_id[call_id] = tx_hash
            _logger.debug(f"Added tx {tx_hash} to fetch queue")

    # refresh cache entries
    for tx_hash in txhash_list.difference(noncached_txhashes):
        try:
            raw_transactions_cache.refresh(tx_hash)
            _logger.debug(f"Refreshed cache for tx {tx_hash}")
        except Exception as e:
            _logger.warning(f"Failed to refresh cache for tx {tx_hash}: {str(e)}")

    _logger.debug(
        "Batch stats: cache_size={}, to_fetch={}, total_requested={}".format(
            len(raw_transactions_cache), len(payload), len(txhash_list)
        )
    )

    # populate cache
    if payload:
        try:
            batch_responses = rpc_batch(payload)
            _logger.debug(f"Received {len(batch_responses)} responses from RPC batch")

            for response in batch_responses:
                tx_hash = tx_hash_call_id.get(response.get("id", "??"), "??")
                _logger.debug(f"Processing response for tx {tx_hash}")

                if "error" not in response or response["error"] is None:
                    if "result" not in response:
                        _logger.error(f"Missing 'result' in response for tx {tx_hash}: {response}")
                        continue

                    tx_hex = response["result"]
                    _logger.debug(f"Got valid response for tx {tx_hash}")

                    try:
                        raw_transactions_cache[tx_hash] = tx_hex
                        _logger.debug(f"Successfully cached tx {tx_hash}")
                    except Exception as e:
                        _logger.error(f"Failed to cache tx {tx_hash}: {str(e)}")
                        raise

                elif skip_missing and "error" in response and response["error"]["code"] == -5:
                    raw_transactions_cache[tx_hash] = None
                    _logger.debug(f"Missing TX skipped: {tx_hash}")
                else:
                    _logger.error(f"RPC error for tx {tx_hash}: {response.get('error')}")
                    if not skip_missing:
                        raise BackendRPCError(f"Error fetching tx {tx_hash}: {response.get('error')}")
        except Exception as e:
            _logger.error(f"Failed to fetch transactions: {str(e)}")
            raise

    # get transactions from cache
    result = {}
    for tx_hash in txhash_list:
        try:
            cached_tx = raw_transactions_cache[tx_hash]
            if cached_tx is None:
                result[tx_hash] = None
            else:
                result[tx_hash] = cached_tx["hex"] if not verbose else cached_tx
            _logger.debug(f"Retrieved tx {tx_hash} from cache")
        except KeyError as e:
            _logger.warning(
                f"Transaction {tx_hash} missing from cache after fetching. Cache stats: "
                f"size={len(raw_transactions_cache)}, noncached={len(noncached_txhashes)}"
            )
            if _retry < GETRAWTRANSACTION_MAX_RETRIES:
                _logger.info(f"Retrying fetch for tx {tx_hash} (attempt {_retry + 1})")
                time.sleep(0.05 * (_retry + 1))
                r = getrawtransaction_batch(
                    [tx_hash],
                    verbose=verbose,
                    skip_missing=skip_missing,
                    _retry=_retry + 1,
                )
                result[tx_hash] = r[tx_hash]
            else:
                _logger.error(f"Max retries exceeded for tx {tx_hash}")
                if skip_missing:
                    result[tx_hash] = None
                    continue
                raise

    return result
