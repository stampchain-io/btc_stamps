from typing import TypedDict, Optional, Union
from dataclasses import dataclass
# from pymysql.connections import Connection
from datetime import datetime, timezone
import base64


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
    destination: str
    btc_amount: float
    fee: float
    data: str
    decoded_tx: str
    keyburn: int
    tx_index: int
    block_index: int
    block_time: Union[int, datetime]
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

    def validate_data(self):
        if not self.data:
            raise ValueError("Input data is empty or None")

    def update_stamp_data_rows(self, stamp: dict):
        self.asset_longname = stamp.get('asset_longname')
        self.supply = stamp.get('quantity')
        self.locked = stamp.get('locked')
        self.divisible = stamp.get('divisible')
        self.message_index = stamp.get('message_index')
        self.creator = self.source
        if isinstance(self.block_time, int):
            self.block_time = datetime.fromtimestamp(self.block_time, tz=timezone.utc)

    def update_cpid_and_stamp_hash(self, get_cpid_func, stamp):
        self.cpid, self.stamp_hash = get_cpid_func(stamp, self.block_index, self.tx_hash)

    def is_reissue(self, check_reissue_func, db, valid_stamps_in_block):
        return self.cpid and check_reissue_func(db, self.cpid, valid_stamps_in_block)

    def is_src20(self):
        return self.ident == 'SRC-20' and self.keyburn == 1

    def valid_cp_src20(self, CP_SRC20_END_BLOCK):
        return self.is_src20() and self.cpid and self.block_index < CP_SRC20_END_BLOCK and self.supply == 0

    def valid_src20(self, CP_SRC20_END_BLOCK):
        return self.valid_cp_src20(CP_SRC20_END_BLOCK) or (self.is_src20() and not self.cpid)

    def valid_src721(self, CP_P2WSH_FEAT_BLOCK_START):
        return self.ident == 'SRC-721' and (self.keyburn == 1 or (self.p2wsh_data is not None and self.block_index >= CP_P2WSH_FEAT_BLOCK_START)) and self.supply <= 1

    def normalize_file_suffix(self):
        self.file_suffix = "svg" if self.file_suffix == "svg+xml" else self.file_suffix

    def get_src_or_img(self, get_data_func, stamp):
        self.decoded_base64, self.stamp_base64, self.stamp_mimetype, self.is_valid_base64 = get_data_func(stamp, self.block_index)

    def process_stamp_data(
            self, decode_base64_func, check_decoded_data_fetch_ident_func, CP_P2WSH_FEAT_BLOCK_START):
        if self.p2wsh_data is not None and self.block_index >= CP_P2WSH_FEAT_BLOCK_START:
            self.stamp_base64 = base64.b64encode(self.p2wsh_data).decode()
            self.decoded_base64, self.is_valid_base64 = decode_base64_func(
                self.stamp_base64, self.block_index)
            # self.decoded_base64 = p2wsh_data # bytestring
            self.ident, self.file_suffix, self.decoded_base64 = check_decoded_data_fetch_ident_func(
                self.decoded_base64, self.block_index, self.ident)
            self.is_op_return = None  # reset because p2wsh are typically op_return
        elif self.decoded_base64 is not None:
            self.ident, self.file_suffix, self.decoded_base64 = check_decoded_data_fetch_ident_func(
                self.decoded_base64, self.block_index, self.ident)
        else:
            self.ident, self.file_suffix = 'UNKNOWN', None
        return self.decoded_base64

    def update_mime_type(self, MIME_TYPES):
        if not self.stamp_mimetype and self.file_suffix in MIME_TYPES:
            self.stamp_mimetype = MIME_TYPES[self.file_suffix]

    def update_cpid_and_stamp_url(self, DOMAINNAME, filename):
        self.cpid = self.cpid if self.cpid else self.stamp_hash
        self.stamp_url = f'https://{DOMAINNAME}/stamps/{filename}' if self.file_suffix is not None and filename is not None else None
