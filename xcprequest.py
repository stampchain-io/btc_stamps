import time
import json
import config
import requests
from requests.auth import HTTPBasicAuth
import logging

logger = logging.getLogger(__name__)


url = config.CP_RPC_URL + "/api/rest"  # "http://public.coindaddy.io:4001"
auth = HTTPBasicAuth(config.CP_RPC_USER, config.CP_RPC_PASSWORD)


def create_payload(method, params):
    base_payload = {
        "method": "",
        "params": {},
        "jsonrpc": "2.0",
        "id": 0
    }
    base_payload["method"] = method
    base_payload["params"] = params
    return base_payload


def get_block_count():
    payload = create_payload("get_running_info", {})
    headers = {'content-type': 'application/json'}
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers=headers,
        auth=auth
    )
    return json.loads(response.text)["result"]["last_block"]["block_index"]


def get_issuances(params={}):
    payload = create_payload(
        "get_issuances",
        params
    )
    headers = {'content-type': 'application/json'}
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers=headers,
        auth=auth
    )
    return json.loads(response.text)["result"]


def get_issuances_by_block(block_index):
    while True:
        try:
            block_count = get_block_count()
            if block_index <= block_count:
                break
            else:
                logger.warning(
                    "Waiting for block {} to be parsed...".format(block_index)
                )
                time.sleep(100)
        except Exception as e:
            logger.warning(
                "Error getting block count: {}\nSleeping to retry...".format(e)
            )
            time.sleep(100)
    while True:
        try:
            return get_issuances(
                params={
                    "filters": {
                        "field": "block_index",
                        "op": "==",
                        "value": block_index
                    }
                }
            )
        except Exception as e:
            logger.warning(
                "Error getting issuances: {}\n Sleeping to retry...".format(e)
            )
            time.sleep(100)


def get_stamp_issuances(issuances):
    stamp_issuances = []
    for issuance in issuances:
        description = issuance["description"]
        if description is not None and description.lower().find("stamp:") != -1:
            stamp_search = description[description.lower().find("stamp:") + 6:]
            stamp_search = stamp_search.strip()
            if ";" in stamp_search:
                stamp_mimetype, stamp_base64 = stamp_search.split(";", 1)
                stamp_base64 = stamp_base64.strip() if len(stamp_base64) > 1 else None
            else:
                stamp_mimetype = ""
                stamp_base64 = stamp_search.strip() if len(stamp_search) > 1 else None

            filtered_issuance = {
                "cpid": issuance["asset"],  # Renombrar 'asset' a 'cp_id'
                "quantity": issuance["quantity"],
                "divisible": issuance["divisible"],
                "locked": issuance["locked"],
                "source": issuance["source"],
                "issuer": issuance["issuer"],
                "transfer": issuance["transfer"],
                "description": issuance["description"],
                "reset": issuance["reset"],
                "status": issuance["status"],
                "asset_longname":
                    issuance["asset_longname"] if "asset_longname" in issuance else "",
                "tx_hash": issuance["tx_hash"],
                "message_index": issuance["msg_index"],
                "stamp_mimetype": stamp_mimetype
            }
            stamp_issuances.append(json.loads(json.dumps(filtered_issuance)))
    return stamp_issuances


def filter_issuances_by_tx_hash(issuances, tx_hash):
    filtered_issuances = [
        issuance for issuance in issuances if issuance["tx_hash"] == tx_hash
    ]
    return filtered_issuances[0] if filtered_issuances else None
