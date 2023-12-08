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


def get_dispensers_by_block(params):
    payload = create_payload(
        "get_dispensers",
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


def get_dispenses_by_block(params):
    payload = create_payload(
        "get_dispenses",
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


def get_all_tx_by_block(block_index):
    return handle_cp_call_with_retry(
        func=get_block,
        params={
            "block_indexes": [block_index]
        },
        block_index=block_index
    )


def get_all_dispensers_by_block(block_index):
    return handle_cp_call_with_retry(
        func=get_dispensers_by_block,
        params={
            "filters": {
                "field": "block_index",
                "op": "==",
                "value": block_index
            }
        },
        block_index=block_index
    )


def get_all_prev_issuances_for_cpid_and_block(cpid, block_index):
    return handle_cp_call_with_retry(
        func=get_issuances,
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
        }
    )


def get_all_dispenses_by_block(block_index):
    return handle_cp_call_with_retry(
        func=get_dispenses_by_block,
        params={
            "filters": {
                "field": "block_index",
                "op": "==",
                "value": block_index
            }
        },
        block_index=block_index
    )


def parse_issuances_and_sends_from_block(block_data, db):
    issuances, sends = [], []
    cursor = db.cursor()
    block_data = json.loads(json.dumps(block_data[0]))
    dividends = []
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
                    issuance=tx_data,
                    cursor=cursor
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
        if (
            tx.get("command") == 'insert'
            and (
                (
                    tx.get('category') == 'debits'
                    or tx.get('category') == 'credits'
                )
                and tx_data.get('action') == 'dividend'
            )
        ):
            dividend = check_for_stamp_dividend(
                dividend=tx_data,
                type=tx.get('category'),
                cursor=cursor
            )
            if (dividend is not None):
                dividends.append(
                    dividend
                )
    cursor.close()
    filtered_dividends = convert_dividends_to_sends(dividends)
    sends.extend(filtered_dividends)
    return {
        "block_index": block_data["block_index"],
        "issuances": issuances,
        "sends": sends
    }


def check_for_stamp_dividend(dividend, type, cursor):
    cursor.execute(
        f"SELECT * FROM {config.STAMP_TABLE} WHERE cpid = %s",
        (dividend["asset"],)
    )
    issuance = cursor.fetchone()
    if (issuance is not None):
        filtered_dividend = {
            "cpid": dividend["asset"],
            "quantity": dividend["quantity"],
            "address": dividend["address"],
            "memo": "dividend",
            "tx_hash": dividend["event"],
            "block_index": dividend["block_index"],
            "type": type
        }
        return filtered_dividend
    return None


def convert_dividends_to_sends(dividends):
    sends = []
    source = None
    for dividend in dividends:
        if dividend["type"] == "debits":
            source = dividend["address"]
    for dividend in dividends:
        if dividend["type"] == "credits":
            send = {
                "cpid": dividend["cpid"],
                "quantity": dividend["quantity"],
                "source": source,
                "destination": dividend["address"],
                "memo": dividend["memo"],
                "tx_hash": dividend["tx_hash"],
                "block_index": dividend["block_index"]
            }
            sends.append(send)
    return sends


def parse_dispensers_from_block(dispensers, db):
    stamp_dispensers, dispensers_sends = [], []
    cursor = db.cursor()
    for dispenser in dispensers:
        stamp_dispenser, dispenser_send = check_for_stamp_dispensers(
            dispenser=dispenser,
            cursor=cursor
        )
        if stamp_dispenser and dispenser_send is not None:
            stamp_dispensers.append(
                stamp_dispenser
            )
            dispensers_sends.append(
                dispenser_send
            )
    cursor.close()
    return {
        "dispensers": stamp_dispensers,
        "sends": dispensers_sends
    }


def parse_dispenses_from_block(dispenses, db):
    dispenses_sends = []
    cursor = db.cursor()
    for dispense in dispenses:
        dispense_send = check_for_stamp_dispenses(
            dispense=dispense,
            cursor=cursor
        )
        if dispense_send is not None:
            dispenses_sends.append(
                dispense_send
            )
    cursor.close()
    return dispenses_sends


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


def check_for_stamp_issuance(issuance, cursor):
    description = issuance["description"]
    if (
        description is not None and
        description.lower().find("stamp:") != -1
    ):
        prev_qty = 0
        (
            stamp_base64,
            stamp_mimetype
        ) = parse_base64_from_description(description)
        cursor.execute(
            f"SELECT * FROM {config.STAMP_TABLE} WHERE cpid = %s",
            (issuance["asset"],)
        )
        issuances = cursor.fetchall()
        if (issuances is None):
            prev_issuances = get_all_prev_issuances_for_cpid_and_block(
                cpid=issuance["asset"],
                block_index=issuance["block_index"]
            )
            if len(prev_issuances) > 0:
                for prev_issuance in prev_issuances:
                    prev_qty += prev_issuance["quantity"]
        if issuance["status"] == "valid":
            filtered_issuance = {
                # we are not adding the base64 string to the json string
                # in issuances, this is parsed when going to StampTable
                "cpid": issuance["asset"],  # Rename 'asset' to 'cpid'
                "quantity": issuance["quantity"] + prev_qty,
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


def check_for_stamp_dispensers(dispenser, cursor):
    cursor.execute(
        f"SELECT * FROM {config.STAMP_TABLE} WHERE cpid = %s",
        (dispenser["asset"],)
    )
    issuance = cursor.fetchone()
    if (issuance is not None):
        filtered_dispenser = {
            "source": dispenser["source"],
            "origin": dispenser["origin"],
            "tx_hash": dispenser["tx_hash"],
            "block_index": dispenser["block_index"],
            "cpid": dispenser["asset"],
            "escrow_quantity": dispenser["escrow_quantity"],
            "give_quantity": dispenser["give_quantity"],
            "give_remaining": dispenser["give_remaining"],
            "satoshirate":  dispenser["satoshirate"],
            "status": dispenser["status"],
            "oracle_address": dispenser["oracle_address"],
        }
        filtered_send = {
            "cpid": dispenser["asset"],
            "quantity": dispenser["escrow_quantity"],
            "source": dispenser["origin"],
            "destination": dispenser["source"],
            "satoshirate": dispenser["satoshirate"],
            "memo": "dispenser",
            "tx_hash": dispenser["tx_hash"],
            "block_index": dispenser["block_index"]
        }
        return filtered_dispenser, filtered_send
    return None, None


def check_for_stamp_dispenses(dispense, cursor):
    cursor.execute(
        f"SELECT * FROM {config.STAMP_TABLE} WHERE cpid = %s",
        (dispense["asset"],)
    )
    issuance = cursor.fetchone()
    if (issuance is not None):
        cursor.execute(
            "SELECT satoshirate FROM dispensers WHERE tx_hash = %s",
            (dispense["dispenser_tx_hash"],)
        )
        satoshirate = cursor.fetchone()[0]
        filtered_send = {
            "cpid": dispense["asset"],
            "quantity": dispense["dispense_quantity"],
            "source": dispense["source"],
            "destination": dispense["destination"],
            "satoshirate": satoshirate,
            "memo": "dispense",
            "tx_hash": dispense["tx_hash"],
            "block_index": dispense["block_index"]
        }
        return filtered_send
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
                "memo": send.get("memo", "send"),
                "status": send["status"],
                "tx_hash": send["tx_hash"],
                "block_index": send["block_index"],
                "message_index": send["msg_index"]
            }
            return filtered_send
    return None

# DEPRECATED
#  def get_stamp_issuances(issuances):
#      stamp_issuances = []
#      for issuance in issuances:
#          filtered_issuance = check_for_stamp_issuance(issuance)
#          if (filtered_issuance is None):
#              continue
#          stamp_issuances.append(
#              json.loads(json.dumps(filtered_issuance))
#          )
#      return stamp_issuances


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


def filter_dispensers_by_tx_hash(dispensers, tx_hash):
    filtered_disp = [
        disp for disp in dispensers if disp["tx_hash"] == tx_hash
    ]
    return filtered_disp[0] if filtered_disp else None


def filter_txs_by_tx_hash(txs, tx_hash):
    filtered_txs = [
        tx for tx in txs if tx["tx_hash"] == tx_hash
    ]
    return filtered_txs if filtered_txs else None
