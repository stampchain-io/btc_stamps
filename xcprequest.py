import time
import json
import config
import requests
from requests.auth import HTTPBasicAuth

url = config.CP_RPC_URL + "/api/rest"  # "http://public.coindaddy.io:4001"
auth = HTTPBasicAuth(config.CP_RPC_USER, config.CP_RPC_PASSWORD)

base_payload = {
  "method": "",
  "params": {},
  "jsonrpc": "2.0",
  "id": 0
}


def create_payload(method, params):
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


def get_issuances_by_block(block_index):
    while True:
        block_count = get_block_count()
        if block_index <= block_count:
            break
        else:
            print("Waiting for block {} to be parsed...".format(block_index))
            time.sleep(100)
    payload = create_payload(
        "get_issuances",
        {
            "filters": {
                "field": "block_index",
                "op": "==",
                "value": block_index
            }
        }
    )
    headers = {'content-type': 'application/json'}
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers=headers,
        auth=auth
    )
    return json.loads(response.text)["result"]


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
                "source": issuance["source"],
                "issuer": issuance["issuer"],
                "transfer": issuance["transfer"],
                "description": issuance["description"],
                "reset": issuance["reset"],
                "status": issuance["status"],
                "asset_longname": issuance.get("asset_longname", ""),
                "tx_hash": issuance["tx_hash"],
                "msg_index": issuance["msg_index"],
                "stamp_mimetype": stamp_mimetype
            }
            stamp_issuances.append(json.dump(filtered_issuance))
    return stamp_issuances


def filter_issuances_by_tx_hash(issuances, tx_hash):
    filtered_issuances = [issuance for issuance in issuances if issuance["tx_hash"] == tx_hash]
    return filtered_issuances[0] if filtered_issuances else None