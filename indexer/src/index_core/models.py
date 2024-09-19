import base64
import hashlib
import json
import logging
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar, Dict, List, Optional, TypedDict, Union

import magic
import msgpack
import regex as re

import index_core.log as log
from config import (
    CP_BMN_FEAT_BLOCK_START,
    CP_P2WSH_FEAT_BLOCK_START,
    CP_SRC20_END_BLOCK,
    CP_SRC721_GENESIS_BLOCK,
    DOMAINNAME,
    INVALID_BTC_STAMP_SUFFIX,
    STRIP_WHITESPACE,
    SUPPORTED_SUB_PROTOCOLS,
)
from index_core.src20 import build_src20_svg_string, check_format
from index_core.src101 import check_src101_inputs
from index_core.src721 import validate_src721_and_process
from index_core.util import create_base62_hash

logger = logging.getLogger(__name__)
log.set_logger(logger)


class ValidStamp(TypedDict):
    stamp_number: int
    tx_hash: str
    cpid: str
    is_btc_stamp: bool
    is_valid_base64: bool
    stamp_base64: str
    is_cursed: bool
    src_data: str


@dataclass
class StampData:
    """
    A class to encapsulate all data related to a stamp transaction.

    Attributes:
        tx_hash (str): The hash of the transaction.
        source (str): The source address of the transaction.
        destination (str): The destination address of the transaction.
        btc_amount (float): The amount of BTC in the transaction.
        fee (float): The transaction fee.
        data (str): The data associated with the transaction.
        decoded_tx (str): The decoded transaction.
        keyburn (int): The keyburn value.
        tx_index (int): The index of the transaction.
        block_index (int): The index of the block containing the transaction.
        block_time (int): The timestamp of the block containing the transaction.
        is_op_return (bool): Indicates if the transaction is an OP_RETURN transaction.
        valid_stamps_in_block (List[ValidStamp]): A list to store valid stamps in the block.
        p2wsh_data (bytes): The P2WSH data associated with the transaction.
    """

    tx_hash: str
    source: str
    prev_tx_hash: str
    destination: str
    destination_nvalue: int
    btc_amount: float
    fee: float
    data: str
    decoded_tx: str
    keyburn: int
    tx_index: int
    block_index: int
    block_time: Union[int, datetime]
    block_timestamp: int
    is_op_return: bool
    p2wsh_data: bytes
    stamp: Optional[int] = None
    creator: Optional[str] = None
    cpid: Optional[str] = None
    asset_longname: Optional[str] = None
    divisible: Optional[bool] = None
    ident: Optional[str] = None
    locked: Optional[bool] = None
    message_index: Optional[int] = None
    stamp_base64: Optional[str] = None
    stamp_mimetype: Optional[str] = None
    stamp_url: Optional[str] = None
    supply: Optional[int] = None
    src_data: Optional[str] = None
    stamp_hash: Optional[str] = None
    is_btc_stamp: Optional[bool] = None
    is_cursed: Optional[bool] = None
    file_hash: Optional[str] = None
    is_valid_base64: Optional[bool] = None
    file_suffix: Optional[str] = None
    decoded_base64: Optional[Union[str, bytes]] = None
    src20_dict: Optional[dict] = None
    src101_dict: Optional[dict] = None
    pval_src20: Optional[bool] = None
    pval_src101: Optional[bool] = None
    is_posh: Optional[bool] = False
    precomputed_collections: ClassVar[List[Dict]] = []

    @staticmethod
    def check_custom_suffix(bytestring_data):
        """for items that aren't part of the magic module that we want to include"""
        if bytestring_data[:3] == b"BMN":
            return True
        else:
            return None

    def is_valid_json_object_or_array(self, s):
        s = s.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                json.loads(s)
                return True
            except json.JSONDecodeError:
                return False
        return False

    @staticmethod
    def generate_collection_id(name: str) -> bytes:
        return hashlib.md5(name.encode(), usedforsecurity=False).digest()

    @classmethod
    def precompute_collections(cls, collections: List[Dict]):
        if not cls.precomputed_collections:
            for collection in collections:
                collection_id = cls.generate_collection_id(collection["name"]).hex()
                file_hashes_set = set(collection.get("file_hashes", []))
                stamps_set = set(collection.get("stamps", []))
                is_posh = collection.get("is_posh", False)
                cls.precomputed_collections.append(
                    {
                        "collection_id": collection_id,
                        "name": collection["name"],
                        "file_hashes": file_hashes_set,
                        "stamps": stamps_set,
                        "creators": collection.get("creators", []),
                        "is_posh": is_posh,
                    }
                )

    def match_and_insert_collection_data(self, collections: List[Dict], db):
        if not self.__class__.precomputed_collections:
            self.__class__.precompute_collections(collections)

        collection_inserts = []
        stamp_inserts = []
        creator_inserts = []

        for collection in self.__class__.precomputed_collections:
            if (
                self.file_hash in collection["file_hashes"]
                or self.stamp in collection["stamps"]
                or (self.is_posh and collection["is_posh"])
            ):
                collection_inserts.append((collection["collection_id"], collection["name"]))
                stamp_inserts.append((collection["collection_id"], self.stamp))
                for creator in collection["creators"]:
                    creator_inserts.append((collection["collection_id"], creator))

        if collection_inserts:
            self.insert_into_collections(db, collection_inserts)
        if stamp_inserts:
            self.insert_into_collection_stamps(db, stamp_inserts)
        if creator_inserts:
            self.ensure_creators_exist(db, creator_inserts)
            self.insert_into_collection_creators(db, creator_inserts)

    @staticmethod
    def ensure_creators_exist(db, creator_inserts: List[tuple]):
        cursor = db.cursor()
        for _, creator_address in creator_inserts:
            cursor.execute("SELECT 1 FROM creator WHERE address = %s", (creator_address,))
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO creator (address) VALUES (%s)", (creator_address,))
        db.commit()

    @staticmethod
    def insert_into_collections(db, collection_inserts: List[tuple]):
        query = """
        INSERT INTO collections (collection_id, collection_name)
        VALUES (UNHEX(%s), %s)
        ON DUPLICATE KEY UPDATE collection_name=VALUES(collection_name)
        """
        cursor = db.cursor()
        cursor.executemany(query, collection_inserts)
        db.commit()

    @staticmethod
    def insert_into_collection_stamps(db, stamp_inserts: List[tuple]):
        query = """
        INSERT INTO collection_stamps (collection_id, stamp)
        VALUES (UNHEX(%s), %s)
        ON DUPLICATE KEY UPDATE collection_id=VALUES(collection_id), stamp=VALUES(stamp)
        """
        cursor = db.cursor()
        cursor.executemany(query, stamp_inserts)
        db.commit()

    @staticmethod
    def insert_into_collection_creators(db, creator_inserts: List[tuple]):
        query = """
        INSERT INTO collection_creators (collection_id, creator_address)
        VALUES (UNHEX(%s), %s)
        ON DUPLICATE KEY UPDATE collection_id=VALUES(collection_id), creator_address=VALUES(creator_address)
        """
        cursor = db.cursor()
        cursor.executemany(query, creator_inserts)
        db.commit()

    def is_javascript(self, bytestring_data):
        """
        Determines if the given bytestring data is JavaScript.
        """
        js_code = bytestring_data.decode("utf-8", errors="ignore")

        # Enhanced regex to detect common JavaScript syntax elements, including ES6 features
        js_pattern = re.compile(
            r"\b(function|var|let|const|if|else|for|while|=>|class|import|export|new|return|typeof|instanceof|catch|try|finally)\b",
            re.VERSION1,  # Ensure consistent behavior across all Python versions
        )
        if not js_pattern.search(js_code):
            return False

        # Check for some common JavaScript structures and constructs
        js_formatting_patterns = [
            r"\bfunction\s+\w+\s*\(",  # function declarations
            r"\bvar\s+\w+\s*=",  # var declarations
            r"\blet\s+\w+\s*=",  # let declarations
            r"\bconst\s+\w+\s*=",  # const declarations
            r"\bif\s*\(.*?\)\s*{",  # if statements
            r"\belse\s*{",  # else statements
            r"\bfor\s*\(.*?\)\s*{",  # for loops
            r"\bwhile\s*\(.*?\)\s*{",  # while loops
            r"\bclass\s+\w+\s*{",  # class declarations
            r'\bimport\s+.*?\s+from\s+["\']',  # import statements
            r"\bexport\s+(default\s+)?\w+\s*",  # export statements
            r"\bnew\s+\w+\s*\(",  # object instantiation
            r"\breturn\s+",  # return statements
            r"\btypeof\s+\w+",  # typeof operator
            r"\binstanceof\s+\w+",  # instanceof operator
            r"\bcatch\s*\(.*?\)\s*{",  # catch blocks
            r"\btry\s*{",  # try blocks
            r"\bfinally\s*{",  # finally blocks
            r"\b=>\s*{",  # arrow functions
        ]

        for pattern in js_formatting_patterns:
            if re.search(pattern, js_code, re.VERSION1):
                return True

        return False

    def decode_and_reformat_src_string(self):
        """
        Decode the source JSON string to a dictionary, reformat it by making all keys lowercase,
        and extract the identifier and file suffix.
        """
        if not isinstance(self.decoded_base64, dict):
            self.decoded_base64 = json.loads(self.decoded_base64)
        self.decoded_base64 = {k.lower(): v for k, v in self.decoded_base64.items()}
        if (
            self.decoded_base64
            and self.decoded_base64.get("p")
            and self.decoded_base64.get("p").upper() in SUPPORTED_SUB_PROTOCOLS
        ):
            self.ident = self.decoded_base64["p"].upper()
            self.file_suffix = "json"
        else:
            self.file_suffix = "json"  # a valid json file, but not SRC-20, will be cursed
            self.stamp_mimetype = "application/json"
            self.ident = "UNKNOWN"

    def zlib_decompress(self, compressed_data):
        """
        Decompresses zlib-compressed data and returns the decompressed data as a JSON string.
        """
        try:
            uncompressed_data = zlib.decompress(compressed_data)
            decoded_data = msgpack.unpackb(uncompressed_data)
            self.decoded_base64 = json.dumps(decoded_data)
            self.file_suffix = "json"
        except (zlib.error, msgpack.exceptions.ExtraData, TypeError) as e:
            logger.info(f"EXCLUSION: {type(e).__name__} occurred")
            self.ident = "UNKNOWN"
            return

        self.handle_json_string()  # this is a big assumption all zlib files will have a string...

    def update_file_suffix_and_mime_type(self, bytestring_data):
        """
        Updates the file suffix and MIME type based on the given bytestring data.
        """
        if self.block_index > CP_BMN_FEAT_BLOCK_START and self.check_custom_suffix(bytestring_data):
            self.file_suffix = "bmn"
            self.stamp_mimetype = None
            return

        try:
            json.loads(bytestring_data.decode("utf-8"))
            self.file_suffix = "json"
            self.stamp_mimetype = "application/json"
            return
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

        mime_type = magic.from_buffer(
            (bytestring_data.lstrip() if self.block_index > STRIP_WHITESPACE else bytestring_data),
            mime=True,
        )
        self.file_suffix = mime_type.split("/")[-1]
        self.stamp_mimetype = mime_type

        if (mime_type == "text/plain" or mime_type == "application/javascript") and self.is_javascript(bytestring_data):
            self.file_suffix = "js"
            self.stamp_mimetype = "application/javascript"

    def handle_bytes(self):
        try:
            self.decoded_base64 = self.decoded_base64.decode("utf-8")  # to check for a text encoded bytestring / src-20, etc
        except UnicodeDecodeError:
            self.handle_bytes_again()  # FIXME: if we detect a octet-stream or invalid type here we later flag in stamp.py as cursed

    def handle_bytes_again(self):
        self.update_file_suffix_and_mime_type(self.decoded_base64)  # retry magic on non-utf-8 decoded bytes
        if self.file_suffix in ["zlib"]:
            self.zlib_decompress(self.decoded_base64)
        else:
            # we can likely just flag as cursed here if in invalid filetypes instead of removing the stamp ident later
            self.ident = "STAMP"

    def handle_dict(self):
        self.decode_and_reformat_src_string()

    def handle_json_string(self):
        if self.is_valid_json_object_or_array(self.decoded_base64):
            self.decode_and_reformat_src_string()
        else:
            self.handle_string()  # for svg stamps

    def handle_string(self):
        self.decoded_base64 = self.decoded_base64.encode("utf-8")
        self.update_file_suffix_and_mime_type(self.decoded_base64)
        self.ident = "STAMP"

    def handle_unknown_type(self):
        self.file_suffix = None
        self.ident = "UNKNOWN"
        self.stamp_mimetype = None

    def check_decoded_data_fetch_ident_mime(self):
        """
        Check the decoded data and fetch the identifier, mime-type, and file suffix.

        Raises:
            Exception: If an error occurs during the process.
        """
        # FIXME: this needs some love upstream to simplify. SVG stamps (and CP SRC?) come in as strings, SRC-20 as bytes.
        try:
            if type(self.decoded_base64) is bytes:
                self.handle_bytes()
            if type(self.decoded_base64) is dict:
                self.handle_dict()  # SRC-20 coming in as bytes are converted to dict here
            elif type(self.decoded_base64) is str:
                self.handle_json_string()  # outputs dict for CP src-20, or a bytestring for svg stamps
            else:
                type_func_map = {
                    str: self.handle_string,
                    bytes: self.handle_bytes_again,
                }
                handler = type_func_map.get(type(self.decoded_base64), self.handle_unknown_type)
                handler()

        except Exception as e:
            logger.error(f"Error: {e}")
            raise

    def validate_data_exists(self):
        if not self.data:
            raise ValueError("Input data is empty or None")

    def update_stamp_data_rows_from_cp_asset(self, stamp: dict):
        self.cpid = stamp.get("cpid", None)
        self.asset_longname = stamp.get("asset_longname")
        self.supply = stamp.get("quantity")
        self.locked = stamp.get("locked")
        self.divisible = stamp.get("divisible")
        self.message_index = stamp.get("message_index")

    def update_stamp_hash_and_block_time(self):
        self.creator = self.source
        self.stamp_hash = create_base62_hash(self.tx_hash, str(self.block_index), 20)
        if isinstance(self.block_time, int):
            self.block_timestamp = self.block_time
            self.block_time = datetime.fromtimestamp(self.block_time, tz=timezone.utc)

    def is_reissue(self, check_reissue_func, db, valid_stamps_in_block):
        if self.cpid and check_reissue_func(db, self.cpid, valid_stamps_in_block):
            raise ValueError("reissue invalidation")

    def is_src20(self):
        return self.ident == "SRC-20" and self.keyburn == 1

    def is_src101(self):
        return self.ident == "SRC-101" and self.keyburn == 1

    def valid_cp_src20(self):
        return (
            self.is_src20()
            and self.cpid
            and self.block_index < CP_SRC20_END_BLOCK
            and self.supply == 0
            and self.cpid.startswith("A")
        )

    def valid_cp_src101(self):
        return self.is_src101() and self.cpid

    def valid_src20(self):
        results = self.valid_cp_src20() or (self.is_src20() and not self.cpid)
        self.pval_src20 = results
        return results

    def valid_src721(self):
        if self.block_index < CP_SRC721_GENESIS_BLOCK:
            return False
        base_condition = (
            self.ident == "SRC-721"
            and (self.keyburn == 1 or (self.p2wsh_data is not None and self.block_index >= CP_P2WSH_FEAT_BLOCK_START))
            and self.supply <= 1
        )
        return base_condition

    def valid_src101(self):
        results = self.valid_cp_src101() or (self.is_src101() and not self.cpid)
        self.pval_src101 = results
        return results

    def normalize_mime_and_suffix(self):
        self.normalize_file_suffix()
        self.normalize_mimetype()

    def normalize_file_suffix(self):
        suffix_map = {"svg+xml": "svg", "plain": "txt", "xhtml+xml": "html"}
        self.file_suffix = suffix_map.get(self.file_suffix, self.file_suffix)

    def normalize_mimetype(self):
        if not self.is_valid_base64:
            self.stamp_mimetype = None

    def get_base_64_data_from_trx(self, get_data_func, stamp):
        (
            self.decoded_base64,
            self.stamp_base64,
            self.stamp_mimetype,
            self.is_valid_base64,
        ) = get_data_func(stamp, self.block_index)

    def process_p2wsh_data(self, decode_base64_func):
        self.stamp_base64 = base64.b64encode(self.p2wsh_data).decode()
        self.decoded_base64, self.is_valid_base64 = decode_base64_func(self.stamp_base64, self.block_index)
        self.check_decoded_data_fetch_ident_mime()
        self.is_op_return = None  # reset because p2wsh are typically op_return

    def process_decoded_base64(self):
        self.check_decoded_data_fetch_ident_mime()

    def update_cpid_and_stamp_url(self, filename):
        self.cpid = self.cpid if self.cpid else self.stamp_hash
        self.stamp_url = (
            "https://" + DOMAINNAME + "/stamps/" + filename if self.file_suffix is not None and filename is not None else None
        )

    def determine_stamp_data_type(self, decode_base64_func):
        if self.p2wsh_data is not None and self.block_index >= CP_P2WSH_FEAT_BLOCK_START:
            self.process_p2wsh_data(decode_base64_func)
        elif self.decoded_base64 is not None:
            self.process_decoded_base64()
        else:
            self.handle_unknown_type()
        return self.decoded_base64

    def validate_and_process_stamp_data(self, decode_base64, db, valid_stamps_in_block):
        self.determine_stamp_data_type(decode_base64)

        ident_known = self.ident != "UNKNOWN"
        cpid_starts_with_A = self.cpid and self.cpid.startswith("A")

        valid_func_map = {
            self.valid_src20: (self.src20_pre_validation, (db,)),
            self.valid_src721: (self.process_src721, (valid_stamps_in_block, db)),
            self.valid_src101: (self.src101_pre_validation, ()),
        }

        for valid_func, (process_func, args) in valid_func_map.items():
            if valid_func():
                process_func(*args)

        if self.cpid:
            self.process_all_stamps(ident_known, cpid_starts_with_A)
        else:
            self.process_cursed_with_other_conditions(cpid_starts_with_A, ident_known)

    def src20_pre_validation(self, db):
        self.src20_dict = check_format(self.decoded_base64, self.tx_hash)
        if self.src20_dict is not None:
            self.is_btc_stamp = True
            self.decoded_base64 = build_src20_svg_string(
                db, self.src20_dict
            )  # valid stamps get decoded_base64 back to bytestring here
            self.file_suffix = "svg"
            self.stamp_mimetype = "image/svg+xml"
        else:
            raise ValueError(
                "Invalid SRC-20 Pre-check"
            )  # we don't save in stamp_results, stamp_data, valid_stamp, prevalidated_src20

    def src101_pre_validation(self):
        # TODO need  more check
        self.src101_dict = check_src101_inputs(self.decoded_base64, self.tx_hash)
        if self.src101_dict is not None:
            self.is_btc_stamp = True
        else:
            raise ValueError("Invalid SRC-101 Pre-check")

    def process_src721(self, valid_stamps_in_block, db):
        self.src_data = self.decoded_base64
        self.is_btc_stamp = True
        svg_output, self.file_suffix = validate_src721_and_process(self.src_data, valid_stamps_in_block, db)
        self.src_data = json.dumps(self.src_data)
        self.decoded_base64 = svg_output
        self.file_suffix = "svg"
        self.stamp_mimetype = "image/svg+xml"

    def process_all_stamps(self, ident_known, cpid_starts_with_A):
        if (
            ident_known
            and self.asset_longname is None
            and cpid_starts_with_A
            and not self.is_op_return
            and self.file_suffix not in INVALID_BTC_STAMP_SUFFIX
        ):
            self.is_btc_stamp = True
        else:
            if not self.process_cursed_with_asset_longname():
                self.process_cursed_with_other_conditions(cpid_starts_with_A, ident_known)

    def process_cursed_with_asset_longname(self):
        if self.asset_longname is not None:
            self.cpid = self.asset_longname
            self.is_cursed = True
            self.is_posh = True
            self.is_btc_stamp = False
            return True
        return False

    def process_cursed_with_other_conditions(self, cpid_starts_with_A, ident_known):
        if self.cpid and (
            self.file_suffix in INVALID_BTC_STAMP_SUFFIX or not cpid_starts_with_A or self.is_op_return or not ident_known
        ):
            self.is_btc_stamp = False
            self.is_cursed = True
        if self.cpid and not cpid_starts_with_A and self.file_suffix not in INVALID_BTC_STAMP_SUFFIX:
            self.is_posh = True

    def process_and_store_stamp_data(
        self,
        get_src_or_img_from_data,
        convert_to_dict_or_string,
        encode_and_store_file,
        check_reissue,
        decode_base64,
        db,
        valid_stamps_in_block,
    ):
        self.validate_data_exists()
        stamp = convert_to_dict_or_string(self.data, output_format="dict")

        self.get_base_64_data_from_trx(get_src_or_img_from_data, stamp)
        if stamp is not None:
            self.update_stamp_data_rows_from_cp_asset(stamp)
        self.update_stamp_hash_and_block_time()

        self.is_reissue(check_reissue, db, valid_stamps_in_block)
        self.validate_and_process_stamp_data(decode_base64, db, valid_stamps_in_block)

        self.normalize_mime_and_suffix()
        # if isinstance(self.decoded_base64, bytes):
        self.file_hash, filename = encode_and_store_file(  # can be any type (bytestring, string or dict)
            db,
            self.tx_hash,
            self.file_suffix,
            self.decoded_base64,
            self.stamp_mimetype,
        )

        self.update_cpid_and_stamp_url(filename)
        return True
