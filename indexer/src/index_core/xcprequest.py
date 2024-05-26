import concurrent.futures
import json
import logging
import time

import requests
from tqdm import tqdm

import config
import index_core.util as util

logger = logging.getLogger(__name__)

url = config.CP_RPC_URL
auth = config.CP_AUTH


def _create_payload(method, params):
    base_payload = {
        "method": "",
        "params": {},
        "jsonrpc": "2.0",
        "id": 0
    }
    base_payload["method"] = method
    base_payload["params"] = params
    return base_payload


def fetch_cp_concurrent(block_index, block_tip, indicator=None):
    ''' testing with this method because we were initially getting invalid results
        when using the get_blocks[xxx,yyyy,zzz] method to the CP API '''
    with concurrent.futures.ThreadPoolExecutor() as executor:

        blocks_to_fetch = 1000
        futures = []
        results_dict = {}  # Create an empty dictionary to store the results

        if block_tip > block_index + blocks_to_fetch:
            block_tip = block_index + blocks_to_fetch
        else:
            blocks_to_fetch = block_tip - block_index + 1

        pbar = tqdm(total=blocks_to_fetch, desc=f"Fetching CP Trx [{block_index}..{block_tip}]", leave=True)  # Update the total to 500 and add leave=True

        while block_index <= block_tip:
            future = executor.submit(get_xcp_block_data, block_index, indicator=indicator)
            future.block_index = block_index  # Save the block_index with the future
            futures.append(future)
            block_index += 1

        # Process the results as they become available
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results_dict[future.block_index] = result  # Store the result in the dictionary using future.block_index as the key
            pbar.update(1)  # Update the progress bar

        pbar.close()  # Close the progress bar

        # Sort the results_dict based on block_index
        sorted_results = dict(sorted(results_dict.items(), key=lambda x: x[0]))
    return sorted_results


def _handle_cp_call_with_retry(func, params, block_index, indicator=None):
    if indicator is not None:
        pbar = tqdm(desc="Waiting for CP block {} to be parsed...".format(block_index), leave=True, bar_format='{desc}: {elapsed} {bar} [{postfix}]')

    while util.CP_BLOCK_COUNT is None or block_index > util.CP_BLOCK_COUNT:
        try:
            util.CP_BLOCK_COUNT = _get_block_count()
            logger.info("Current block count: {}".format(util.CP_BLOCK_COUNT))
            if (util.CP_BLOCK_COUNT is not None and block_index <= util.CP_BLOCK_COUNT):
                if indicator is not None:
                    pbar.close()
                break
            else:
                if indicator is not None:
                    pbar.refresh()
                time.sleep(config.BACKEND_POLL_INTERVAL)
        except (TypeError, Exception) as e:
            logger.warning("Error getting CP block count: {}\nSleeping to retry...".format(e))
            time.sleep(config.BACKEND_POLL_INTERVAL)
    data = None
    while data is None:
        try:
            if util.CP_BLOCK_COUNT is not None:
                data = func(params=params)
                if data is not None:
                    return data
            else:
                logger.warning("CP_BLOCK_COUNT is None. Sleeping to retry...")
                time.sleep(config.BACKEND_POLL_INTERVAL)
        except Exception as e:
            logger.warning("Error getting issuances: {}\n Sleeping to retry...".format(e))
            time.sleep(config.BACKEND_POLL_INTERVAL)


def get_cp_version():
    try:
        logger.warning(f"""Connecting to CP Node: {config.CP_RPC_URL}""")
        payload = _create_payload("get_running_info", {})
        headers = {'content-type': 'application/json'}
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            auth=auth,
            timeout=10
        )
        result = json.loads(response.text)["result"]
        version_major = result["version_major"]
        version_minor = result["version_minor"]
        version_revision = result["version_revision"]
        version = ".".join(
            [
                str(version_major),
                str(version_minor),
                str(version_revision)
            ]
        )
        return version
    except Exception as e:
        logger.warning(
            "Error getting version info: {}".format(e)
        )
        return None


def _get_block_count():
    result = None
    try:
        payload = _create_payload("get_running_info", {})
        headers = {'content-type': 'application/json'}
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            auth=auth,
            timeout=10
        )
        logger.info("get_block_count response: {}".format(response.text))
        result = json.loads(response.text)["result"]
        if result["last_block"] is None:
            return None
        return result["last_block"]["block_index"]
    except Exception as e:
        print(result)
        logger.warning(
            "Error getting CP block count: {}".format(e)
        )
        return None


def _get_issuances(params={}):
    payload = _create_payload(
        "get_issuances",
        params
    )
    headers = {'content-type': 'application/json'}
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers=headers,
        auth=auth,
        timeout=10
    )
    return json.loads(response.text)["result"]


def _get_sends(params={}):
    payload = _create_payload(
        "get_sends",
        params
    )
    headers = {'content-type': 'application/json'}
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers=headers,
        auth=auth,
        timeout=10
    )
    return json.loads(response.text)["result"]


def _get_block(params={}):
    payload = _create_payload(
        "get_blocks",
        params
    )
    headers = {'content-type': 'application/json'}
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers=headers,
        auth=auth,
        timeout=10
    )
    return json.loads(response.text)["result"]


def _get_issuances_by_block(block_index):
    return _handle_cp_call_with_retry(
        func=_get_issuances,
        params={
            "filters": {
                "field": "block_index",
                "op": "==",
                "value": block_index
            }
        },
        block_index=block_index
    )


def _get_all_tx_by_block(block_index, indicator=None):
    return _handle_cp_call_with_retry(
        func=_get_block,
        params={
            "block_indexes": [block_index]
        },
        block_index=block_index,
        indicator=indicator
    )


def _get_all_prev_issuances_for_cpid_and_block(cpid, block_index):
    return _handle_cp_call_with_retry(
        func=_get_issuances,
        params={
            "filters": [
                {
                    "field": "block_index",
                    "op": "<",
                    "value": block_index
                },
                {
                    "field": "asset",
                    "op": "==",
                    "value": cpid
                }
            ]
        },
        block_index=block_index
    )


def get_xcp_block_data(block_index, indicator=None):
    block_data_from_xcp = _get_all_tx_by_block(block_index, indicator=indicator)
    parsed_block_data = _parse_issuances_from_block(block_data=block_data_from_xcp)
    stamp_issuances = parsed_block_data['issuances']
    # logger.warning(
    #     f"""
    #     XCP Block {block_index}
    #     - {len(stamp_issuances)} issuances
    #     """
    # )
    return stamp_issuances


def _parse_issuances_from_block(block_data):
    issuances = []
    block_data = json.loads(json.dumps(block_data[0]))
    for tx in block_data['_messages']:
        tx_data = json.loads(tx.get('bindings'))
        tx_data['msg_index'] = tx.get('message_index')
        tx_data['block_index'] = tx.get('block_index')
        if (
            tx.get("command") == 'insert' and tx.get("category") == 'issuances'
        ):
            if (
                tx_data.get('status', 'invalid') == 'valid'
            ):
                stamp_issuance = _check_for_stamp_issuance(issuance=tx_data)
                if stamp_issuance is not None:
                    issuances.append(
                        stamp_issuance
                    )
    return {
        "block_index": block_data["block_index"],
        "issuances": issuances,
    }


def parse_base64_from_description(description):
    if description is not None and description.lower().find("stamp:") != -1:
        stamp_search = description[description.lower().find("stamp:") + 6:]
        stamp_search = stamp_search.strip()
        if ";" in stamp_search:
            stamp_mimetype, stamp_base64 = stamp_search.split(";", 1)
            stamp_mimetype = (
                stamp_mimetype.strip()
                if len(stamp_mimetype) <= 255
                else ""
            )  # db limit
            stamp_base64 = (
                stamp_base64.strip()
                if len(stamp_base64) > 1
                else None
            )
        else:
            stamp_mimetype = ""
            stamp_base64 = (
                stamp_search.strip()
                if len(stamp_search) > 1
                else None
            )

        return stamp_base64, stamp_mimetype
    else:
        return None, None


def _check_for_stamp_issuance(issuance):
    description = issuance["description"]

    if (
        description is not None and description.lower().find("stamp:") != -1
    ):
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
                "asset_longname": (
                    issuance["asset_longname"]
                    if "asset_longname" in issuance
                    else ""  # TODO change to NULL
                ),
                "tx_hash": issuance["tx_hash"],
                "message_index": issuance["msg_index"],
                "stamp_mimetype": stamp_mimetype
            }
        return filtered_issuance
    return None


def filter_issuances_by_tx_hash(issuances, tx_hash):
    filtered_issuances = [
        issuance for issuance in issuances if issuance["tx_hash"] == tx_hash
    ]
    return filtered_issuances[0] if filtered_issuances else None
