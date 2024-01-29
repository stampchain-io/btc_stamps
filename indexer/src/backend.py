import json
import requests
from requests.exceptions import Timeout, ConnectionError
import time
import concurrent.futures
import collections
import binascii
import hashlib
import config
import src.util as util

import bitcoin as bitcoinlib
from bitcoin.core import CBlock

import logging
logger = logging.getLogger(__name__)

raw_transactions_cache = util.DictCache(
    size=config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE
)  # used in getrawtransaction_batch()


class BackendRPCError(Exception):
    pass


def rpc_call(payload):
    """Calls to bitcoin core and returns the response"""
    url = config.RPC_URL
    response = None
    TRIES = 12

    for i in range(TRIES):
        try:
            response = requests.post(
                url, data=json.dumps(payload),
                headers={'content-type': 'application/json'},
                verify=(not config.BACKEND_SSL_NO_VERIFY),
                timeout=config.REQUESTS_TIMEOUT
            )
            if i > 0:
                logger.debug('Successfully connected.')
            break
        except (Timeout, ConnectionError):
            logger.debug(
                'Could not connect to backend at `{}`. (Try {}/{})'
                .format(util.clean_url_for_log(url), i+1, TRIES)
            )
            time.sleep(5)
    if response is None:
        if config.TESTNET:
            network = 'testnet'
        elif config.REGTEST:
            network = 'regtest'
        else:
            network = 'mainnet'
        raise BackendRPCError(
            '''
            Cannot communicate with backend at `{}`.
            (server is set to run on {}, is backend?
            '''
            .format(util.clean_url_for_log(url), network)
        )
    elif response.status_code in (401,):
        raise BackendRPCError(
            'Authorization error connecting to {}: {} {}'
            .format(
                util.clean_url_for_log(url),
                response.status_code,
                response.reason
            )
        )
    elif response.status_code not in (200, 500, 503):
        raise BackendRPCError(
            f"{response.status_code} {response.reason}"
        )

    # Handle json decode errors
    try:
        response_json = response.json()
    except json.decoder.JSONDecodeError as e:
        raise BackendRPCError(
            f'''
            Received invalid JSON from backend with a response of:
            {response.status_code} {response.reason}
            '''
        )

    # Batch query returns a list
    if isinstance(response_json, list):
        return response_json
    if 'error' not in response_json.keys() or response_json['error'] is None:
        return response_json['result']
    elif response_json['error']['code'] == -5:   # RPC_INVALID_ADDRESS_OR_KEY
        raise BackendRPCError('{} Is `txindex` enabled in {} Core?'.format(
            response_json['error'], config.BTC_NAME
        ))
    elif response_json['error']['code'] in [-28, -8, -2]:
        # “Verifying blocks...” or “Block height out of range” or “The network does not appear to fully agree!“
        logger.debug('Backend not ready. Sleeping for ten seconds.')
        # If Bitcoin Core takes more than `sys.getrecursionlimit() * 10 = 9970`
        # seconds to start, this’ll hit the maximum recursion depth limit.
        time.sleep(10)
        return rpc_call(payload)
    else:
        raise BackendRPCError('Error connecting to {}: {}'.format(util.clean_url_for_log(url), response_json['error']))


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
        #send a list of requests to bitcoind to be executed
        #note that this is list executed serially, in the same thread in bitcoind
        #e.g. see: https://github.com/bitcoin/bitcoin/blob/master/src/rpcserver.cpp#L939
        responses.extend(rpc_call(chunk))

    chunks = util.chunkify(request_list, config.RPC_BATCH_SIZE)
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.BACKEND_RPC_BATCH_NUM_WORKERS) as executor:
        for chunk in chunks:
            executor.submit(make_call, chunk)
    return list(responses)


def getblockcount():
    return rpc('getblockcount', [])


def getblockhash(blockcount):
    return rpc('getblockhash', [blockcount])


def getblock(block_hash): # returns a hex string
    return rpc('getblock', [block_hash, False])


def getcblock(block_hash):
    block_hex = getblock(block_hash)
    return CBlock.deserialize(bytes.fromhex(block_hex))


def getrawtransaction(tx_hash, verbose=False, skip_missing=False):
    return getrawtransaction_batch([tx_hash], verbose=verbose, skip_missing=skip_missing)[tx_hash]


def deserialize(tx_hex):
    return bitcoinlib.core.CTransaction.deserialize(binascii.unhexlify(tx_hex))


def serialize(ctx):
    return bitcoinlib.core.CTransaction.serialize(ctx)


def get_tx_list(block):
    raw_transactions = {}
    tx_hash_list = []

    for ctx in block.vtx:
        if util.enabled('correct_segwit_txids'): # always enabled
            # This differs from the transactions hash as given by GetHash. GetTxid excludes witness data, while GetHash includes it
            hsh = ctx.GetTxid()
        else:
            hsh = ctx.GetHash()
        tx_hash = bitcoinlib.core.b2lx(hsh)
        raw = ctx.serialize()

        tx_hash_list.append(tx_hash)
        raw_transactions[tx_hash] = bitcoinlib.core.b2x(raw)
    return (tx_hash_list, raw_transactions)


GETRAWTRANSACTION_MAX_RETRIES = 2
monotonic_call_id = 0


def getrawtransaction_batch(txhash_list, verbose=False, skip_missing=False, _retry=0):
    _logger = logger.getChild("getrawtransaction_batch")

    if len(txhash_list) > config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE:
        #don't try to load in more than BACKEND_RAW_TRANSACTIONS_CACHE_SIZE entries in a single call
        txhash_list_chunks = util.chunkify(txhash_list, config.BACKEND_RAW_TRANSACTIONS_CACHE_SIZE)
        txes = {}
        for txhash_list_chunk in txhash_list_chunks:
            txes.update(getrawtransaction_batch(txhash_list_chunk, verbose=verbose, skip_missing=skip_missing))
        return txes

    tx_hash_call_id = {}
    payload = []
    noncached_txhashes = set()

    txhash_list = set(txhash_list)

    # payload for transactions not in cache
    for tx_hash in txhash_list:
        if tx_hash not in raw_transactions_cache:
            #call_id = binascii.hexlify(os.urandom(5)).decode('utf8') # Don't drain urandom
            global monotonic_call_id
            monotonic_call_id = monotonic_call_id + 1
            call_id = "{}".format(monotonic_call_id)
            payload.append({
                "method": 'getrawtransaction',
                "params": [tx_hash, 1],
                "jsonrpc": "2.0",
                "id": call_id
            })
            noncached_txhashes.add(tx_hash)
            tx_hash_call_id[call_id] = tx_hash
    #refresh any/all cache entries that already exist in the cache,
    # so they're not inadvertently removed by another thread before we can consult them
    #(this assumes that the size of the working set for any given workload doesn't exceed the max size of the cache)
    for tx_hash in txhash_list.difference(noncached_txhashes):
        raw_transactions_cache.refresh(tx_hash)

    _logger.debug("getrawtransaction_batch: txhash_list size: {} / raw_transactions_cache size: {} / # getrawtransaction calls: {}".format(
        len(txhash_list), len(raw_transactions_cache), len(payload)))

    # populate cache
    if payload:
        batch_responses = rpc_batch(payload)
        for response in batch_responses:
            if 'error' not in response or response['error'] is None:
                tx_hex = response['result']
                tx_hash = tx_hash_call_id[response['id']]
                raw_transactions_cache[tx_hash] = tx_hex
            elif skip_missing and 'error' in response and response['error']['code'] == -5:
                raw_transactions_cache[tx_hash] = None
                logging.debug('Missing TX with no raw info skipped (txhash: {}): {}'.format(
                    tx_hash_call_id.get(response.get('id', '??'), '??'), response['error']))
            else:
                #TODO: this seems to happen for bogus transactions? Maybe handle it more gracefully than just erroring out?
                raise BackendRPCError('{} (txhash:: {})'.format(response['error'], tx_hash_call_id.get(response.get('id', '??'), '??')))

    # get transactions from cache
    result = {}
    for tx_hash in txhash_list:
        try:
            if verbose:
                result[tx_hash] = raw_transactions_cache[tx_hash]
            else:
                result[tx_hash] = raw_transactions_cache[tx_hash]['hex'] if raw_transactions_cache[tx_hash] is not None else None
        except KeyError as e: #shows up most likely due to finickyness with addrindex not always returning results that we need...
            print("Key error in addrindexrs still exists!!!!!")
            _logger.warning("tx missing in rawtx cache: {} -- txhash_list size: {}, hash: {} / raw_transactions_cache size: {} / # rpc_batch calls: {} / txhash in noncached_txhashes: {} / txhash in txhash_list: {} -- list {}".format(
                e, len(txhash_list), hashlib.md5(json.dumps(list(txhash_list)).encode()).hexdigest(), len(raw_transactions_cache), len(payload),
                tx_hash in noncached_txhashes, tx_hash in txhash_list, list(txhash_list.difference(noncached_txhashes)) ))
            if  _retry < GETRAWTRANSACTION_MAX_RETRIES: #try again
                time.sleep(0.05 * (_retry + 1)) # Wait a bit, hitting the index non-stop may cause it to just break down... TODO: Better handling
                r = getrawtransaction_batch([tx_hash], verbose=verbose, skip_missing=skip_missing, _retry=_retry+1)
                result[tx_hash] = r[tx_hash]
            else:
                raise  #already tried again, give up

    return result
