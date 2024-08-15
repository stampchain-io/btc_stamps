import base64
import decimal
import hashlib
import json
import logging
import re
from typing import Optional, TypedDict, Union

import index_core.log as log
from config import SRC101_IMG_URL_PREFIX, SRC101_OWNERS_TABLE, SRC101_TABLE, SRC101_VALID_TABLE
from index_core.database import get_src101_deploy, get_src101_price
from index_core.util import (
    check_contains_special,
    check_valid_base64_string,
    check_valid_bitcoin_address,
    check_valid_eth_address,
    check_valid_tx_hash,
    escape_non_ascii_characters,
)

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)


class Src101Dict(TypedDict, total=False):
    tick: Optional[str]
    tokenid: Optional[str]
    hash: Optional[str]
    p: Optional[str]
    op: Optional[str]
    type: Optional[str]
    data: Optional[str]
    owner: Optional[str]
    toaddress: Optional[str]
    rec: Optional[str]
    prim: Optional[bool]
    holders_of: Optional[str]
    dua: Optional[Union[str, D]]
    lim: Optional[Union[str, D]]
    mintstart: Optional[Union[str, D]]
    mintend: Optional[Union[str, D]]
    pri: Optional[Union[str, D]]
    status: Optional[str]
    tick_hash: Optional[str]
    tokenid_utf8: Optional[str]


class Src101Validator:
    def __init__(self, src101_dict):
        self.src101_dict = src101_dict
        self.validation_errors = []

    def process_values(self):
        num_pattern = re.compile(r"^[0-9]*(\.[0-9]*)?$")
        # dec_pattern = re.compile(r"^[0-9]+$")

        for key, value in list(self.src101_dict.items()):
            if value == "":
                self.src101_dict[key] = None
            elif key in ["tick"]:
                self._process_tick_value(key, value)
            elif key in ["tokenid"]:
                self._process_tokenid_value(key, value)
            elif key in ["hash"]:
                self._process_hash_value(key, value)
            elif key in ["prim"]:
                self._process_bool_value(key, value)
            elif key in ["type", "data"]:
                self._process_type_data_value(key, value)
            elif key in ["owner", "toaddress"]:
                self._prceess_address_value(key, value)
            elif key in ["rec"]:
                self._process_addresslist_value(key, value)
            elif key in ["p", "op"]:
                self._process_uppercase_value(key, value)
            elif key in ["root"]:
                self._process_lowercase_value(key, value)
            elif key in ["lim", "dua", "mintstart", "mintend"]:
                self._apply_regex_validation(key, value, num_pattern)

        if "type" in self.src101_dict.keys() and "data" in self.src101_dict.keys():
            self.src101_dict[self.src101_dict["type"] + "_data"] = self.src101_dict["data"]
        return self.src101_dict

    def _apply_regex_validation(self, key, value, num_pattern):
        if key in ["lim", "dua", "mintstart", "mintend", "pri"]:
            if num_pattern.match(str(value)):
                self.src101_dict[key] = int(value)
            else:
                self._update_status(key, f"NN: INVALID NUM for {key}")
                self.src101_dict[key] = None

    def _update_status(self, key, message):
        error_message = f"{key}: {message}"
        self.validation_errors.append(error_message)

        if "status" in self.src101_dict:
            self.src101_dict["status"] += f", {error_message}"
        else:
            self.src101_dict["status"] = error_message

    def _process_tick_value(self, key, value):
        self.src101_dict[key] = value.lower()
        self.src101_dict[key] = escape_non_ascii_characters(self.src101_dict[key])
        self.src101_dict[key + "_hash"] = self.create_tick_hash(value.lower())

    def _process_bool_value(self, key, value):
        if value == "true":
            self.src101_dict[key] = True
        elif value == "false":
            self.src101_dict[key] = False
        else:
            self._update_status(key, f"IP: INVALID PRIM VAL {value}")

    def _process_hash_value(self, key, value):
        valid = check_valid_tx_hash(value)
        if valid:
            self.src101_dict["deploy_hash"] = str(value)
        else:
            self._update_status(key, f"IH: INVALID HASH VAL {value}")
            self.src101_dict[key] = None

    def _process_type_data_value(self, key, value):
        self.src101_dict[key] = value

    def _process_addresslist_value(self, key, value):
        try:
            valid = True
            for a in value:
                valid and check_valid_bitcoin_address(a)
            if valid and type(value) == list:
                self.src101_dict[key] = value
            else:
                self._update_status(key, f"IAL: INVALID ADDRESSLIST VAL {value}")
                self.src101_dict[key] = None
        except:
            self._update_status(key, f"IAL: INVALID ADDRESSLIST VAL {value}")
            self.src101_dict[key] = None

    def _prceess_address_value(self, key, value):
        valid = check_valid_bitcoin_address(value)
        if valid:
            self.src101_dict[key] = str(value)
        else:
            self._update_status(key, f"IA: INVALID ADDRESS VAL {value}")
            self.src101_dict[key] = None

    def _process_tokenid_value(self, key, value):
        if type(value) == list:
            valid = True
            utf8valuelist = []
            for v in value:
                valid = valid and check_valid_base64_string(v)
                try:
                    utf8value = base64.urlsafe_b64decode(v).decode("utf-8")
                    utf8value = utf8value.lower()
                    if len(v) > 128:
                        valid = False
                    if utf8value in utf8valuelist:
                        valid = False
                    elif check_contains_special(utf8value):
                        valid = False
                    else:
                        utf8valuelist.append(utf8value)
                except Exception as e:
                    valid = False
            if valid:
                self.src101_dict[key] = value
                self.src101_dict[key + "_utf8"] = utf8valuelist
            else:
                self._update_status(key, f"IT: INVALID TOKENID VAL {value}")
                self.src101_dict[key] = None
                self.src101_dict[key + "_utf8"] = None
        elif type(value) == str:
            valid = check_valid_base64_string(value)
            if len(value) > 128:
                valid = False
            if valid:
                self.src101_dict[key] = value
                self.src101_dict[key + "_utf8"] = base64.b64decode(value).decode("utf8").lower()
            else:
                self._update_status(key, f"IT: INVALID TOKENID VAL {value}")
                self.src101_dict[key] = None
                self.src101_dict[key + "_utf8"] = None
        else:
            self._update_status(key, f"IT: INVALID TOKENID VAL TYPE {value}")
            self.src101_dict[key] = None
            self.src101_dict[key + "_utf8"] = None

    def _process_uppercase_value(self, key, value):
        self.src101_dict[key] = value.upper()

    def _process_lowercase_value(self, key, value):
        self.src101_dict[key] = value.lower()

    @staticmethod
    def create_tick_hash(tick):
        """
        Create a SHA3-256 of the normalized tick value. This is the final NIST SHA3-256 implementation
        not to be confused with Keccak-256 which is the Ethereum implementation of SHA3-256.
        """
        return hashlib.sha3_256(tick.encode()).hexdigest()

    @property
    def is_valid(self):
        return len(self.validation_errors) == 0


class Src101Processor:
    STATUS_MESSAGES = {  # second value in tuple  = is_invalid
        "IH": ("INVALID HASH : {op}", False),
        "IND": ("INVALID DUA : {op}", False),
        "ID": ("INVALID DATA {deploy_hash}: {tokenid} ", False),
        "IDB": ("INVALID BTC DATA {deploy_hash}: {tokenid} ", False),
        "IR": ("INVALID RECIPIENT {deploy_hash}: {recipient} ", False),
        "ITT": ("INVALID TOKENID TYPE {deploy_hash}: {tokenid} ", False),
        "IRV": ("INVALID RECIPIENTVALUE {deploy_hash}: {recipient_nvalue} ", False),
        "IT": ("INVALID TOKENID : {deploy_hash}: {tokenid}", False),
        "ND": ("INVALID {op}: {deploy_hash} NO DEPLOY", True),
        "NM": ("INVALID {deploy_hash}: {tokenid} NO MINT", False),
        "NO": ("INVALID OWNER, {owner} NOR OWN {deploy_hash}: {tokenid}", False),
        "DM": ("INVALID MINT {deploy_hash} : {tokenid} MINT EXISTS", False),
        "UT": (" {deploy_hash} NOT START", False),
        "OT": (" OVER {deploy_hash} MINT END TIME", False),
        "OE": (" OVER {deploy_hash} {tokenid} EXPIRE TIME", False),
        "UO": ("UNSUPPORTED OP {op} ", True),
        "IDP": ("INVALID DEPLOY PARAMS", False),
    }

    def __init__(self, db, src101_dict, processed_src101_in_block):
        self.db = db
        self.src101_dict = src101_dict
        self.processed_src101_in_block = processed_src101_in_block
        self.is_valid = True

    def update_valid_src101_list(
        self,
        operation=None,
        expire_timestamp=None,
        src101_owner=None,
        src101_preowner=None,
        address_data=None,
        txt_data=None,
        prim=None,
    ):
        if operation == "TRANSFER":
            self.src101_dict["src101_preowner"] = src101_preowner
            self.src101_dict["src101_owner"] = src101_owner
            self.src101_dict["expire_timestamp"] = expire_timestamp
            self.src101_dict["prim"] = prim
        elif operation == "MINT":
            self.src101_dict["src101_preowner"] = src101_preowner
            self.src101_dict["src101_owner"] = src101_owner
            deltatime = self.src101_dict["dua"] * 31536000
            self.src101_dict["expire_timestamp"] = self.src101_dict["block_timestamp"] + deltatime
        elif operation == "DEPLOY":
            if not self.src101_dict.get("mintend") or self.src101_dict.get("mintend") == 0:
                self.src101_dict["mintend"] = 18446744073709551615
            self.src101_dict["expire_timestamp"] = expire_timestamp
        elif operation == "RENEW":
            self.src101_dict["src101_preowner"] = src101_preowner
            self.src101_dict["src101_owner"] = src101_owner
            deltatime = self.src101_dict["dua"] * 31536000
            self.src101_dict["prim"] = prim
            if expire_timestamp <= self.src101_dict["block_timestamp"]:
                self.src101_dict["expire_timestamp"] = self.src101_dict["block_timestamp"] + deltatime
            else:
                self.src101_dict["expire_timestamp"] = expire_timestamp + deltatime
        elif operation == "SETRECORD":
            self.src101_dict["src101_preowner"] = src101_preowner
            self.src101_dict["src101_owner"] = src101_owner
            self.src101_dict["expire_timestamp"] = expire_timestamp
        else:
            raise Exception(f"Invalid Operation '{operation}' on SRC20 Table Insert")

        self.src101_dict["valid"] = 1
        self.src101_dict["address_data"] = address_data
        self.src101_dict["address_btc"] = address_data["btc"] if address_data and "btc" in address_data.keys() else None
        self.src101_dict["address_eth"] = address_data["eth"] if address_data and "eth" in address_data.keys() else None
        self.src101_dict["txt_data"] = txt_data

    def set_status_and_log(self, status_code, **kwargs):
        message_template, is_invalid = self.STATUS_MESSAGES[status_code]
        message = message_template.format(**kwargs)
        status_message = f"{status_code}: {message}"
        self.src101_dict["status"] = status_message

        if is_invalid:
            logger.warning(message)
            self.is_valid = False
        else:
            logger.info(message)

    def handle_deploy(self):
        try:
            if (
                len(self.src101_dict["root"]) >= 32
                or len(self.src101_dict["name"]) >= 32
                or len(self.src101_dict["tick"]) >= 32
                or len(self.src101_dict["wll"]) >= 255
                or len(self.src101_dict["pri"]) >= 255
            ):
                self.set_status_and_log("IDP")
                return
            if not self.deploy_hash and not self.deploy_lim:
                self.update_valid_src101_list(operation=self.operation)
            else:
                raise ValueError("deploy_hash must be none when deploy")
        except Exception as e:
            logger.error(f"Error in deploy operations: {e}")
            raise

    def handle_mint(self):
        try:
            if not self.src101_dict["destination"] in self.rec:
                self.set_status_and_log(
                    "IR", deploy_hash=self.src101_dict["deploy_hash"], recipient=self.src101_dict["destination"]
                )
                return

            if not type(self.src101_dict["tokenid"]) == list:
                self.set_status_and_log(
                    "ITT", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"]
                )
                return

            needValue = 0
            for t in self.src101_dict["tokenid_utf8"]:
                if len(t) > len(self.price):
                    needValue += self.price[len(self.price) - 1]
                else:
                    needValue += self.price[len(t) - 1]
            if self.src101_dict["destination_nvalue"] < needValue:
                self.set_status_and_log(
                    "IRV", deploy_hash=self.src101_dict["deploy_hash"], recipient_nvalue=self.src101_dict["destination_nvalue"]
                )
                return

            # check time
            if self.src101_dict["block_timestamp"] < self.mintstart:
                self.set_status_and_log("UT", deploy_hash=self.src101_dict["deploy_hash"])
                return

            if self.src101_dict["block_timestamp"] >= self.mintend:
                self.set_status_and_log("OT", deploy_hash=self.src101_dict["deploy_hash"])
                return

            # check tokenid
            preowners = []
            for index in reversed(range(len(self.src101_dict["tokenid"]))):
                result = get_owner_expire_data_from_running(
                    self.db,
                    self.processed_src101_in_block,
                    self.src101_dict["deploy_hash"],
                    self.src101_dict["tokenid"][index],
                )
                # src101_preowner = result[0]
                src101_owner = result[1]
                expire_timestamp = result[2]
                address_data = json.loads(result[3]) if result[3] else result[3]
                txt_data = json.loads(result[4]) if result[4] else result[4]
                if expire_timestamp and expire_timestamp > self.src101_dict["block_timestamp"]:
                    del self.src101_dict["tokenid"][index]
                    del self.src101_dict["tokenid_utf8"][index]
                else:
                    preowners.append(src101_owner)
            preowners.reverse()
            if len(self.src101_dict["tokenid"]) == 0:
                self.set_status_and_log("DM", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return

            self.update_valid_src101_list(
                operation=self.operation,
                src101_owner=self.src101_dict["toaddress"],
                src101_preowner=preowners,
                address_data=address_data,
                txt_data=txt_data,
            )

        except Exception as e:
            logger.error(f"Error in minting operations: {e}")
            raise

    def handle_transfer(self):
        try:
            # check src101 has deployed
            if not self.src101_dict["deploy_hash"]:
                self.set_status_and_log("ND", op=self.src101_dict["op"], deploy_hash=self.src101_dict["deploy_hash"])
                return

            result = get_owner_expire_data_from_running(
                self.db, self.processed_src101_in_block, self.src101_dict["deploy_hash"], self.src101_dict["tokenid"]
            )
            src101_preowner = result[0]
            src101_owner = result[1]
            expire_timestamp = result[2]
            address_data = json.loads(result[3]) if result[3] else result[3]
            txt_data = json.loads(result[4]) if result[4] else result[4]
            prim = result[5]

            # check token has mint
            if not self.src101_dict["tokenid"] or not src101_owner or not expire_timestamp:
                self.set_status_and_log("NM", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return

            # check owner
            if self.src101_dict["creator"] != src101_owner:
                self.set_status_and_log(
                    "NO",
                    owner=self.src101_dict["creator"],
                    deploy_hash=self.src101_dict["deploy_hash"],
                    tokenid=self.src101_dict["tokenid"],
                )
                return
            # check empiration time
            if self.src101_dict["block_timestamp"] >= expire_timestamp:
                self.set_status_and_log("OE", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return

            self.update_valid_src101_list(
                operation=self.operation,
                src101_owner=self.src101_dict["toaddress"],
                src101_preowner=src101_owner,
                expire_timestamp=expire_timestamp,
                address_data=address_data,
                txt_data=txt_data,
                prim=prim,
            )

        except Exception as e:
            logger.error(f"Error in handle_transfer: {e}")
            raise

    def handle_renew(self):
        try:
            # check if it was deployed
            if not self.src101_dict["deploy_hash"]:
                self.set_status_and_log("ND", op=self.src101_dict["op"], deploy_hash=self.src101_dict["deploy_hash"])
                return
            result = get_owner_expire_data_from_running(
                self.db, self.processed_src101_in_block, self.src101_dict["deploy_hash"], self.src101_dict["tokenid"]
            )
            src101_preowner = result[0]
            src101_owner = result[1]
            expire_timestamp = result[2]
            address_data = json.loads(result[3]) if result[3] else result[3]
            txt_data = json.loads(result[4]) if result[4] else result[4]
            prim = result[5]
            # check token has mint
            if not self.src101_dict["tokenid"] or not src101_owner or not expire_timestamp:
                self.set_status_and_log("NM", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return
            # check owner
            if self.src101_dict["creator"] != src101_owner:
                self.set_status_and_log(
                    "NO",
                    owner=self.src101_dict["creator"],
                    deploy_hash=self.src101_dict["deploy_hash"],
                    tokenid=self.src101_dict["tokenid"],
                )
                return
            # check empiration time
            if self.src101_dict["block_timestamp"] >= expire_timestamp:
                self.set_status_and_log("OE", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return
            self.update_valid_src101_list(
                operation=self.operation,
                src101_preowner=src101_preowner,
                src101_owner=src101_owner,
                expire_timestamp=expire_timestamp,
                address_data=address_data,
                txt_data=txt_data,
                prim=prim,
            )

        except Exception as e:
            logger.error(f"Error in handle_renew: {e}")
            raise

    def handle_setrecord(self):
        try:
            # check if it was deployed
            if not self.src101_dict["deploy_hash"]:
                self.set_status_and_log("ND", op=self.src101_dict["op"], deploy_hash=self.src101_dict["deploy_hash"])
                return
            result = get_owner_expire_data_from_running(
                self.db, self.processed_src101_in_block, self.src101_dict["deploy_hash"], self.src101_dict["tokenid"]
            )
            src101_preowner = result[0]
            src101_owner = result[1]
            expire_timestamp = result[2]
            address_data = json.loads(result[3]) if result[3] else result[3]
            txt_data = json.loads(result[4]) if result[4] else result[4]
            # check token has mint
            if not self.src101_dict["tokenid"] or not src101_owner or not expire_timestamp:
                self.set_status_and_log("NM", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return
            # check owner
            if self.src101_dict["creator"] != src101_owner:
                self.set_status_and_log(
                    "NO",
                    owner=self.src101_dict["creator"],
                    deploy_hash=self.src101_dict["deploy_hash"],
                    tokenid=self.src101_dict["tokenid"],
                )
                return
            # check empiration time
            if self.src101_dict["block_timestamp"] >= expire_timestamp:
                self.set_status_and_log("OE", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return
            # check data
            if not "address_data" in self.src101_dict.keys():
                self.src101_dict["address_data"] = None
            else:
                valid = check_addres_type_data(self.src101_dict["address_data"])
                if not valid:
                    self.set_status_and_log(
                        "ID", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"]
                    )
                    return
            if not "txt_data" in self.src101_dict.keys():
                self.src101_dict["txt_data"] = None
            if not self.src101_dict["address_data"] and not self.src101_dict["txt_data"]:
                self.set_status_and_log("ID", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"])
                return
            address_data = self.src101_dict["address_data"] if self.src101_dict["address_data"] else address_data
            txt_data = self.src101_dict["txt_data"] if self.src101_dict["txt_data"] else txt_data
            self.update_valid_src101_list(
                operation=self.operation,
                src101_owner=src101_owner,
                src101_preowner=src101_preowner,
                expire_timestamp=expire_timestamp,
                address_data=address_data,
                txt_data=txt_data,
            )
            if self.src101_dict["prim"] == True and self.src101_dict["address_btc"] != self.src101_dict["creator"]:
                self.set_status_and_log(
                    "IDB", deploy_hash=self.src101_dict["deploy_hash"], tokenid=self.src101_dict["tokenid"]
                )

        except Exception as e:
            logger.error(f"Error in handle_setrecord: {e}")
            raise

    def validate_and_process_operation(self):
        self.operation = self.src101_dict.get("op")
        op_hash_validations = ["TRANSFEROWNERSHIP", "RENEW", "SETRECORD", "TRANSFER", "MINT"]
        if self.operation in op_hash_validations and not self.deploy_hash:
            self.set_status_and_log("IH", op=self.operation)
            return

        op_dua_validations = ["MINT", "RENEW"]
        if self.operation in op_dua_validations and not self.src101_dict.get("dua"):
            self.set_status_and_log("IND", op=self.operation)
            return

        # get src101 info here
        if self.deploy_hash:
            self.deploy_lim, self.pri, self.mintstart, self.mintend, self.rec = get_src101_deploy(
                self.db, self.deploy_hash, self.processed_src101_in_block
            )
            self.price = get_src101_price(self.db, self.deploy_hash, self.processed_src101_in_block)
        else:
            self.deploy_lim, self.pri, self.mintstart, self.mintend, self.rec, self.price = None, None, None, None, None, None
        if not self.deploy_hash and self.operation in op_hash_validations:
            self.set_status_and_log("ND", op=self.operation, deploy_hash=self.src101_dict["deploy_hash"])
            return
        if self.operation == "DEPLOY":
            self.handle_deploy()
        elif self.operation == "MINT":
            self.handle_mint()
        elif self.operation == "TRANSFER":
            self.handle_transfer()
        elif self.operation == "RENEW":
            self.handle_renew()
        elif self.operation == "SETRECORD":
            self.handle_setrecord()
        else:
            self.set_status_and_log("UO", op=self.operation, deploy_hash=self.src101_dict.get("deploy_hash", "undefined"))

    def process(self):
        validator = Src101Validator(self.src101_dict)
        self.src101_dict = validator.process_values()
        self.deploy_hash = self.src101_dict.get("hash")

        if not validator.is_valid:
            # self.processed_src101_in_block.append(self.src101_dict)
            logger.warning(f"Invalid {self.deploy_hash} SRC101: {self.src101_dict['status']}")
            self.is_valid = False
            return

        self.validate_and_process_operation()


def parse_src101(db, src101_dict, processed_src101_in_block):
    processor = Src101Processor(db, src101_dict, processed_src101_in_block)
    processor.process()

    return processor.is_valid, src101_dict


def check_addres_type_data(data):
    try:
        valid = False
        if "btc" in data.keys() and data["btc"]:
            valid = check_valid_bitcoin_address(data["btc"])
            if not valid:
                return valid
        if "eth" in data.keys() and data["eth"]:
            valid = check_valid_eth_address(data["eth"])
        return valid
    except:
        return False


def check_src101_inputs(input_string, tx_hash):
    try:
        try:
            if isinstance(input_string, bytes):
                input_string = input_string.decode("utf-8")
            elif isinstance(input_string, str):
                input_dict = json.loads(input_string, parse_float=D)
            elif isinstance(input_string, dict):
                input_dict = input_string
        except (json.JSONDecodeError, TypeError):
            raise
        if input_dict.get("p").lower() == "src-101":
            deploy_keys = {
                "p",
                "op",
                "name",
                "lim",
                "owner",
                "rec",
                "tick",
                "pri",
                "desc",
                "mintstart",
                "mintend",
                "wll",
                "root",
            }
            transfer_keys = {"p", "op", "hash", "toaddress", "tokenid"}
            mint_keys = {"p", "op", "hash", "toaddress", "tokenid", "dua", "prim"}
            setrecord_keys = {"p", "op", "hash", "tokenid", "type", "data", "prim"}
            renew_keys = {"p", "op", "hash", "tokenid", "dua"}
            input_keys = set(input_dict.keys())
            if input_dict.get("op").lower() == "deploy":
                if len(deploy_keys ^ input_keys) != 0:
                    logger.warning("deploy inputs mismatching")
                    return None
            elif input_dict.get("op").lower() == "transfer":
                if len(transfer_keys ^ input_keys) != 0:
                    logger.warning("transfer inputs mismatching")
                    return None
            elif input_dict.get("op").lower() == "mint":
                if len(mint_keys ^ input_keys) != 0:
                    logger.warning("mint inputs mismatching")
                    return None
            elif input_dict.get("op").lower() == "setrecord":
                if len(setrecord_keys ^ input_keys) != 0:
                    logger.warning("setrecord inputs mismatching")
                    return None
            elif input_dict.get("op").lower() == "renew":
                if len(renew_keys ^ input_keys) != 0:
                    logger.warning("renew inputs mismatching")
                    return None
            else:
                return None
            return input_dict
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error updating SRC101 owners: {e}")
        return None


def update_src101_owners(db, block_index, src101_processed_in_block):
    owner_updates = []
    for src101_dict in src101_processed_in_block:
        if src101_dict.get("valid") == 1 and src101_dict.get("tokenid") and src101_dict.get("deploy_hash"):
            try:
                owner_dict = next(
                    (
                        item
                        for item in owner_updates
                        if item["tokenid"] == src101_dict["tokenid"] and item["deploy_hash"] == src101_dict["deploy_hash"]
                    ),
                    None,
                )
                if src101_dict["op"] == "MINT":
                    if owner_dict is None:
                        address_data = (
                            {"btc": src101_dict["src101_owner"]} if src101_dict["prim"] else src101_dict["address_data"]
                        )
                        for index in range(len(src101_dict["tokenid"])):
                            owner_dict = {
                                "p": src101_dict["p"],
                                "deploy_hash": src101_dict["deploy_hash"],
                                "tokenid": src101_dict["tokenid"][index],
                                "tokenid_utf8": src101_dict["tokenid_utf8"][index],
                                "owner": src101_dict["src101_owner"],
                                "preowner": src101_dict["src101_preowner"][index],
                                "expire_timestamp": src101_dict["expire_timestamp"],
                                "txt_data": src101_dict["txt_data"],
                                "address_data": address_data,
                                "address_btc": src101_dict["src101_owner"],
                                "address_eth": None,
                                "prim": src101_dict["prim"],
                            }
                            owner_updates.append(owner_dict)
                    else:
                        raise ValueError("cannot mint the same tokenid")
                if src101_dict["op"] == "TRANSFER":
                    if owner_dict is None:
                        owner_dict = {
                            "p": src101_dict["p"],
                            "deploy_hash": src101_dict["deploy_hash"],
                            "tokenid": src101_dict["tokenid"],
                            "tokenid_utf8": src101_dict["tokenid_utf8"],
                            "owner": src101_dict["src101_owner"],
                            "preowner": src101_dict["src101_preowner"],
                            "expire_timestamp": src101_dict["expire_timestamp"],
                            "txt_data": None,
                            "address_data": None,
                            "address_btc": None,
                            "address_eth": None,
                            "prim": False,
                        }
                        owner_updates.append(owner_dict)
                    else:
                        owner_dict["owner"] = (src101_dict["src101_owner"],)
                        owner_dict["preowner"] = src101_dict["src101_preowner"]
                if src101_dict["op"] == "RENEW":
                    if owner_dict is None:
                        owner_dict = {
                            "p": src101_dict["p"],
                            "deploy_hash": src101_dict["deploy_hash"],
                            "tokenid": src101_dict["tokenid"],
                            "tokenid_utf8": src101_dict["tokenid_utf8"],
                            "owner": src101_dict["src101_owner"],
                            "expire_timestamp": src101_dict["expire_timestamp"],
                            "preowner": src101_dict["src101_preowner"],
                            "txt_data": src101_dict["txt_data"],
                            "address_data": src101_dict["address_data"],
                            "address_btc": src101_dict["address_btc"],
                            "address_eth": src101_dict["address_eth"],
                            "prim": src101_dict["prim"],
                        }
                        owner_updates.append(owner_dict)
                    else:
                        owner_dict["expire_timestamp"] = (src101_dict["expire_timestamp"],)
                if src101_dict["op"] == "SETRECORD":
                    if owner_dict is None:
                        owner_dict = {
                            "p": src101_dict["p"],
                            "deploy_hash": src101_dict["deploy_hash"],
                            "tokenid": src101_dict["tokenid"],
                            "tokenid_utf8": src101_dict["tokenid_utf8"],
                            "owner": src101_dict["src101_owner"],
                            "expire_timestamp": src101_dict["expire_timestamp"],
                            "preowner": src101_dict["src101_preowner"],
                            "txt_data": src101_dict["txt_data"],
                            "address_data": src101_dict["address_data"],
                            "address_btc": src101_dict["address_btc"],
                            "address_eth": src101_dict["address_eth"],
                            "prim": src101_dict["prim"],
                        }
                        owner_updates.append(owner_dict)
                    else:
                        owner_dict["txt_data"] = src101_dict["txt_data"]
                        owner_dict["address_data"] = src101_dict["address_data"]
                        owner_dict["address_btc"] = src101_dict["address_btc"]
                        owner_dict["address_eth"] = src101_dict["address_eth"]

            except Exception as e:
                logger.error(f"Error updating SRC101 owners: {e}")
                raise e
    if owner_updates:
        update_owner_table(db, owner_updates, block_index)
    return owner_updates


def update_owner_table(db, owner_updates, block_index):
    cursor = db.cursor()
    for owner_dict in owner_updates:
        try:
            querystr = (
                f"SELECT COALESCE(MAX({SRC101_OWNERS_TABLE}.index), 0) FROM {SRC101_OWNERS_TABLE} WHERE deploy_hash = %s"
            )
            cursor.execute(querystr, (owner_dict["deploy_hash"],))
            max_index = cursor.fetchone()[0]
            id_field = owner_dict["p"] + "_" + owner_dict["deploy_hash"] + "_" + owner_dict["tokenid"]
            imgurl = SRC101_IMG_URL_PREFIX + owner_dict["tokenid_utf8"] + ".png"
            if owner_dict["prim"] and owner_dict["prim"] == True:
                cursor.execute(
                    f"""
                    UPDATE {SRC101_OWNERS_TABLE}
                    SET prim = FALSE
                    WHERE address_btc = %s AND prim = TRUE;
                    """,
                    (owner_dict["address_btc"],),
                )
            cursor.execute(
                f"""
                INSERT INTO {SRC101_OWNERS_TABLE}
                ({SRC101_OWNERS_TABLE}.index, id, last_update, p, deploy_hash, tokenid, tokenid_utf8, img, preowner, owner, address_data, txt_data, expire_timestamp, address_btc, address_eth, prim)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    last_update = VALUES(last_update),
                    preowner = VALUES(preowner),
                    owner = VALUES(owner),
                    address_data= VALUES(address_data),
                    txt_data = VALUES(txt_data),
                    address_btc = VALUES(address_btc),
                    address_eth = VALUES(address_eth),
                    prim = VALUES(prim),
                    expire_timestamp = VALUES(expire_timestamp)
            """,
                (
                    max_index + 1,
                    id_field,
                    block_index,
                    owner_dict["p"],
                    owner_dict["deploy_hash"],
                    owner_dict["tokenid"],
                    owner_dict["tokenid_utf8"],
                    imgurl,
                    owner_dict["preowner"],
                    owner_dict["owner"],
                    json.dumps(owner_dict["address_data"]) if owner_dict["address_data"] else None,
                    json.dumps(owner_dict["txt_data"]) if owner_dict["txt_data"] else None,
                    owner_dict["expire_timestamp"],
                    owner_dict["address_btc"],
                    owner_dict["address_eth"],
                    owner_dict["prim"],
                ),
            )

        except Exception as e:
            logger.error("Error updating owners table:", e)
            raise e

    cursor.close()
    return


# def get_owner_from_owners(db, deploy_hash, tokenid):
#     cursor = db.cursor()
#     id_field = "src-101" + "_" + deploy_hash + "_" + tokenid
#     cursor.execute(f"SELECT owner FROM {SRC101_OWNERS_TABLE} WHERE id = %s", (id_field,))
#     result = cursor.fetchone()
#     return result

# def get_owner_from_owners(db, id_field):
#     cursor = db.cursor()
#     cursor.execute(f"SELECT owner FROM {SRC101_OWNERS_TABLE} WHERE id = %s", (id_field,))
#     result = cursor.fetchone()
#     return result


def get_owner_expire_data_from_running(db, processed_src101_in_block, deploy_hash, tokenid):
    preowner = None
    owner = None
    expire_timestamp = None
    address_data = None
    txt_data = None
    prim = None
    for d in processed_src101_in_block:
        if (
            d
            and d["tokenid"]
            and type(d["tokenid"]) == list
            and tokenid in d["tokenid"]
            and d["hash"] == deploy_hash
            and d["valid"] == 1
        ):
            preowner = d["src101_preowner"]
            owner = d["src101_owner"]
            expire_timestamp = d["expire_timestamp"]
            address_data = json.dumps(d["address_data"])
            txt_data = json.dumps(d["txt_data"])
            prim = d["prim"]
        elif (
            d
            and d["tokenid"]
            and type(d["tokenid"]) == str
            and tokenid == d["tokenid"]
            and d["hash"] == deploy_hash
            and d["valid"] == 1
        ):
            preowner = d["src101_preowner"]
            owner = d["src101_owner"]
            expire_timestamp = d["expire_timestamp"]
            address_data = json.dumps(d["address_data"])
            txt_data = json.dumps(d["txt_data"])
            prim = d["prim"]
    if owner and expire_timestamp:
        return [preowner, owner, expire_timestamp, address_data, txt_data, prim]
    return get_owner_expire_data_from_db(db, deploy_hash, tokenid)


def get_owner_expire_data_from_db(db, deploy_hash, tokenid):
    cursor = db.cursor()
    id_field = "src-101" + "_" + deploy_hash + "_" + tokenid
    cursor.execute(
        f"SELECT preowner, owner,expire_timestamp,address_data,txt_data,prim FROM {SRC101_OWNERS_TABLE} WHERE id = %s",
        (id_field,),
    )
    result = cursor.fetchone()
    if not result:
        result = [None, None, None, None, None, None]
    return result
