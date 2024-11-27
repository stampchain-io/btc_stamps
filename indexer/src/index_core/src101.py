import base64
import decimal
import hashlib
import json
import logging
import math
import re
from datetime import datetime
from typing import Optional, TypedDict, Union

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from eth_account import Account
from eth_account.messages import encode_defunct

import index_core.log as log
from config import BTC_SRC101_IMG_OPTIONAL_BLOCK, SRC101_OWNERS_TABLE
from index_core.database import get_src101_deploy, get_src101_price
from index_core.util import (
    check_contains_special,
    check_valid_base64_string,
    check_valid_bitcoin_address,
    check_valid_eth_address,
    check_valid_tx_hash,
    escape_non_ascii_characters,
    is_valid_pubkey_hex,
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
    idua: Optional[Union[str, D]]
    lim: Optional[Union[str, D]]
    mintstart: Optional[Union[str, D]]
    mintend: Optional[Union[str, D]]
    pri: Optional[Union[str, D]]
    status: Optional[str]
    tick_hash: Optional[str]
    tokenid_utf8: Optional[str]
    tokenid_origin: Optional[str]


class Src101Validator:
    def __init__(self, src101_dict):
        self.src101_dict = src101_dict
        self.validation_errors = []

    def process_values(self):
        try:
            num_pattern = re.compile(r"^[0-9]*(\.[0-9]*)?$")
            # dec_pattern = re.compile(r"^[0-9]+$")

            for key, value in list(self.src101_dict.items()):
                try:
                    if value == "":
                        self.src101_dict[key] = None
                    elif key in ["block_time"]:
                        self._process_block_time_value(key, value)
                    elif key in ["imglp", "imgf", "sig"]:
                        self._process_str_value(key, value)
                    elif key in ["img"]:
                        self._process_strArray_value(key, value)
                    elif key in ["tick"]:
                        self._process_tick_value(key, value)
                    elif key in ["root", "name"]:
                        self._process_root_value(key, value)
                    elif key in ["tokenid"]:
                        self._process_tokenid_value(key, value)
                    elif key in ["hash"]:
                        self._process_hash_value(key, value)
                    elif key in ["pri"]:
                        self._process_pri_value(key, value)
                    elif key in ["wla"]:
                        self._process_wla_value(key, value)
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
                    elif key in ["lim", "dua", "idua", "mintstart", "mintend", "coef"]:
                        self._apply_regex_validation(key, value, num_pattern)
                except Exception as e:
                    self.src101_dict[key] = None
                    self._update_status(f"{key}:{value}", e)

            if "type" in self.src101_dict.keys() and "data" in self.src101_dict.keys():
                self.src101_dict[self.src101_dict["type"] + "_data"] = self.src101_dict["data"]
            return self.src101_dict
        except Exception as e:
            self._update_status("process_values", e)
            return self.src101_dict

    def _apply_regex_validation(self, key, value, num_pattern):
        if key in ["lim", "dua", "idua", "mintstart", "mintend", "coef"]:
            try:
                if num_pattern.match(str(value)) and int(value) >= 0:
                    self.src101_dict[key] = int(value)
                else:
                    raise
            except:
                self._update_status(key, f"NN: INVALID NUM for {key}")
                self.src101_dict[key] = None

    def _update_status(self, key, message):
        error_message = f"{key}: {message}"
        self.validation_errors.append(error_message)

        if "status" in self.src101_dict:
            self.src101_dict["status"] += f", {error_message}"
        else:
            self.src101_dict["status"] = error_message

    def _process_str_value(self, key, value):
        if type(value) == str:
            self.src101_dict[key] = value
        else:
            self.src101_dict[key] = None
            self._update_status(key, f"IIM: INVALID {key} VAL {value}")

    def _process_block_time_value(self, key, value):
        if key == "block_time" and type(value) == datetime:
            self.src101_dict["block_timestamp"] = int(value.timestamp())
        else:
            self.src101_dict[key] = 0
            self._update_status(key, f"IBT: INVALID {key} BLOCK TIMESTAMP {value}")

    def _process_strArray_value(self, key, value):
        if type(value) == list:
            are_all_strings = all(isinstance(item, str) for item in value)
            if are_all_strings:
                self.src101_dict[key] = value
                return
        self.src101_dict[key] = None
        self._update_status(key, f"IIM: INVALID {key} VAL {value}")

    def _process_tick_value(self, key, value):
        self.src101_dict[key] = value.lower()
        self.src101_dict[key] = escape_non_ascii_characters(self.src101_dict[key])
        self.src101_dict[key + "_hash"] = self.create_tick_hash(value.lower())

    def _process_pri_value(self, key, value):
        try:
            # check valid
            seen_keys = set()
            valid = True
            if isinstance(value, dict):
                for k, v in value.items():
                    try:
                        int_key = int(k)
                    except:
                        valid = False
                    if k in seen_keys:
                        valid = False
                    else:
                        seen_keys.add(k)
                    if not isinstance(v, int):
                        valid = False
            else:
                valid = False
            if valid:
                self.src101_dict[key] = value
            else:
                self.src101_dict[key] = None
                self._update_status(key, f"IPC: INVALID PRI VAL {value}")
        except:
            self.src101_dict[key] = None
            self._update_status(key, f"IPC: INVALID PRI VAL {value}")

    def _process_bool_value(self, key, value):
        if value == "true":
            self.src101_dict[key] = True
        elif value == "false":
            self.src101_dict[key] = False
        else:
            self._update_status(key, f"IP: INVALID PRIM VAL {value}")
            self.src101_dict[key] = None

    def _process_wla_value(self, key, value):
        valid = is_valid_pubkey_hex(value)
        if valid:
            self.src101_dict[key] = value
        else:
            self._update_status(key, f"IWLA: INVALID WLA VAL {value}")
            self.src101_dict[key] = None

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
                valid = valid and check_valid_bitcoin_address(a)
            if valid and type(value) == list:
                self.src101_dict[key] = list(set(value))
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

    def _process_root_value(self, key, value):
        valid = not check_contains_special(value)
        if valid:
            self.src101_dict[key] = str(value)
        else:
            self._update_status(key, f"IA: INVALID {key} VAL {value}")
            self.src101_dict[key] = None

    def _process_tokenid_value(self, key, value):
        if type(value) == list:
            self.src101_dict[key + "_origin"] = value
            valid = True
            utf8valuelist = []
            normvaluelist = []
            for v in value:
                valid = valid and check_valid_base64_string(v)
                try:
                    utf8value = base64.urlsafe_b64decode(v).decode("utf-8").lower()
                    normvalue = base64.b64encode(utf8value.encode("utf-8")).decode("utf-8")
                    if len(v) > 128:
                        valid = False
                    if utf8value in utf8valuelist:
                        valid = False
                    elif check_contains_special(utf8value):
                        valid = False
                    else:
                        normvaluelist.append(normvalue)
                        utf8valuelist.append(utf8value)
                except Exception as e:
                    valid = False
            if valid:
                self.src101_dict[key] = normvaluelist
                self.src101_dict[key + "_utf8"] = utf8valuelist
            else:
                self._update_status(key, f"IT: INVALID TOKENID VAL {value}")
                self.src101_dict[key] = None
                self.src101_dict[key + "_utf8"] = None
        elif type(value) == str:
            self.src101_dict[key + "_origin"] = value
            valid = check_valid_base64_string(value)
            if len(value) > 128:
                valid = False
            try:
                utf8value = base64.b64decode(value).decode("utf8").lower()
                if check_contains_special(utf8value):
                    valid = False
            except Exception as e:
                valid = False
            if valid:
                self.src101_dict[key] = value
                self.src101_dict[key + "_utf8"] = utf8value
            else:
                self._update_status(key, f"IT: INVALID TOKENID VAL {value}")
                self.src101_dict[key] = None
                self.src101_dict[key + "_utf8"] = None
        else:
            self._update_status(key, f"IT: INVALID TOKENID VAL TYPE {value}")
            self.src101_dict[key + "_origin"] = None
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
        "ITC": ("INVALID COEF {deploy_hash}: {coef} ", False),
        "ITID": ("INVALID IDUA {deploy_hash}: {idua} ", False),
        "ITD": ("INVALID DUA {deploy_hash}: {dua} ", False),
        "ITI": ("INVALID IMG TYPE {deploy_hash}: {img} ", False),
        "IRS": ("INVALID SIG {deploy_hash}: {sig} ", False),
        "IRV": ("INVALID RECIPIENTVALUE {deploy_hash}: {recipient_nvalue} ", False),
        "IRL": ("INVALID LENGTH {deploy_hash}: {tokenid} ", False),
        "IRM": ("INVALID IMG {deploy_hash}: {img} ", False),
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
        "UE": ("UNEXPECTED ERROR : {error}", False),
    }

    def __init__(self, db, src101_dict, processed_src101_in_block, block_index):
        self.db = db
        self.src101_dict = src101_dict
        self.processed_src101_in_block = processed_src101_in_block
        self.block_index = block_index
        self.is_valid = True

    def update_valid_src101_list(
        self,
        operation=None,
        expire_timestamp=None,
        src101_owner=None,
        src101_preowner=None,
        address_btc=None,
        address_eth=None,
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
        self.src101_dict["address_btc"] = address_btc
        self.src101_dict["address_eth"] = address_eth
        self.src101_dict["txt_data"] = txt_data

    def set_status_and_log(self, status_code, **kwargs):
        message_template, is_invalid = self.STATUS_MESSAGES[status_code]
        if kwargs is None:
            kwargs = {}
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
                len(self.src101_dict.get("root", "*" * 33)) >= 32
                or len(self.src101_dict.get("name", "*" * 33)) >= 32
                or len(self.src101_dict.get("tick", "*" * 33)) >= 32
                or len(self.src101_dict.get("pri", "*" * 256)) >= 255
                or len(self.src101_dict.get("imglp", "*" * 256)) >= 255
                or len(self.src101_dict.get("imgf", "*" * 33)) >= 32
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
            if not self.src101_dict.get("destination") in self.rec:
                self.set_status_and_log(
                    "IR", deploy_hash=self.src101_dict.get("deploy_hash"), recipient=self.src101_dict.get("destination")
                )
                return

            if (
                not self.src101_dict.get("tokenid")
                or not type(self.src101_dict.get("tokenid")) == list
                or not self.src101_dict.get("tokenid_utf8")
                or not type(self.src101_dict.get("tokenid_utf8")) == list
            ):
                self.set_status_and_log(
                    "ITT", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return

            if (
                not type(self.src101_dict.get("coef")) == int
                or self.src101_dict.get("coef", 1001) > 1000
                or self.src101_dict.get("coef", -1) < 0
            ):
                self.set_status_and_log(
                    "ITC", deploy_hash=self.src101_dict.get("deploy_hash"), coef=self.src101_dict.get("coef")
                )
                return

            if self.block_index < BTC_SRC101_IMG_OPTIONAL_BLOCK:
                if not self.src101_dict.get("img") or not type(self.src101_dict.get("img")) == list:
                    self.set_status_and_log(
                        "ITI", deploy_hash=self.src101_dict.get("deploy_hash"), img=self.src101_dict.get("img")
                    )
                    return
            else:
                if self.src101_dict.get("img") is None:
                    self.src101_dict["img"] = [None] * len(self.src101_dict.get("tokenid"))
                elif not type(self.src101_dict.get("img")) == list:
                    self.set_status_and_log(
                        "ITI", deploy_hash=self.src101_dict.get("deploy_hash"), img=self.src101_dict.get("img")
                    )
                    return
            if not self.src101_dict.get("dua") or type(self.src101_dict.get("dua")) != int or self.src101_dict.get("dua") <= 0:
                self.set_status_and_log(
                    "ITD", deploy_hash=self.src101_dict.get("deploy_hash"), dua=self.src101_dict.get("dua")
                )
                return
            if not self.idua or self.idua <= 0:
                self.set_status_and_log("ITID", deploy_hash=self.src101_dict.get("deploy_hash"), idua=self.idua)
                return
            self.src101_dict["dua"] = math.ceil(self.src101_dict.get("dua") / self.idua) * self.idua
            self.src101_dict["round"] = self.src101_dict.get("dua") / self.idua
            needValue = 0
            price = get_src101_price(self.db, self.src101_dict.get("deploy_hash"), self.processed_src101_in_block)
            for t in self.src101_dict.get("tokenid_utf8"):
                if t and len(t) in price.keys():
                    _p = price[len(t)]
                elif 0 in price.keys():
                    _p = price[0]
                else:
                    _p = -1
                if _p != -1:
                    needValue += _p * self.src101_dict.get("round")
                else:
                    self.set_status_and_log(
                        "IRL", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                    )
                    return

            _coef = 1000
            if self.src101_dict.get("sig") and self.src101_dict.get("sig") != "":
                try:
                    data = {
                        "hash": self.src101_dict["deploy_hash"],
                        "coef": str(self.src101_dict["coef"]),
                        "address": self.src101_dict["creator"],
                        "tokenid": self.src101_dict["tokenid_origin"],
                        "dua": str(self.src101_dict["dua"]),
                    }

                    compressed_public_key_bytes = bytes.fromhex(self.wla)
                    public_key_from_compressed = ec.EllipticCurvePublicKey.from_encoded_point(
                        ec.SECP256K1(), compressed_public_key_bytes
                    )
                    public_key_from_compressed.verify(
                        bytes.fromhex(self.src101_dict["sig"]), json.dumps(data).encode(), ec.ECDSA(hashes.SHA256())
                    )
                    _coef = self.src101_dict["coef"]
                except Exception as e:
                    try:
                        data = {
                            "hash": self.src101_dict["deploy_hash"],
                            "coef": str(self.src101_dict["coef"]),
                            "address": self.src101_dict["creator"],
                            "dua": str(self.src101_dict["dua"]),
                        }
                        compressed_public_key_bytes = bytes.fromhex(self.wla)
                        public_key_from_compressed = ec.EllipticCurvePublicKey.from_encoded_point(
                            ec.SECP256K1(), compressed_public_key_bytes
                        )
                        public_key_from_compressed.verify(
                            bytes.fromhex(self.src101_dict["sig"]), json.dumps(data).encode(), ec.ECDSA(hashes.SHA256())
                        )
                        _coef = self.src101_dict["coef"]
                    except Exception as inner_e:
                        self.set_status_and_log(
                            "IRS", deploy_hash=self.src101_dict["deploy_hash"], sig=self.src101_dict["sig"]
                        )
                        return

            if self.src101_dict.get("destination_nvalue", 0) < needValue * _coef / 1000:
                self.set_status_and_log(
                    "IRV",
                    deploy_hash=self.src101_dict.get("deploy_hash"),
                    recipient_nvalue=self.src101_dict.get("destination_nvalue"),
                )
                return
            if self.imglp and self.imgf:
                if self.block_index < BTC_SRC101_IMG_OPTIONAL_BLOCK:
                    # check img
                    for index in range(len(self.src101_dict.get("tokenid_utf8"))):
                        _img = self.imglp + self.src101_dict.get("tokenid_utf8")[index] + "." + self.imgf
                        if index >= len(self.src101_dict.get("img")) or _img != self.src101_dict.get("img")[index]:
                            self.set_status_and_log(
                                "IRM", deploy_hash=self.src101_dict.get("deploy_hash"), img=self.src101_dict.get("img")
                            )
                            return
                else:
                    # set img
                    self.src101_dict["img"] = [None] * len(self.src101_dict.get("tokenid"))
                    for index in range(len(self.src101_dict.get("tokenid_utf8"))):
                        self.src101_dict["img"][index] = (
                            self.imglp + self.src101_dict.get("tokenid_utf8")[index] + "." + self.imgf
                        )
            # check time
            if self.src101_dict.get("block_timestamp", self.mintstart - 1) < self.mintstart:
                self.set_status_and_log("UT", deploy_hash=self.src101_dict.get("deploy_hash"))
                return

            if self.src101_dict.get("block_timestamp", self.mintend + 1) >= self.mintend:
                self.set_status_and_log("OT", deploy_hash=self.src101_dict.get("deploy_hash"))
                return

            # check tokenid
            preowners = []
            for index in reversed(range(len(self.src101_dict.get("tokenid_utf8")))):
                result = get_owner_expire_data_from_running(
                    self.db,
                    self.processed_src101_in_block,
                    self.src101_dict.get("deploy_hash"),
                    self.src101_dict.get("tokenid_utf8")[index],
                )
                # src101_preowner = result[0]
                src101_owner = result[1]
                expire_timestamp = result[2]
                address_btc = result[3]
                address_eth = result[4]
                txt_data = json.loads(result[5]) if result[5] else result[5]
                if expire_timestamp and expire_timestamp > self.src101_dict.get("block_timestamp"):
                    del self.src101_dict.get("tokenid")[index]
                    del self.src101_dict.get("tokenid_utf8")[index]
                else:
                    preowners.append(src101_owner)
            preowners.reverse()
            if len(self.src101_dict.get("tokenid")) == 0:
                self.set_status_and_log(
                    "DM", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return

            self.update_valid_src101_list(
                operation=self.operation,
                src101_owner=self.src101_dict.get("toaddress"),
                src101_preowner=preowners,
                address_btc=address_btc,
                address_eth=address_eth,
                txt_data=txt_data,
            )

        except Exception as e:
            logger.error(f"Error in minting operations: {e}")
            raise

    def handle_transfer(self):
        try:
            # check src101 has deployed
            if not self.src101_dict.get("deploy_hash"):
                self.set_status_and_log("ND", op=self.src101_dict.get("op"), deploy_hash=self.src101_dict.get("deploy_hash"))
                return

            result = get_owner_expire_data_from_running(
                self.db,
                self.processed_src101_in_block,
                self.src101_dict.get("deploy_hash"),
                self.src101_dict.get("tokenid_utf8"),
            )
            src101_preowner = result[0]
            src101_owner = result[1]
            expire_timestamp = result[2]
            address_btc = result[3]
            address_eth = result[4]
            txt_data = json.loads(result[5]) if result[5] else result[5]
            prim = result[6]

            # check token has mint
            if not self.src101_dict.get("tokenid") or not src101_owner or not expire_timestamp:
                self.set_status_and_log(
                    "NM", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return

            # check owner
            if self.src101_dict.get("creator") != src101_owner:
                self.set_status_and_log(
                    "NO",
                    owner=self.src101_dict.get("creator"),
                    deploy_hash=self.src101_dict.get("deploy_hash"),
                    tokenid=self.src101_dict.get("tokenid"),
                )
                return
            # check empiration time
            if self.src101_dict.get("block_timestamp") >= expire_timestamp:
                self.set_status_and_log(
                    "OE", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return

            self.update_valid_src101_list(
                operation=self.operation,
                src101_owner=self.src101_dict.get("toaddress"),
                src101_preowner=src101_owner,
                expire_timestamp=expire_timestamp,
                address_btc=address_btc,
                address_eth=address_eth,
                txt_data=txt_data,
                prim=prim,
            )

        except Exception as e:
            logger.error(f"Error in handle_transfer: {e}")
            raise

    def handle_renew(self):
        try:
            # check if it was deployed
            if not self.src101_dict.get("deploy_hash"):
                self.set_status_and_log("ND", op=self.src101_dict.get("op"), deploy_hash=self.src101_dict.get("deploy_hash"))
                return
            result = get_owner_expire_data_from_running(
                self.db,
                self.processed_src101_in_block,
                self.src101_dict.get("deploy_hash"),
                self.src101_dict.get("tokenid_utf8"),
            )
            src101_preowner = result[0]
            src101_owner = result[1]
            expire_timestamp = result[2]
            address_btc = result[3]
            address_eth = result[4]
            txt_data = json.loads(result[5]) if result[5] else result[5]
            prim = result[6]
            # check token has mint
            if (
                not self.src101_dict.get("tokenid")
                or not self.src101_dict.get("tokenid_utf8")
                or not src101_owner
                or not expire_timestamp
            ):
                self.set_status_and_log(
                    "NM", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return
            # check owner
            if self.src101_dict.get("creator") != src101_owner:
                self.set_status_and_log(
                    "NO",
                    owner=self.src101_dict.get("creator"),
                    deploy_hash=self.src101_dict.get("deploy_hash"),
                    tokenid=self.src101_dict.get("tokenid"),
                )
                return
            # check empiration time
            if self.src101_dict.get("block_timestamp") >= expire_timestamp:
                self.set_status_and_log(
                    "OE", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return

            if not self.src101_dict.get("dua") or type(self.src101_dict.get("dua")) != int or self.src101_dict.get("dua") <= 0:
                self.set_status_and_log(
                    "ITD", deploy_hash=self.src101_dict.get("deploy_hash"), dua=self.src101_dict.get("dua")
                )
                return
            if not self.idua or self.idua <= 0:
                self.set_status_and_log("ITID", deploy_hash=self.src101_dict.get("deploy_hash"), idua=self.idua)
                return

            self.src101_dict["dua"] = math.ceil(self.src101_dict.get("dua") / self.idua) * self.idua
            self.src101_dict["round"] = self.src101_dict.get("dua") / self.idua

            price = get_src101_price(self.db, self.src101_dict.get("deploy_hash"), self.processed_src101_in_block)
            if len(self.src101_dict.get("tokenid_utf8")) in price.keys():
                needValue = price[len(self.src101_dict.get("tokenid_utf8"))]
            elif 0 in price.keys():
                needValue = price[0]
            else:
                needValue = -1
            if needValue == -1:
                self.set_status_and_log(
                    "IRL", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return
            else:
                needValue = needValue * self.src101_dict.get("round")
            if self.src101_dict.get("destination_nvalue", needValue - 1) < needValue:
                self.set_status_and_log(
                    "IRV",
                    deploy_hash=self.src101_dict.get("deploy_hash"),
                    recipient_nvalue=self.src101_dict.get("destination_nvalue", needValue - 1),
                )
                return

            self.update_valid_src101_list(
                operation=self.operation,
                src101_preowner=src101_preowner,
                src101_owner=src101_owner,
                expire_timestamp=expire_timestamp,
                address_btc=address_btc,
                address_eth=address_eth,
                txt_data=txt_data,
                prim=prim,
            )

        except Exception as e:
            logger.error(f"Error in handle_renew: {e}")
            raise

    def handle_setrecord(self):
        try:
            # check if it was deployed
            if not self.src101_dict.get("deploy_hash"):
                self.set_status_and_log("ND", op=self.src101_dict.get("op"), deploy_hash=self.src101_dict.get("deploy_hash"))
                return
            result = get_owner_expire_data_from_running(
                self.db,
                self.processed_src101_in_block,
                self.src101_dict.get("deploy_hash"),
                self.src101_dict.get("tokenid_utf8"),
            )
            src101_preowner = result[0]
            src101_owner = result[1]
            expire_timestamp = result[2]
            address_btc = result[3]
            address_eth = result[4]
            txt_data = json.loads(result[5]) if result[5] else result[5]
            # check token has mint
            if not self.src101_dict.get("tokenid") or not src101_owner or not expire_timestamp:
                self.set_status_and_log(
                    "NM", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return
            # check owner
            if self.src101_dict.get("creator") and self.src101_dict.get("creator") != src101_owner:
                self.set_status_and_log(
                    "NO",
                    owner=self.src101_dict.get("creator"),
                    deploy_hash=self.src101_dict.get("deploy_hash"),
                    tokenid=self.src101_dict.get("tokenid"),
                )
                return
            # check empiration time
            if self.src101_dict.get("block_timestamp") >= expire_timestamp:
                self.set_status_and_log(
                    "OE", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return
            # check data
            if not "address_data" in self.src101_dict.keys():
                self.src101_dict["address_data"] = None
            else:
                (valid, self.src101_dict["address_data"]) = check_and_convert_addres_type_data(
                    self.src101_dict["address_data"], bytes(reversed(self.src101_dict.get("prev_tx_hash"))).hex()
                )
                if not valid:
                    self.set_status_and_log(
                        "ID", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                    )
                    return
                address_btc = (
                    self.src101_dict.get("address_data", {}).get("btc", "")
                    if "btc" in self.src101_dict.get("address_data", {}).keys()
                    else address_btc
                )
                address_eth = (
                    self.src101_dict.get("address_data", {}).get("eth", "")
                    if "eth" in self.src101_dict.get("address_data", {}).keys()
                    else address_eth
                )
            if (
                self.src101_dict.get("prim") == True
                and self.src101_dict.get("address_data")
                and self.src101_dict.get("address_data").get("btc") != self.src101_dict.get("creator")
            ):
                self.set_status_and_log(
                    "IDB", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return
            if not "txt_data" in self.src101_dict.keys():
                self.src101_dict["txt_data"] = None
            if not self.src101_dict.get("address_data") and not self.src101_dict.get("txt_data"):
                self.set_status_and_log(
                    "ID", deploy_hash=self.src101_dict.get("deploy_hash"), tokenid=self.src101_dict.get("tokenid")
                )
                return
            txt_data = self.src101_dict.get("txt_data") if self.src101_dict.get("txt_data") else txt_data
            self.update_valid_src101_list(
                operation=self.operation,
                src101_owner=src101_owner,
                src101_preowner=src101_preowner,
                expire_timestamp=expire_timestamp,
                address_btc=address_btc,
                address_eth=address_eth,
                txt_data=txt_data,
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
            self.deploy_lim, self.pri, self.mintstart, self.mintend, self.rec, self.wla, self.imglp, self.imgf, self.idua = (
                get_src101_deploy(self.db, self.deploy_hash, self.processed_src101_in_block)
            )
        else:
            self.deploy_lim, self.pri, self.mintstart, self.mintend, self.rec, self.wla, self.imglp, self.imgf, self.idua = (
                0,
                None,
                0,
                0,
                None,
                None,
                None,
                None,
                0,
            )
        if not self.deploy_hash and self.operation in op_hash_validations:
            self.set_status_and_log("ND", op=self.operation, deploy_hash=self.src101_dict.get("deploy_hash"))
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
            logger.warning(f"Invalid {self.deploy_hash} SRC101: {self.src101_dict['status']}")
            self.is_valid = False
            return
        try:
            self.validate_and_process_operation()
        except Exception as e:
            self.set_status_and_log("UE", error=e)
            self.is_valid = False
            logger.warning(f"exception: {e}")


def parse_src101(db, src101_dict, processed_src101_in_block, block_index):
    processor = Src101Processor(db, src101_dict, processed_src101_in_block, block_index)
    processor.process()

    return processor.is_valid, src101_dict


def check_and_convert_addres_type_data(data, hex_prev_tx_hash):
    try:
        valid = False
        if "btc" in data.keys() and data["btc"] and data["btc"] != "":
            valid = check_valid_bitcoin_address(data["btc"])
            if not valid:
                return valid
        if "eth" in data.keys() and data["eth"] and data["eth"] != "":
            recovered_address = Account.recover_message(
                encode_defunct(text=hex_prev_tx_hash), signature=bytes.fromhex(data["eth"])
            )
            valid = check_valid_eth_address(recovered_address)
            recovered_address = recovered_address[2:]
            data["eth"] = recovered_address
        return valid, data
    except:
        return False, data


def check_src101_inputs(input_string, tx_hash, block_index):
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
                "root",
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
                "wla",
                "imglp",
                "imgf",
                "idua",
            }
            transfer_keys = {"p", "op", "hash", "toaddress", "tokenid"}
            if block_index < BTC_SRC101_IMG_OPTIONAL_BLOCK:
                mint_keys = {"p", "op", "hash", "toaddress", "tokenid", "dua", "prim", "sig", "img", "coef"}
            else:
                mint_keys = {"p", "op", "hash", "toaddress", "tokenid", "dua", "prim", "sig", "coef"}
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
                if block_index < BTC_SRC101_IMG_OPTIONAL_BLOCK:
                    match = (len(mint_keys ^ input_keys) != 0)
                else:
                    match = not all(field in input_dict for field in mint_keys)
                if match:
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
    except Exception as e:
        logger.error(f"Error check_src101_inputs: {e}")
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
                                "address_btc": src101_dict["src101_owner"],
                                "address_eth": None,
                                "prim": src101_dict["prim"],
                                "img": src101_dict["img"][index],
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
                            "address_btc": None,
                            "address_eth": None,
                            "prim": False,
                            "img": None,
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
                            "address_btc": src101_dict["address_btc"],
                            "address_eth": src101_dict["address_eth"],
                            "prim": src101_dict["prim"],
                            "img": None,
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
                            "address_btc": src101_dict["address_btc"],
                            "address_eth": src101_dict["address_eth"],
                            "prim": src101_dict["prim"],
                            "img": None,
                        }
                        owner_updates.append(owner_dict)
                    else:
                        owner_dict["txt_data"] = src101_dict["txt_data"]
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
            imgurl = owner_dict["img"]
            if owner_dict["prim"] and owner_dict["prim"] == True:
                cursor.execute(
                    f"""
                    UPDATE {SRC101_OWNERS_TABLE}
                    SET prim = FALSE
                    WHERE address_btc = %s AND deploy_hash = %s AND prim = TRUE;
                    """,
                    (
                        owner_dict["address_btc"],
                        owner_dict["deploy_hash"],
                    ),
                )
            cursor.execute(
                f"""
                INSERT INTO {SRC101_OWNERS_TABLE}
                ({SRC101_OWNERS_TABLE}.index, id, last_update, p, deploy_hash, tokenid, tokenid_utf8, img, preowner, owner, txt_data, expire_timestamp, address_btc, address_eth, prim)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    last_update = VALUES(last_update),
                    preowner = VALUES(preowner),
                    owner = VALUES(owner),
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


def get_owner_expire_data_from_running(db, processed_src101_in_block, deploy_hash, tokenid_utf8):
    preowner = None
    owner = None
    expire_timestamp = None
    address_btc = None
    address_eth = None
    txt_data = None
    prim = None
    for d in processed_src101_in_block:
        if (
            d
            and d.get("tokenid_utf8")
            and type(d.get("tokenid_utf8")) == list
            and tokenid_utf8 in d.get("tokenid_utf8")
            and d.get("hash") == deploy_hash
            and d.get("valid", 0) == 1
        ):
            preowner = d.get("src101_preowner")
            owner = d.get("src101_owner")
            expire_timestamp = d.get("expire_timestamp")
            address_btc = d.get("address_btc")
            address_eth = d.get("address_eth")
            txt_data = json.dumps(d.get("txt_data"))
            prim = d.get("prim")
        elif (
            d
            and d.get("tokenid_utf8")
            and type(d.get("tokenid_utf8")) == str
            and tokenid_utf8 == d.get("tokenid_utf8")
            and d.get("hash") == deploy_hash
            and d.get("valid", 0) == 1
        ):
            preowner = d.get("src101_preowner")
            owner = d.get("src101_owner")
            expire_timestamp = d.get("expire_timestamp")
            address_btc = d.get("address_btc")
            address_eth = d.get("address_eth")
            txt_data = json.dumps(d.get("txt_data"))
            prim = d.get("prim")
    if owner and expire_timestamp:
        return [preowner, owner, expire_timestamp, address_btc, address_eth, txt_data, prim]
    return get_owner_expire_data_from_db(db, deploy_hash, tokenid_utf8)


def get_owner_expire_data_from_db(db, deploy_hash, tokenid_utf8):
    cursor = db.cursor()
    cursor.execute(
        f"SELECT preowner, owner,expire_timestamp,address_btc,address_eth,txt_data,prim FROM {SRC101_OWNERS_TABLE} WHERE tokenid_utf8 = %s AND deploy_hash = %s",
        (tokenid_utf8, deploy_hash),
    )
    result = cursor.fetchone()
    if not result:
        result = [None, None, None, None, None, None, None]
    return result
