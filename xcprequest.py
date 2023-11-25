import time
import json
import config
import requests
import logging
import src.util as util

logger = logging.getLogger(__name__)

url = config.CP_RPC_URL
auth = config.CP_AUTH


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
    try:
        payload = create_payload("get_running_info", {})
        headers = {'content-type': 'application/json'}
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            auth=auth
        )
        return json.loads(response.text)["result"]["last_block"]["block_index"]
    except Exception as e:
        logger.warning(
            "Error getting block count: {}".format(e)
        )
        return None


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
    while util.CP_BLOCK_COUNT is None and block_index > util.CP_BLOCK_COUNT:
        try:
            util.CP_BLOCK_COUNT = get_block_count()
            if (
                util.CP_BLOCK_COUNT is not None
                and block_index <= util.CP_BLOCK_COUNT
            ):
                break
            else:
                logger.warning(
                    "Waiting for block {} to be parsed...".format(block_index)
                )
                time.sleep(config.BACKEND_POLL_INTERVAL)
        except Exception as e:
            logger.warning(
                "Error getting block count: {}\nSleeping to retry...".format(e)
            )
            time.sleep(config.BACKEND_POLL_INTERVAL)
    issuances = None
    while issuances is None:
        try:
            issuances = get_issuances(
                params={
                    "filters": {
                        "field": "block_index",
                        "op": "==",
                        "value": block_index
                    }
                }
            )
            if issuances is not None:
                return issuances
        except Exception as e:
            logger.warning(
                "Error getting issuances: {}\n Sleeping to retry...".format(e)
            )
            time.sleep(config.BACKEND_POLL_INTERVAL)


def parse_base64_from_description(description):
    if description is not None and description.lower().find("stamp:") != -1:
        stamp_search = description[description.lower().find("stamp:") + 6:]
        stamp_search = stamp_search.strip()
        if ";" in stamp_search:
            stamp_mimetype, stamp_base64 = stamp_search.split(";", 1)
            stamp_mimetype = stamp_mimetype.strip() if len(stamp_mimetype) <= 255 else "" # db limit
            stamp_base64 = stamp_base64.strip() if len(stamp_base64) > 1 else None
        else:
            stamp_mimetype = ""
            stamp_base64 = stamp_search.strip() if len(stamp_search) > 1 else None

        # this is new for 'A5479569622374092000' which was included in production, but rejected here
        # NOTE: this was not part of prior production code validation
        # we may need to activate this at a block height once we validate data
        # if stamp_base64 is not None:
        #     stamp_base64 = re.sub(r'[^a-zA-Z0-9+/=]', '', stamp_base64)

        return stamp_base64, stamp_mimetype
    else:
        return None, None


def get_stamp_issuances(issuances):
    stamp_issuances = []
    for issuance in issuances:
        description = issuance["description"]
        if (
            description is not None and
            description.lower().find("stamp:") != -1
        ):
            (
                stamp_base64,
                stamp_mimetype
            ) = parse_base64_from_description(description)

            if issuance["status"] == "valid":
                filtered_issuance = {
                    # we are not adding the base64 string to the json string in issuances, this is parsed when going to StampTable
                    "cpid": issuance["asset"],  # Rename 'asset' to 'cpid'
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
