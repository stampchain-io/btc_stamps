import collections
import concurrent.futures
import gc
import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests
from bitcoin.core import CBlock, CTransaction, x
from requests.exceptions import ConnectionError, Timeout

import config
import index_core.util as util
from exceptions import BackendRPCError
from index_core.caching import LRUCache, cache_manager
from index_core.memory_manager import memory_manager
from index_core.parser import RUST_PARSER_AVAILABLE, Parser

# Initialize logger
logger = logging.getLogger(__name__)


class Backend:
    """Backend interface for Bitcoin RPC and transaction parsing."""

    def __init__(self):
        """Initialize the backend with caches and parser."""
        # Initialize caches
        self.raw_transactions_cache = LRUCache[Any](max_size=config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE)
        self.deserialized_tx_cache = LRUCache[Any](max_size=config.DESERIALIZED_TX_CACHE_SIZE)
        self.monotonic_call_id = 0

        # Register caches with cache manager
        cache_manager.register_cache("raw_transactions", self.raw_transactions_cache)
        cache_manager.register_cache("deserialized_tx", self.deserialized_tx_cache)

        # Initialize parser
        self._parser = None
        if RUST_PARSER_AVAILABLE and not config.DISABLE_RUST_PARSER:
            try:
                self._parser = Parser()
                logger.info("Using high-performance Rust parser")
            except Exception as e:
                logger.warning(f"Failed to initialize Rust parser: {e}. Falling back to Python parser")

        # Initialize memory manager
        self.memory_manager = memory_manager

    def rpc_call(self, payload):
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
            logger.debug(f"Batch request with {len(payload)} payload={payload}")
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
                    # logger.debug(f"Response text: {response.text}")
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
            return self.rpc_call(payload)
        else:
            raise BackendRPCError("Error connecting to {}: {}".format(util.clean_url_for_log(url), response_json["error"]))

    def rpc(self, method, params):
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": "2.0",
            "id": 0,
        }
        return self.rpc_call(payload)

    def rpc_batch(self, request_list):
        responses = collections.deque()

        def make_call(chunk):
            try:
                logger.debug(f"Making RPC batch call with {len(chunk)} requests")
                batch_responses = self.rpc_call(chunk)  # This will now return the full response array

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

    def getblockcount(self):
        return self.rpc("getblockcount", [])

    def getblockhash(self, blockcount):
        return self.rpc("getblockhash", [blockcount])

    def getblock(self, block_hash, verbosity=False):
        return self.rpc("getblock", [block_hash, verbosity])

    def getcblock(self, block_hash):
        block_hex = self.getblock(block_hash)
        return CBlock.deserialize(bytes.fromhex(block_hex))

    def getblockheader(self, block_hash):
        """Fetches the block header for a given block hash."""
        return self.rpc("getblockheader", [block_hash])

    def getrawtransaction(self, tx_hash, verbose=False, skip_missing=False, current_block=None):
        """Get raw transaction data for a single transaction."""
        return self.getrawtransaction_batch(
            [tx_hash], verbose=verbose, skip_missing=skip_missing, current_block=current_block
        )[tx_hash]

    def deserialize(self, tx_hex):
        """
        Deserialize a transaction hex string into a CTransaction object.
        Uses Rust parser if available for better performance.
        """
        # Check cache first, get() will track both hits and misses
        cached_tx = self.deserialized_tx_cache.get(tx_hex)
        if cached_tx is not None:
            return cached_tx

        if self._parser is not None:
            try:
                # Use Rust parser for better performance
                tx = self._parser.deserialize_transaction(tx_hex)
                self.deserialized_tx_cache.set(tx_hex, tx)
                return tx
            except Exception as e:
                logger.warning(f"Rust parser failed: {e}. Falling back to Python parser")

        # Fallback to Python parser
        ctx = CTransaction.deserialize(x(tx_hex))
        self.deserialized_tx_cache.set(tx_hex, ctx)
        return ctx

    def serialize(self, ctx):
        return CTransaction.serialize(ctx)

    def get_tx_list(self, block_hash):
        """Get transaction list from block using Rust parser if available."""
        if self._parser is not None:
            try:
                block_data = self.rpc("getblock", [block_hash, 0])  # Get raw block hex
                return self._parser.parse_block(block_data)
            except Exception as e:
                logger.warning(f"Rust block parser failed: {e}. Falling back to Python parser")

        # Fallback to original implementation
        block_data = self.rpc("getblock", [block_hash, 2])

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

    def getrawtransaction_batch(
        self,
        txhash_list: List[str],
        verbose: bool = False,
        skip_missing: bool = False,
        _retry: int = 0,
        max_retries: int = 3,
        current_block: Optional[int] = None,
    ) -> Dict[str, Optional[dict]]:
        """
        Fetch raw transactions in batches, with memory logging and caching.

        Args:
            txhash_list: List of transaction hashes to fetch
            verbose: Whether to return verbose transaction info
            skip_missing: Whether to skip missing transactions
            _retry: Current retry attempt (internal use)
            max_retries: Maximum number of retry attempts
            current_block: Current block number for memory logging

        Returns:
            Dict mapping transaction hashes to their raw data
        """
        # Remove duplicates while preserving order
        txhash_list = list(dict.fromkeys(txhash_list))

        # Check cache first
        noncached_txhashes = []
        cached_results = {}
        for tx_hash in txhash_list:
            # Use get() to properly track hits/misses
            cached_tx = self.raw_transactions_cache.get(tx_hash)
            if cached_tx is not None:
                cached_results[tx_hash] = cached_tx
            else:
                noncached_txhashes.append(tx_hash)

        if noncached_txhashes:
            try:
                # Process in chunks to manage memory
                chunk_size = min(len(noncached_txhashes), config.BATCH_SIZE)
                chunks = util.chunkify(noncached_txhashes, chunk_size)

                for i, chunk in enumerate(chunks):
                    # Build RPC payload
                    payload = []
                    tx_hash_call_id = {}

                    for tx_hash in chunk:
                        self.monotonic_call_id += 1
                        call_id = self.monotonic_call_id
                        tx_hash_call_id[call_id] = tx_hash

                        payload.append(
                            {"method": "getrawtransaction", "params": [tx_hash, verbose], "jsonrpc": "2.0", "id": call_id}
                        )

                    # Make RPC call
                    response = self.rpc_batch(payload)

                    # Process results
                    for result in response:
                        if "error" in result and result["error"] is not None:
                            if not skip_missing:
                                if _retry < max_retries:
                                    logger.warning(f"Error in batch, retrying: {result['error']}")
                                    time.sleep(1 * (2**_retry))  # Exponential backoff
                                    return self.getrawtransaction_batch(
                                        txhash_list,
                                        verbose=verbose,
                                        skip_missing=skip_missing,
                                        _retry=_retry + 1,
                                        max_retries=max_retries,
                                        current_block=current_block,
                                    )
                                else:
                                    raise BackendRPCError(f"Error fetching transaction: {result['error']}")
                        else:
                            tx_hash = tx_hash_call_id[result["id"]]
                            tx_result = result["result"]
                            self.raw_transactions_cache.set(tx_hash, tx_result)
                            cached_results[tx_hash] = tx_result

                    # Periodic garbage collection
                    if i % 5 == 0:  # Every 5 chunks
                        gc.collect()

                    # Check memory usage and clear caches if needed
                    self.memory_manager.clear_caches_if_needed()

            except Exception as e:
                if not skip_missing:
                    if _retry < max_retries:
                        logger.warning(f"Error in batch, retrying: {str(e)}")
                        time.sleep(1 * (2**_retry))  # Exponential backoff
                        return self.getrawtransaction_batch(
                            txhash_list,
                            verbose=verbose,
                            skip_missing=skip_missing,
                            _retry=_retry + 1,
                            max_retries=max_retries,
                            current_block=current_block,
                        )
                    else:
                        raise BackendRPCError(f"Error fetching transactions: {str(e)}")

        # Return results in original order
        return {tx_hash: cached_results.get(tx_hash) for tx_hash in txhash_list}
