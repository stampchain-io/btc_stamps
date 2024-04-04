import json
import logging
import re
import hashlib
import datetime
from collections import namedtuple
import decimal
import time
import requests

from config import (
    TICK_PATTERN_SET,
    SRC20_TABLE,
    SRC20_VALID_TABLE,
    SRC_VALIDATION_API1,
    SRC20_BALANCES_TABLE,
    SRC_BACKGROUND_TABLE
)
import src.log as log

D = decimal.Decimal
logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger

DEPLOY_CACHE = {}
TOTAL_MINTED_CACHE = {}

def reset_src20_globals():
    global DEPLOY_CACHE
    global TOTAL_MINTED_CACHE
    DEPLOY_CACHE = {}
    TOTAL_MINTED_CACHE = {}


def build_src20_svg_string(db, src_20_dict):
    background_base64, font_size, text_color = get_srcbackground_data(db, src_20_dict.get('tick'))
    svg_image_data = generate_srcbackground_svg(src_20_dict, background_base64, font_size, text_color)
    return svg_image_data


# query the srcbackground mysql table for these columns tick, base64, font_size, text_color, unicode, p
def get_srcbackground_data(db, tick):
    """
    Retrieves the background image data for a given tick and p value.

    Args:
        db: The database connection object.
        tick: The tick value.

    Returns:
        A tuple containing the base64 image data, font size, and text color.
        If no data is found, returns (None, None, None).
    """
    with db.cursor() as cursor:
        query = f"""
            SELECT
                base64,
                CASE WHEN font_size IS NULL OR font_size = '' THEN '30px' ELSE font_size END AS font_size,
                CASE WHEN text_color IS NULL OR text_color = '' THEN 'white' ELSE text_color END AS text_color
            FROM
                {SRC_BACKGROUND_TABLE}
            WHERE
                tick = %s
                AND p = %s
        """
        cursor.execute(query, (tick, "SRC-20")) # NOTE: even SRC-721 placeholder has a 'SRC-20' p value for now
        result = cursor.fetchone()
        if result:
            base64, font_size, text_color = result
            return base64, font_size, text_color
        else:
            return None, None, None


def format_address(address):
    return address[:4] + '...' + address[-4:]


def generate_srcbackground_svg(input_dict, base64, font_size, text_color):
    if '\\' in input_dict['tick']:
        input_dict['tick'] = bytes(input_dict['tick'], "utf-8").decode("unicode_escape")
        input_dict['tick'] = input_dict['tick'] .replace('\\u', '\\U')


    if (input_dict.get("op").upper() == "DEPLOY"):
        dict_to_use = {
            "p": input_dict.get("p", None).upper(),
            "op": input_dict.get("op", None).upper(),
            "tick": input_dict.get("tick", None).upper(),
            "max": input_dict.get("max", None),
            "lim": input_dict.get("lim", None),
        }
    elif (
        input_dict.get("op").upper() == "MINT"
    ):
        dict_to_use = {
            "p": input_dict.get("p", None).upper(),
            "op": input_dict.get("op", None).upper(),
            "tick": input_dict.get("tick", None).upper(),
            "amt": input_dict.get("amt", None),
        }
    elif (
        input_dict.get("op").upper() == "TRANSFER"
    ):
        dict_to_use = {
            "p": input_dict.get("p", None).upper(),
            "op": input_dict.get("op", None).upper(),
            "tick": input_dict.get("tick", None).upper(),
            "amt": input_dict.get("amt", None),
        }

    sorted_keys = sorted(dict_to_use.keys(), key=sort_keys)
    pretty_json = json.dumps({k: dict_to_use[k] for k in sorted_keys}, indent=1, separators=(',', ': '), sort_keys=False, ensure_ascii=False, default=str)

    if base64 is not None:
        svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><foreignObject font-size="{font_size}" width="100%" height="100%"><p xmlns="http://www.w3.org/1999/xhtml" style="background-image: url(data:{base64});color:{text_color};padding:20px;margin:0px;width:1000px;height:1000px;"><pre>{pretty_json}</pre></p></foreignObject></svg>"""
    else:
        svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><foreignObject font-size="30px" width="100%" height="100%"><p xmlns="http://www.w3.org/1999/xhtml" style="background: rgb(149,56,182); background: linear-gradient(138deg, rgba(149,56,182,1) 23%, rgba(0,56,255,1) 100%);padding:20px;margin:0px;width:1000px;height:1000px;"><pre>{pretty_json}</pre></p></foreignObject></svg>"""
    img_data = svg_output.encode('utf-8')

    return img_data


def matches_any_pattern(text, char_set):
    """
    Checks if the characters in the given text matches chars in the pattern list.

    Args:
        text (str): The text to be checked.
        pattern_list (list): A list of regex patterns to match against.

    Returns:
        bool: True if all characters in the text matches the pattern list, False otherwise.
    """
    for char in text:
        if char not in char_set:
            return False
    return True


def sort_keys(key):
    priority_keys = ["p", "op", "tick"]
    if key in priority_keys:
        return priority_keys.index(key)
    return len(priority_keys)


def convert_to_utf8_string(tick_value):
    """
    Converts the tick value to a UTF-8 encoded string.

    Args:
        tick_value (str): The tick value to be converted.

    Returns:
        str: The converted tick value as a UTF-8 encoded string.
    """
    try:
        # This will work if tick_value is a string representation of a bytestring
        tick_value = tick_value.encode('latin-1').decode('utf-8')
    except UnicodeEncodeError:
        # This will work if tick_value is a valid UTF-8 character or a combination of ASCII and UTF-8 characters
        tick_value = tick_value.encode('utf-8').decode('utf-8')
    return tick_value


def check_format(input_string, tx_hash):
    """
    Check the format of the SRC-20 json string and return a dictionary if it meets the validation reqs.
    This is the original function to determine inclusion/exclusion as a valid stamp. 
    It is not used to validate user balances or full validitiy of the actual values in the string.
    If this does not evaluate to True the transaction is not saved to the stamp table.
    Edit with caution as this can impact stamp numbering.


    Args:
        input_string (str or bytes or dict): The input string to be checked.
        tx_hash (str): The transaction hash associated with the input string.

    Returns:
        dict or None: If the input string meets the requirements for src-20, a dictionary representing the input string is returned.
                     Otherwise, None is returned.

    Raises:
        json.JSONDecodeError: If the input string cannot be decoded as JSON.

    """
    try:
        try:
            if isinstance(input_string, bytes):
                input_string = input_string.decode('utf-8')
            elif isinstance(input_string, str):
                input_dict = json.loads(input_string)
            elif isinstance(input_string, dict):
                input_dict = input_string
        except (json.JSONDecodeError, TypeError):
            raise

        if input_dict.get("p").lower() == "src-721":
            return input_dict
        elif input_dict.get("p").lower() == "src-20":
            tick_value = convert_to_utf8_string(input_dict.get("tick"))
            is_transfer = input_dict.get("op").upper() == "TRANSFER"
            input_dict["tick"] = tick_value
            if not tick_value or not matches_any_pattern(tick_value, TICK_PATTERN_SET) or len(tick_value) > 5:
                logger.warning(f"EXCLUSION: did not match tick pattern", input_dict)
                return None

            deploy_keys = {"op", "tick", "max", "lim"}
            transfer_keys = {"op", "tick", "amt"}
            mint_keys = {"op", "tick", "amt"}
            bulk_xfer_keys = {"op", "tick", "amt", "destinations"} # note this requires a destinations list

            input_keys = set(input_dict.keys())

            uint64_max = D(2 ** 64 - 1)
            key_sets = [deploy_keys, transfer_keys, mint_keys, bulk_xfer_keys]
            key_values_to_check = {
                "deploy_keys": ["max", "lim"],
                "transfer_keys": ["amt"],
                "mint_keys": ["amt"],
                "bulk_xfer_keys": ["amt"],
            }

            for i, key_set in enumerate(key_sets):
                if input_keys >= key_set:
                    for key in key_values_to_check[list(key_values_to_check.keys())[i]]:
                        value = input_dict.get(key)
                        if value is None:
                            logger.warning(f"EXCLUSION: Missing or invalid value for {key}", input_dict)
                            return None

                        if isinstance(value, str):
                            try:
                                value = D(''.join(c for c in value if c.isdigit() or c == '.')) if value else D(0)
                            except decimal.InvalidOperation as e:
                                logger.warning(f"EXCLUSION: {key} not a valid decimal: {e}. Input dict: {input_dict}, {tx_hash}")
                                return None
                        elif isinstance(value, int):
                            value = D(value)
                        elif isinstance(value, float) and is_transfer:
                            value = D(str(value))
                        else:
                            logger.warning(f"EXCLUSION: {key} not a string or integer", input_dict)
                            return None

                        if not (0 <= value <= uint64_max):
                            logger.warning(f"EXCLUSION: {key} not in range", input_dict)
                            return None
            return input_dict

    except json.JSONDecodeError:
        return None

    return None


def get_first_src20_deploy_lim_max(db, tick, src20_processed_in_block):
    if tick in DEPLOY_CACHE:
        return DEPLOY_CACHE[tick]["lim"], DEPLOY_CACHE[tick]["max"], DEPLOY_CACHE[tick]["dec"]
    processed_blocks = {f"{item['tick']}-{item['op']}": item for item in src20_processed_in_block}

    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            SELECT
                lim, max, deci
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND op = 'DEPLOY'
                AND p = 'SRC-20'
            ORDER BY
                block_index ASC
            LIMIT 1
        """, (tick,))
        result = src20_cursor.fetchone()

        if result:
            lim, max_value, dec = result
            DEPLOY_CACHE[tick] = {"lim": lim, "max": max_value, "dec": dec}
            return lim, max_value, dec
        else:
            lim, max_value, dec = get_first_src20_deploy_lim_max_in_block(processed_blocks, tick)
            if lim is None or max_value is None:
                return 0, 0, 18
            DEPLOY_CACHE[tick] = {"lim": lim, "max": max_value, "dec": dec}
            return lim, max_value, dec


def get_first_src20_deploy_lim_max_in_block(processed_blocks, tick):
    """
    Retrieves the 'lim', 'max', and 'dec' values from the processed_blocks dictionary for a given tick.

    Args:
        processed_blocks (dict): A dictionary containing processed blocks.
        tick (str): The tick value to search for in the processed_blocks dictionary.

    Returns:
        tuple: A tuple containing the 'lim', 'max', and 'dec' values for the given tick. If the tick is not found,
               returns (None, None, None).
    """
    key = f"{tick}-DEPLOY"
    if key in processed_blocks:
        item = processed_blocks[key]
        return item["lim"], item["max"], item["dec"]
    return None, None, None


def get_total_minted_from_db(db, tick):
    '''Retrieve the total amount of tokens minted from the database for a given tick.

    This function performs a database query to fetch the total amount of tokens minted
    for a specific tick. 

    Args:
        db (DatabaseConnection): The database connection object.
        tick (int): The tick value for which to retrieve the total minted tokens.

    Returns:
        int: The total amount of tokens minted for the given tick.
    '''
    if tick in TOTAL_MINTED_CACHE:
        return TOTAL_MINTED_CACHE[tick]

    total_minted = 0
    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            SELECT
                amt
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND op = 'MINT'
        """, (tick,))
        for row in src20_cursor.fetchall():
            total_minted += row[0]
    TOTAL_MINTED_CACHE[tick] = total_minted
    return total_minted


def get_running_mint_total(db, src20_processed_in_block, tick):
    """
    Get the running mint total for a given tick.

    Args:
        db (Database): The database object.
        src20_processed_in_block (list): The list of processed SRC20 items in a block.
        tick (int): The tick value.

    Returns:
        Decimal: The running mint total for the given tick.
    """
    total_minted = 0
    if len(src20_processed_in_block) > 0:
        for item in reversed(src20_processed_in_block):
            if (
                item["tick"] == tick
                and item["op"] == 'MINT'
                and "total_minted" in item
            ):
                total_minted = item["total_minted"]
                break
    if total_minted == 0:
        total_minted = get_total_minted_from_db(db, tick)

    return D(total_minted)


def get_running_user_balances(db, tick, tick_hash, addresses, src20_processed_in_block):
    """
    Calculate the running balance of multiple users based on the processed transactions 
    in current and prior blocks from the db. this is only be called once for each mint 
    bulk_xfer, or transfer transaction it may get many addresses from the bulk_xfer list. The 
    bulk_xfer list is assumed to have only unique addresses.

    Parameters:
    - db (Database): The database object.
    - tick (int): The tick value.
    - tick_hash (str): The tick hash value.
    - addresses (list or str): The list or string of addresses to calculate the balances for.
    - src20_processed_in_block (list): The list of already processed src20 transactions in the block.

    Returns:
    - list: A list of namedtuples containing the tick, address, and total balance for each address.
    """

    BalanceCurrent = namedtuple('BalanceCurrent', ['tick', 'address', 'total_balance', 'locked_balance'])

    if isinstance(addresses, str):
        addresses = [addresses]
    if len(addresses) != len(set(addresses)):
        raise Exception(f"The addresses list is not all unique addresses: tick={tick}, addresses={addresses}")

    balances = []

    if any(item["tick"] == tick for item in src20_processed_in_block):
        try:
            for prior_tx in reversed(src20_processed_in_block):  # if there is a total-balance in a trx in the block with the same address, tick, and tick_hash, use that value for total_balance_x
                if prior_tx.get("valid") == 1:  # Check if the dict has a valid key with a value of 1
                    for address in addresses:
                        total_balance = None
                        locked_balance = None
                        if (
                            prior_tx["creator"] == address
                            and prior_tx["tick"] == tick
                            and prior_tx["tick_hash"] == tick_hash
                            and "total_balance_creator" in prior_tx # this gets added to the tuple which will be returned for the address and later added to src20_valid.??
                        ):
                            if "total_balance_creator" in prior_tx:
                                total_balance = prior_tx["total_balance_creator"]
                        
                        elif (
                            prior_tx["destination"] == address
                            and prior_tx["tick"] == tick
                            and prior_tx["tick_hash"] == tick_hash
                            and "total_balance_destination" in prior_tx
                        ):
                            if "total_balance_destination" in prior_tx:
                                total_balance = prior_tx["total_balance_destination"]
                        if total_balance is not None: # we got this address balance from the db in a prior loop and it exists in the src20_valid_dict so we can use it
                            balances.append(BalanceCurrent(tick, address, D(total_balance), locked_balance))
                            addresses.remove(address)
        except Exception as e:
            raise

    if addresses:
        try:
            total_balance_tuple = get_total_user_balance_from_balances_db(db, tick, tick_hash, addresses)
            for address in addresses:
                total_balance = next((balance.total_balance for balance in total_balance_tuple if balance.address == address), 0)
                locked_balance = next((balance.locked_amt for balance in total_balance_tuple if balance.address == address), 0) ## NOTE: this is not fully implemented
                # if total_balance is negative throw an exception
                if total_balance < 0:
                    raise Exception(f"Negative balance for address {address} in tick {tick}")
                balances.append(BalanceCurrent(tick, address, D(total_balance), locked_balance if total_balance != 0 else 0))
        except Exception as e:
            print(f"An exception occurred: {e}")
            raise

    return balances


def get_total_user_balance_from_balances_db(db, tick, tick_hash, addresses):
    ''' a revised version of get_total_user_balance_from_db to fetch only from
        the balances table, this should be much more efficient, and we can do 
        a cross check against the get_total_user_balance_from_db to validate and
        for balance table rebuilds '''

    if isinstance(addresses, str):
        addresses = [addresses]

    balances = []
    BalanceTuple = namedtuple('BalanceTuple', ['tick', 'address', 'total_balance', 'highest_block_index', 'block_time_unix', 'locked_amt'])

    with db.cursor() as src20_cursor:
        query = f"""
            SELECT
                tick,
                address,
                amt,
                last_update,
                block_time,
                locked_amt
            FROM
                {SRC20_BALANCES_TABLE}
            WHERE
                tick = %s
                AND tick_hash = %s
                AND address IN %s
        """

        src20_cursor.execute(query, (tick, tick_hash, tuple(addresses)))
        results = src20_cursor.fetchall()
        for address in addresses:
            total_balance = D('0')
            highest_block_index = 0
            block_time_unix = None
            for result in results:
                tick = result[0]
                address = result[1]
                total_balance = result[2]
                highest_block_index = result[3]
                block_time_unix = result[4]
                locked_amt = result[5]
                balances.append(BalanceTuple(tick, address, total_balance, highest_block_index, block_time_unix, locked_amt))

    return balances


def get_total_user_balance_from_db(db, tick, tick_hash, addresses):
    ''' another heavy operation to be running on every creator/tick pair
        this is for validation, the speedy version should pull from the balances table 
        keep in mind balance table is not committed on each transaction 
        The address list must be unique addresses '''
    
    ## this may be better to fetch all tick/address combinations from each block and store in memory... 
    ## would need to include the recipients of bulk_xfers... perhaps if we see an bulk_xfer in the block expand it out first in the dict
    if isinstance(addresses, str):
        addresses = [addresses]

    balances = []
    BalanceTuple = namedtuple('BalanceTuple', ['tick', 'address', 'total_balance', 'highest_block_index', 'block_time_unix'])

    with db.cursor() as src20_cursor:
        query = f"""
            SELECT
                amt,
                op,
                destination,
                creator,
                block_index,
                UNIX_TIMESTAMP(block_time) AS block_time_unix
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s 
                AND tick_hash = %s
                AND (destination IN %s OR creator IN %s)
                AND (op = 'TRANSFER' OR op = 'MINT')
            ORDER BY block_index
        """

        src20_cursor.execute(query, (tick, tick_hash, tuple(addresses), tuple(addresses)))
        # src20_cursor.execute(query, {'tick': tick, 'tick_hash': tick_hash, 'addresses': tuple(addresses)})
        results = src20_cursor.fetchall()
        for address in addresses:
            total_balance = D('0')
            highest_block_index = 0
            q_block_time_unix = None
            for result in results:
                q_amt = D(result[0])
                q_op = result[1]
                q_destination = result[2]
                q_creator = result[3]
                q_block_index = result[4]
                q_block_time_unix = result[5]
                if q_block_index > highest_block_index:
                    highest_block_index = q_block_index
                if q_op == 'MINT' and q_destination == address:
                    total_balance += q_amt
                if q_op == 'TRANSFER' and q_destination == address:
                    total_balance += q_amt
                if q_op == 'TRANSFER' and q_creator == address:
                    total_balance -= q_amt
            balances.append(BalanceTuple(tick, address, total_balance, highest_block_index, q_block_time_unix))

    return balances


def get_tick_holders_from_balances(db, tick):
    '''
    Retrieve the addresses of all tick holders with a balance greater than zero in the prior block.
    This function is not aware of pending / uncommitted transactions.

    Parameters:
    - db: The database connection object.
    - tick: The tick value.

    Returns:
    - tick_holders: A list of addresses of tick holders with a balance greater than zero.
    '''
    tick_holders = []
    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            SELECT
                address
            FROM
                {SRC20_BALANCES_TABLE}
            WHERE
                tick = %s
                AND amt > 0
        """, (tick,))
        for row in src20_cursor.fetchall():
            tick_holders.append(row[0])
    return tick_holders


def insert_into_src20_tables(db, valid_src20_in_block):
    with db.cursor() as src20_cursor:
        for i, src20_dict in enumerate(valid_src20_in_block):
            id = f"{i}_{src20_dict.get('tx_index')}_{src20_dict.get('tx_hash')}"
            if src20_dict.get("valid") == 1:
                insert_into_src20_table(src20_cursor, SRC20_VALID_TABLE, id, src20_dict)
                
            insert_into_src20_table(src20_cursor, SRC20_TABLE, id, src20_dict)


def insert_into_src20_table(cursor, table_name, id, src20_dict):
    block_time = src20_dict.get("block_time")
    if block_time:
        block_time_utc = datetime.datetime.utcfromtimestamp(block_time)
    column_names = [
        "id",
        "tx_hash",
        "tx_index",
        "amt",
        "block_index",
        "creator",
        "deci",
        "lim",
        "max",
        "op",
        "p",
        "tick",
        "destination",
        "block_time",
        "tick_hash",
        "status"
    ]
    column_values = [
        id,
        src20_dict.get("tx_hash"),
        src20_dict.get("tx_index"),
        src20_dict.get("amt"),
        src20_dict.get("block_index"),
        src20_dict.get("creator"),
        src20_dict.get("dec"),
        src20_dict.get("lim"),
        src20_dict.get("max"),
        src20_dict.get("op"),
        src20_dict.get("p"),
        src20_dict.get("tick"),
        src20_dict.get("destination"),
        block_time_utc,
        src20_dict.get("tick_hash"),
        src20_dict.get("status")
    ]

    if "total_balance_creator" in src20_dict and table_name == SRC20_VALID_TABLE:
        column_names.append("creator_bal")
        column_values.append(src20_dict.get("total_balance_creator"))

    if "total_balance_destination" in src20_dict and table_name == SRC20_VALID_TABLE:
        column_names.append("destination_bal")
        column_values.append(src20_dict.get("total_balance_destination"))

    placeholders = ", ".join(["%s"] * len(column_names))

    query = f"""
        INSERT INTO {table_name} ({", ".join(column_names)})
        VALUES ({placeholders})
    """

    cursor.execute(query, tuple(column_values))

    return


def is_number(s):
    '''
    Check if the input string is a valid positive number.

    Args:
        s (str): The input string to be checked.

    Returns:
        bool: True if the input string is a valid number, False otherwise.
    '''
    pattern = r'^[+]?[0-9]*\.?[0-9]+$'
    return bool(re.match(pattern, str(s)))


def create_tick_hash(tick):
    ''' 
    Create a SHA3-256 of the normalized tick value. This is the final NIST SHA3-256 implementation
    not be be confused with Keccak-256 which is the Ethereum implementation of SHA3-256.

    Args:
        tick (str): The tick string to be hashed.

    Returns:
        str: The hashed tick string.
    '''
    # ignore-scan 
    return hashlib.sha3_256(tick.encode()).hexdigest()

class Src20Validator:
    def __init__(self, src20_dict):
        self.src20_dict = src20_dict
        self.updated_dict = {}

    def process_values(self):
        for key, value in self.src20_dict.items():
            if value == '':
                self.updated_dict[key] = None
            elif key in ['tick']:
                self._process_tick_value(key, value)
            elif key in ['p', 'op', 'holders_of']:
                self._process_uppercase_value(key, value)
            elif key in ['max', 'lim']:
                self._process_integer_value(key, value)
            elif key == 'amt':
                self._process_decimal_value(key, value)
            elif key == 'dec':
                self._process_dec_value(key, value)
        self.src20_dict.update(self.updated_dict)
        return self.src20_dict

    def _process_tick_value(self, key, value):
        self.updated_dict['tick'] = value.lower()
        self.updated_dict['tick_hash'] = create_tick_hash(value.lower())

    def _process_uppercase_value(self, key, value):
        self.updated_dict[key] = value.upper()

    def _process_integer_value(self, key, value):
        if not is_number(value):
            self.updated_dict[key] = None
            if 'status' in self.updated_dict:
                self.updated_dict['status'] += f', NN: {key} not NUM'
            else:
                self.updated_dict['status'] = f'NN: {key} not NUM'
        else:
            self.updated_dict[key] = int(D(value))

    def _process_decimal_value(self, key, value):
        if not is_number(value):
            self.updated_dict[key] = None
            if 'status' in self.updated_dict:
                self.updated_dict['status'] += f', NN: {key} not NUM'
            else:
                self.updated_dict['status'] = f'NN: {key} not NUM'
        else:
            # amt = int(value) if value == int(value) else Decimal(value)
            # self.updated_dict[key] = amt
            self.updated_dict[key] = D(str(value))

    def _process_dec_value(self, key, value):
        if value is None:
            self.updated_dict[key] = 18
        elif is_number(value):
            dec_value = int(value)
            if dec_value >= 0 and dec_value <= 18:
                self.updated_dict[key] = dec_value
            else:
                if 'status' in self.updated_dict:
                    self.updated_dict['status'] += f', NN: {key} not in range'
                else:
                    self.updated_dict['status'] = f' NN: {key} not in range'
        else:
            if 'status' in self.updated_dict:
                self.updated_dict['status'] += f', NN: {key} not NUM'
            else:
                self.updated_dict['status'] = f'NN: {key} not NUM'


def encode_non_ascii(text):
    """
    Encodes non-ASCII characters in the given text using unicode_escape encoding and then decodes it using utf-8 encoding.

    Args:
        text (str): The text to encode.

    Returns:
        str: The encoded and decoded text.
    """
    return text.encode('unicode_escape').decode('utf-8')


def create_running_user_balance_dict(running_user_balance_tuple):
    running_user_balance_dict = {}

    for balance_tuple in running_user_balance_tuple:
        address = getattr(balance_tuple, 'address')
        total_balance = getattr(balance_tuple, 'total_balance')
        running_user_balance_dict[address] = total_balance

    return running_user_balance_dict


def update_valid_src20_list(db, src20_dict, running_user_balance_creator, running_user_balance_destination, valid_src20_in_block, operation=None, total_minted=None, deploy_max=None, dec=None, deploy_lim=None):
    if operation == 'TRANSFER':
        amt = D(src20_dict['amt'])
        src20_dict['total_balance_creator'] = D(running_user_balance_creator) - amt
        src20_dict['total_balance_destination'] = D(running_user_balance_destination) + amt
        # src20_dict['locked_balance_creator'] = ## need to pass the tuple in here for simplicity  # WIP
        # src20_dict['locked_balance_destination'] = ## need to pass the tuple in here for simplicity # WIP
        src20_dict['status'] = 'Balance Updated'
        src20_dict['valid'] = 1
        valid_src20_in_block.append(src20_dict)
    elif operation == 'MINT' and total_minted is not None:

        # amt = math.floor((src20_dict['amt']) * 10 ** dec) / 10 ** dec
        # mint amt should be an integer? check specs
        amt = src20_dict['amt']
        if amt > deploy_lim:
            amt = deploy_lim
            src20_dict['amt'] = amt
        TOTAL_MINTED_CACHE[src20_dict.get("tick")] += amt
        running_total_mint = int(total_minted) + amt
        running_user_balance = D(running_user_balance_creator) + amt
        # src20_dict['status'] = f'OK: {running_total_mint} of {deploy_max}' # this will overwrite prior status. -- validate handling 
        src20_dict['total_minted'] = running_total_mint
        src20_dict['total_balance_destination'] = running_user_balance
        src20_dict['valid'] = 1
        valid_src20_in_block.append(src20_dict)
    elif operation == 'DEPLOY':
        src20_dict['valid'] = 1
        src20_dict['dec'] = dec
        valid_src20_in_block.append(src20_dict)
        # this was falling through and getting inserted at the end fo the function to src20

    else:
        raise Exception(f"Invalid Operation '{operation}' on SRC20 Table Insert")
    return


def process_src20_trx(db, src20_dict, source, tx_hash, tx_index, block_index, block_time, destination, valid_src20_in_block):
    ''' this is to process all SRC-20 Tokens that pass check_format '''
    
    src20_dict['creator'] = source
    src20_dict['tx_hash'] = tx_hash
    src20_dict['tx_index'] = tx_index
    src20_dict['block_index'] = block_index
    src20_dict['block_time'] = block_time
    src20_dict['destination'] = destination
    tick_value = src20_dict.get('tick')
    src20_dict["tick"] = encode_non_ascii(tick_value)

    validator = Src20Validator(src20_dict)
    src20_dict = validator.process_values()

    # src20_dict = process_values(src20_dict) # this does normalization of the tick patterns
    deploy_lim, deploy_max, dec = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)
    # if src20_dict status field contains NN then it's not a valid number we only insert into the src20 table - not valid table

    if src20_dict.get('status') and 'NN' in src20_dict['status']:
        valid_src20_in_block.append(src20_dict) # invalid
        logger.warning(f"Invalid {src20_dict['tick']} SRC20: {src20_dict['status']}")
        return
 
    if src20_dict['op'] == 'DEPLOY' and src20_dict['tick_hash']:
        dec = src20_dict.get('dec', 18)
        if not deploy_lim and not deploy_max: # this is a new deploy if these aren't returned from the db
            update_valid_src20_list(db, src20_dict, None, None, valid_src20_in_block, operation='DEPLOY', dec=dec)
            return True # for test cases
        else:
            logger.info(f"Invalid {src20_dict['tick']} DEPLOY - prior DEPLOY exists")
            src20_dict['status'] = f'DE: prior {src20_dict["tick"]} DEPLOY exists'
            valid_src20_in_block.append(src20_dict) # invalid
            return

    elif src20_dict['op'] == 'MINT' and src20_dict['tick_hash']:
        if not src20_dict.get('amt'):
            src20_dict['status'] = f'NN: amt not NUM'
            valid_src20_in_block.append(src20_dict) # invalid
            return
        
        if deploy_lim and deploy_max:
            deploy_lim = int(min(deploy_lim, deploy_max)) # deploy_lim cannot be > deploy_max
            try:
                total_minted = D(get_running_mint_total(db, valid_src20_in_block, src20_dict['tick']))
            except Exception as e:
                logger.error(f"Error getting total minted: {e}")
                raise

            try:
                running_user_balance_tuple = get_running_user_balances(db, src20_dict['tick'], src20_dict['tick_hash'], src20_dict['destination'], valid_src20_in_block)
                if running_user_balance_tuple:
                    running_user_balance = running_user_balance_tuple[0].total_balance
                else:
                    running_user_balance = D('0')
            except Exception as e:
                logger.error(f"Error getting running user for mint balance: {e}")
                raise

            mint_available = D(deploy_max) - D(total_minted)

            if total_minted >= deploy_max:
                logger.info(f" {src20_dict['tick']} OVERMINT: minted {total_minted} > max {deploy_max}")
                src20_dict['status'] = f'OM: Over Max: {total_minted} >= {deploy_max}'
                valid_src20_in_block.append(src20_dict) # invalid 
                return
            else:
                if src20_dict['amt'] > mint_available:
                    src20_dict['status'] = f'OMA:  FROM: {src20_dict["amt"]} TO: {mint_available}'
                    src20_dict['amt'] = mint_available
                    logger.info(f"Reducing {src20_dict['tick']} OVERMINT: minted {total_minted} + amt {src20_dict['amt']} > max {deploy_max} - remain {mint_available} ")
                    try:
                        update_valid_src20_list(db, src20_dict, running_user_balance, None, valid_src20_in_block, operation='MINT', total_minted=total_minted, deploy_max=deploy_max, dec=dec, deploy_lim=deploy_lim) # use the running_user_balance_tuple here to pull in locked WIP
                    except Exception as e:
                        logger.error(f"Error updating valid src20 list: {e}")
                        raise
                    return True # for test cases
                try:
                    update_valid_src20_list(db, src20_dict, running_user_balance, None, valid_src20_in_block, operation='MINT', total_minted=total_minted, deploy_max=deploy_max, dec=dec, deploy_lim=deploy_lim) # use the running_user_balance_tuple here to pull in locked WIP
                except Exception as e:
                    logger.error(f"Error updating valid src20 list: {e}")
                    return True # for test cases

        else:
            logger.info(f"Invalid {src20_dict['tick']} MINT - no deploy_lim {deploy_lim} and deploy_max {deploy_max}")
            src20_dict['status'] = f'ND: No Deploy {src20_dict["tick"]}'
            valid_src20_in_block.append(src20_dict) # invalid 
            return
        
    # Any transfer over the users balance at the time of transfer is considered invalid and will not impact either users balance
    # if wallet x has 1 KEVIN token and attempts to transfer 10000 KEVIN tokens to address y the entire transaction is invalid
    elif src20_dict['op'] == 'TRANSFER' and src20_dict['tick_hash']:  
        if not src20_dict.get('amt'):
            src20_dict['status'] = f'NN: amt not NUM'
            valid_src20_in_block.append(src20_dict) # invalid
            return
        if deploy_lim and deploy_max:
            try:
                if src20_dict['creator'] == src20_dict['destination']:
                    running_user_balance_tuple = get_running_user_balances(db, src20_dict['tick'], src20_dict['tick_hash'], [src20_dict['creator']], valid_src20_in_block)
                else:
                    running_user_balance_tuple = get_running_user_balances(db, src20_dict['tick'], src20_dict['tick_hash'], [src20_dict['creator'], src20_dict['destination']], valid_src20_in_block)
                running_user_balance_dict = create_running_user_balance_dict(running_user_balance_tuple)
                running_user_balance_creator = running_user_balance_dict.get(src20_dict.get('creator'), 0)
                running_user_balance_destination = running_user_balance_dict.get(src20_dict.get('destination'), 0)
            except Exception as e:
                logger.error(f"Error getting running user balances transfer: {e}")
                raise

            try:
                if D(running_user_balance_creator) > D('0') and D(running_user_balance_creator) >= D(src20_dict['amt']):
                    update_valid_src20_list(db, src20_dict, running_user_balance_creator, running_user_balance_destination, valid_src20_in_block, operation='TRANSFER', dec=dec)
                    return True # for test cases
                else:
                    logger.info(f"Invalid {src20_dict['tick']} TRANSFER - total_balance {running_user_balance_creator} < xfer amt {src20_dict['amt']}")
                    src20_dict['status'] = f'BB: TRANSFER over user balance'
                    valid_src20_in_block.append(src20_dict) # invalid 
                    return
            except Exception as e:
                logger.error(f"Error updating valid src20 list: {e}")
                raise
        return #for test cases
            
    # elif src20_dict['op'] == 'BULK_XFER':
    #     if deploy_lim and deploy_max:
    #         target_lim, target_max, dec = get_first_src20_deploy_lim_max(db, src20_dict['holders_of'], valid_src20_in_block)
    #         if target_lim and target_max: # valid target deploy
    #             # validate the src20_dict['destinations'] is a list of addresses
    #             if isinstance(src20_dict['destinations'], list):
    #                 destination_list = src20_dict['destinations']
    #                 # NOTE: the destination value from the transaction is ignored.

    #             if src20_dict['creator'] == src20_dict['destination']:
    #                 running_user_balance_tuple = get_running_user_balances(db, src20_dict['tick'], src20_dict['tick_hash'], [src20_dict['creator']], valid_src20_in_block)
    #             else:
    #                 running_user_balance_tuple = get_running_user_balances(db, src20_dict['tick'], src20_dict['tick_hash'], [src20_dict['creator'], src20_dict['destination']], valid_src20_in_block)
    #             # running_user_balance_tuple = get_running_user_balances(db, src20_dict['tick'], src20_dict['tick_hash'], [src20_dict['creator'], src20_dict['destination']], valid_src20_in_block)
    #             running_user_balance_creator = getattr(running_user_balance_tuple, 'total_balance')
                
    #             if running_user_balance > 0:
    #                 tick_holders = get_tick_holders_from_balances(db, src20_dict['holders_of'])
    #                 tick_holders.remove(src20_dict['creator']) # this removes the row of the creator from the target list
    #                 if tick_holders:
    #                     total_send_amt = len(tick_holders) * D(src20_dict['amt'])
    #                     if D(total_send_amt) <= D(running_user_balance_creator):
    #                         # build the valid_src20_in_block list for all transactions here and update running_user_balance
    #                         # append dicts for each possibly tick_holder to valid_src20_in_block
    #                         # append the current dict to valid_src20_in_block for the creator
    #                         # running_user_balance = D(running_user_balance) - D(total_send_amt)
    #                         src20_dict['total_balance_creator'] = running_user_balance
    #                         src20_dict['status'] = f'New Balance: {running_user_balance}'
    #                         # likely need to just update amount to total send amount here or all the removals will be handled below? 
    #                         # valid_src20_in_block.append(src20_dict) # this is the new balance for the creator. 

    #                         new_dicts = []
    #                         # need to get the running balance for all holders - pull this all in one shot.
    #                         running_dest_balances_tuple = get_running_user_balances(db, src20_dict['tick'], src20_dict['tick_hash'], tick_holders, valid_src20_in_block)
    #                         running_dest_balance_dict = create_running_user_balance_dict(running_dest_balances_tuple)
    #                         # then update the total balance key value for each.
    #                         for tick_holder in tick_holders:
    #                             total_balance_destination = running_dest_balance_dict.get(tick_holder, {}).get('total_balance', D('0'))
    #                             if total_balance_destination is None:
    #                                 raise RuntimeError("bulk_xfer: No match found between source and destination")
    #                             new_dict = {
    #                                 'p': 'SRC-20',
    #                                 'op': 'TRANSFER',
    #                                 'creator': src20_dict['creator'],
    #                                 'tick': src20_dict['tick'],
    #                                 'amt': src20_dict['amt'],
    #                                 'destination': tick_holder,
    #                                 'block_index': block_index,
    #                                 'tx_hash': tx_hash,
    #                                 'tx_index': tx_index,
    #                                 'block_time': block_time,
    #                                 'tick_hash': src20_dict['tick_hash'],
    #                                 'total_balance_destination': total_balance_destination + src20_dict['amt']
    #                             }
    #                             new_dicts.append(new_dict)

    #                         valid_src20_in_block.extend(new_dicts)
    #                         return

    #                     else:
    #                         logger.info(f"Invalid {src20_dict['tick']} bulk_xfer - total_balance {running_user_balance} < xfer amt {total_send_amt}")
    #                         src20_dict['status'] = f'BB: bulk_xfer over user balance'
    #         else:
    #             logger.info(f"Invalid {src20_dict['holders_of']} AD - Invalid holders_of")
    #             src20_dict['status'] = f'DD: Invalid holders_of'
    #     else:
    #         logger.info(f"Invalid {src20_dict['tick']} bulk_xfer - amt is not a number or not >0")
    return True # for test cases
    
def update_src20_balances(db, block_index, block_time, valid_src20_in_block):
    balance_updates = []

    # FIXME: we are looping through the list once for insert into db, and then again here for balances validations... combine! 
    
    for src20_dict in valid_src20_in_block:
        if src20_dict.get('valid') == 1:

            try:
                if src20_dict['op'] == 'MINT':
                    # Credit to destination (creator can be a mint service)
                    balance_dict = next((item for item in balance_updates if 
                                        item['tick'] == src20_dict['tick'] and 
                                        item['tick_hash'] == src20_dict['tick_hash'] and 
                                        item['address'] == src20_dict['destination']), None)
                    if balance_dict is None:
                        balance_dict = {
                            'tick': src20_dict['tick'],
                            'tick_hash': src20_dict['tick_hash'],
                            'address': src20_dict['destination'],
                            'credit': D(src20_dict['amt']),
                            'debit': D(0)
                        }
                        balance_updates.append(balance_dict)
                    else:
                        balance_dict['credit'] += D(src20_dict['amt'])

                elif src20_dict['op'] == 'TRANSFER':
                    # Debit from creator
                    balance_dict = next((item for item in balance_updates if 
                                        item['tick'] == src20_dict['tick'] and 
                                        item['tick_hash'] == src20_dict['tick_hash'] and 
                                        item['address'] == src20_dict['creator']), None)
                    if balance_dict is None:
                        balance_dict = {
                            'tick': src20_dict['tick'],
                            'tick_hash': src20_dict['tick_hash'],
                            'address': src20_dict['creator'],
                            'credit': D(0),
                            'debit': D(src20_dict['amt'])
                        }
                        balance_updates.append(balance_dict)
                    else:
                        balance_dict['debit'] += D(src20_dict['amt'])

                    # Credit to destination
                    balance_dict = next((item for item in balance_updates if 
                                        item['tick'] == src20_dict['tick'] and 
                                        item['tick_hash'] == src20_dict['tick_hash'] and 
                                        item['address'] == src20_dict['destination']), None)
                    if balance_dict is None:
                        balance_dict = {
                            'tick': src20_dict['tick'],
                            'tick_hash': src20_dict['tick_hash'],
                            'address': src20_dict['destination'],
                            'credit': D(src20_dict['amt']),
                            'debit': D(0)
                        }
                        balance_updates.append(balance_dict)
                    else:
                        balance_dict['credit'] += D(src20_dict['amt'])

            except Exception as e:
                logger.error(f"Error updating SRC20 balances: {e}")
                raise e
    
    if balance_updates:
        update_balance_table(db, balance_updates, block_index, block_time)
    return balance_updates


def update_balance_table(db, balance_updates, block_index, block_time):
    ''' update the balances table with the balance_updates list '''
    cursor = db.cursor()

    for balance_dict in balance_updates:
        try:
            net_change = balance_dict.get('credit', 0) - balance_dict.get('debit', 0)
            balance_dict['net_change'] = net_change
            id_field = balance_dict['tick'] + '_' + balance_dict['address']

            cursor.execute(f"SELECT amt FROM {SRC20_BALANCES_TABLE} WHERE id = %s", (id_field,))
            result = cursor.fetchone()
            if result is not None:
                balance_dict['original_amt'] = result[0]
            else:
                balance_dict['original_amt'] = 0

            cursor.execute("""
                INSERT INTO balances
                (id, address, tick, amt, last_update, block_time, p, tick_hash)
                VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s)
                ON DUPLICATE KEY UPDATE
                    amt = amt + VALUES(amt),
                    last_update = VALUES(last_update)
            """, (id_field, balance_dict['address'], balance_dict['tick'], net_change, block_index, block_time, 'SRC-20', balance_dict['tick_hash']))
                
        except Exception as e:
            logger.error("Error updating balances table:", e)
            raise e

    cursor.close()
    return


def process_balance_updates(balance_updates):
    """
    Process the balance updates and return a string representation of valid src20 entries.

    Args:
        balance_updates (list): A list of balance updates.

    Returns:
        str: A string representation of valid src20 entries.
    """

    valid_src20_list = []
    if balance_updates is not None:
        for src20 in balance_updates:
            creator = src20.get('address')
            if '\\' in src20['tick']:
                tick = src20['tick'].replace('\\u', '\\U')
                if len(tick) - 2 < 8:  # Adjusting for the length of '\\U'
                    tick = '\\U' + '0' * (10 - len(tick)) + tick[2:]
                tick = bytes(tick, "utf-8").decode("unicode_escape")
            else:
                tick = src20.get('tick')
            amt = src20.get('net_change') + src20.get('original_amt')
            amt = D(amt).normalize()
            if amt == int(amt):
                amt = int(amt)
            valid_src20_list.append(f"{tick},{creator},{amt}")
    valid_src20_list = sorted(valid_src20_list, key=lambda src20: (src20.split(',')[0] + '_' + src20.split(',')[1]))
    valid_src20_str = ';'.join(valid_src20_list)
    return valid_src20_str


def clear_zero_balances(db):
    """
    Deletes all balances with an amount of 0 from the database.

    Args:
        db: The database connection object.

    Returns:
        None
    """
    with db.cursor() as cursor:
        cursor.execute(f"DELETE FROM {SRC20_BALANCES_TABLE} WHERE amt = 0")
    return


def validate_src20_ledger_hash(block_index, ledger_hash, valid_src20_str):
    """
    Validates the SRC20 ledger hash for a given block index against remote API
    This is currently for OKX and will be to validate against stampscan.xyz as well

    Args:
        block_index (int): The index of the block.
        ledger_hash (str): The expected ledger hash.
        valid_src20_str (str): The valid SRC20 string.

    Returns:
        bool: True if the API ledger hash matches the ledger hash, False otherwise.

    Raises:
        ValueError: If the API ledger hash does not match the ledger hash.
        Exception: If failed to retrieve from the API after retries.
    """
    url = SRC_VALIDATION_API1 + str(block_index)
    max_retries = 10
    retry_count = 0

    while retry_count < max_retries:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                api_ledger_hash = response.json()['data']['hash']
                if api_ledger_hash == ledger_hash:
                    return True
                else:
                    api_ledger_validation = response.json()['data']['balance_data']
                    if api_ledger_validation != valid_src20_str:
                        logger.warning("API ledger validation does not match ledger validation for block %s", block_index)
                        logger.warning("API ledger validation: %s", api_ledger_validation)
                        logger.warning("Ledger validation: %s", valid_src20_str)
                        mismatches = []
                        for api_entry, ledger_entry in zip(api_ledger_validation, valid_src20_str):
                            if api_entry != ledger_entry:
                                mismatches.append((api_entry, ledger_entry))
                        for mismatch in mismatches:
                            logger.warning("Mismatch found:")
                            logger.warning("API Ledger: %s", mismatch[0])
                            logger.warning("Ledger: %s", mismatch[1])
                        if not mismatches:
                            logger.warning("The strings match perfectly.")
                        else:
                            logger.warning("Total mismatches: %s", len(mismatches))
                    raise ValueError('API ledger hash does not match ledger hash')
            else:
                retry_count += 1
                time.sleep(1)
        except requests.exceptions.RequestException as e:
            retry_count += 1
            time.sleep(1)
    raise Exception(f'Failed to retrieve from the API after {max_retries} retries')
