
import json
import config
import logging
logger = logging.getLogger(__name__)
import requests
from requests.auth import HTTPBasicAuth

url = config.CP_RPC_URL + "/api" # "http://public.coindaddy.io:4000/api/"
auth = HTTPBasicAuth(config.CP_RPC_USER, config.CP_RPC_PASSWORD)

base_payload = {
  "method": "",
  "params": {},
  "jsonrpc": "2.0",
  "id": 0
}

def creat_payload(method, params):
    base_payload["method"] = method
    base_payload["params"] = params
    return base_payload

# counterparty public node: https://public.coindaddy.io:4000/api/b

def get_issuances_by_block(block_index):
    payload = creat_payload("get_issuances", {"filters": { "field": "block_index", "op" : "==", "value" : block_index }})
    headers = {'content-type': 'application/json'}
    response = requests.post(url, data=json.dumps(payload), headers=headers, auth=auth)
    logger.warning("Response: {}".format( response))
    
    return response.text

def get_stamp_issuances(issuances):
    stamp_issuances = []
    for issuance in issuances:
        if issuance["description"].tolowercase().startswith("stamp:"):
            stamp_issuances.append(issuance)
    return stamp_issuances

