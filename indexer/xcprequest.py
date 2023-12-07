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


def handle_cp_call_with_retry(func, params, block_index):
    while util.CP_BLOCK_COUNT is None or block_index > util.CP_BLOCK_COUNT:
        try:
            util.CP_BLOCK_COUNT = get_block_count()
            logger.info("Current block count: {}".format(util.CP_BLOCK_COUNT))
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
    data = None
    while data is None:
        try:
            data = func(params=params)
            if data is not None:
                return data
        except Exception as e:
            logger.warning(
                "Error getting issuances: {}\n Sleeping to retry...".format(e)
            )
            time.sleep(config.BACKEND_POLL_INTERVAL)


def get_cp_version():
    try:
        logger.info("Connecting to CP Node: {}".format(config.CP_RPC_URL))
        payload = create_payload("get_running_info", {})
        headers = {'content-type': 'application/json'}
        response = requests.post(
            url,
            data=json.dumps(payload),
            headers=headers,
            auth=auth
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
        logger.info("get_block_count response: {}".format(response.text))
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


def get_block(params={}):
    payload = create_payload(
        "get_blocks",
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
    return handle_cp_call_with_retry(
        func=get_issuances,
        params={
            "filters": {
                "field": "block_index",
                "op": "==",
                "value": block_index
            }
        },
        block_index=block_index
    )


def get_all_tx_by_block(block_index):
    return handle_cp_call_with_retry(
        func=get_block,
        params={
            "block_indexes": [block_index]
        },
        block_index=block_index
    )


def parse_issuances_and_sends_from_block(block_data, db):
    issuances, sends = [], []
    cursor = db.cursor()
    block_data = json.loads(json.dumps(block_data[0]))
    for tx in block_data['_messages']:
        tx_data = json.loads(tx.get('bindings'))
        tx_data['msg_index'] = tx.get('message_index')
        tx_data['block_index'] = tx.get('block_index')
        if (
            tx.get("command") == 'insert'
            and tx.get("category") == 'issuances'
        ):
            if (
                tx_data.get('status', 'invalid') == 'valid'
            ):
                stamp_issuance = check_for_stamp_issuance(
                    issuance=tx_data
                )
                if stamp_issuance is not None:
                    issuances.append(
                        stamp_issuance
                    )
        if (
            tx.get("command") == 'insert'
            and tx.get("category") == 'sends'
        ):
            if (
                tx_data.get('status', 'invalid') == 'valid'
            ):
                stamp_send = check_for_stamp_send(
                    send=tx_data,
                    cursor=cursor
                )
                if stamp_send is not None:
                    sends.append(
                        stamp_send
                    )
    cursor.close()
    return {
        "block_index": block_data["block_index"],
        "issuances": issuances,
        "sends": sends
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

        # this is new for 'A5479569622374092000' which was included in
        # production, but rejected here
        # NOTE: this was not part of prior production code validation
        # we may need to activate this at a block height once we validate data
        # if stamp_base64 is not None:
        #     stamp_base64 = re.sub(r'[^a-zA-Z0-9+/=]', '', stamp_base64)

        return stamp_base64, stamp_mimetype
    else:
        return None, None


def check_for_stamp_issuance(issuance):
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
                # we are not adding the base64 string to the json string
                # in issuances, this is parsed when going to StampTable
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
                "asset_longname": (
                    issuance["asset_longname"]
                    if "asset_longname" in issuance
                    else ""
                ),
                "tx_hash": issuance["tx_hash"],
                "message_index": issuance["msg_index"],
                "stamp_mimetype": stamp_mimetype
            }
            return filtered_issuance
    return None


def check_for_stamp_send(send, cursor):
    if send["status"] == "valid":
        cursor.execute(
            f"SELECT * FROM {config.STAMP_TABLE} WHERE cpid = %s",
            (send["asset"],)
        )
        issuance = cursor.fetchone()
        if (issuance is not None):
            filtered_send = {
                "cpid": send["asset"],
                "quantity": send["quantity"],
                "source": send["source"],
                "destination": send["destination"],
                "memo": send["memo"],
                "status": send["status"],
                "tx_hash": send["tx_hash"],
                "block_index": send["block_index"],
                "message_index": send["msg_index"]
            }
            return filtered_send
    return None


def get_stamp_issuances(issuances):
    stamp_issuances = []
    for issuance in issuances:
        filtered_issuance = check_for_stamp_issuance(issuance)
        if (filtered_issuance is None):
            continue
        stamp_issuances.append(
            json.loads(json.dumps(filtered_issuance))
        )
    return stamp_issuances


def get_stamp_sends(sends, db):
    cursor = db.cursor()
    stamp_sends = []
    for send in sends:
        filtered_send = check_for_stamp_send(send, cursor)
        if (filtered_send is None):
            continue
        stamp_sends.append(
            json.loads(json.dumps(filtered_send))
        )


def filter_issuances_by_tx_hash(issuances, tx_hash):
    filtered_issuances = [
        issuance for issuance in issuances if issuance["tx_hash"] == tx_hash
    ]
    return filtered_issuances[0] if filtered_issuances else None


def filter_sends_by_tx_hash(sends, tx_hash):
    filtered_sends = [
        send for send in sends if send["tx_hash"] == tx_hash
    ]
    return filtered_sends if filtered_sends else None
