from decimal import Decimal, InvalidOperation
import json
import logging
from config import TICK_PATTERN_LIST, SRC20_TABLE, SRC20_VALID_TABLE, SRC20_BALANCES_TABLE
import src.log as log
import re
import hashlib

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger

DEPLOY_CACHE = {}
TOTAL_MINTED_CACHE = {}


def build_src20_svg_string(cursor, src_20_dict):
    background_base64, font_size, text_color = get_srcbackground_data(cursor, src_20_dict.get('tick'))
    svg_image_data = generate_srcbackground_svg(src_20_dict, background_base64, font_size, text_color)
    return svg_image_data


# query the srcbackground mysql table for these columns tick, base64, font_size, text_color, unicode, p
def get_srcbackground_data(cursor, tick):
    """
    Retrieves the background image data for a given tick and p value.

    Args:
        cursor: The database cursor object.
        tick: The tick value.

    Returns:
        A tuple containing the base64 image data, font size, and text color.
        If no data is found, returns (None, None, None).
    """
    query = """
        SELECT
            base64,
            CASE WHEN font_size IS NULL OR font_size = '' THEN '30px' ELSE font_size END AS font_size,
            CASE WHEN text_color IS NULL OR text_color = '' THEN 'white' ELSE text_color END AS text_color
        FROM
            srcbackground
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


def generate_srcbackground_svg(input_dict, base64, font_size, text_color):
    dict_to_use = {
        "p": input_dict.get("p", None),
        "op": input_dict.get("op", None),
        "tick": input_dict.get("tick", None),
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


def matches_any_pattern(text, pattern_list):
    matched = True
    for char in text:
        char_matched = any(pattern.fullmatch(char) for pattern in pattern_list)
        if not char_matched:
            matched = False
            break
    return matched


def sort_keys(key):
    priority_keys = ["p", "op", "tick"]
    if key in priority_keys:
        return priority_keys.index(key)
    return len(priority_keys)


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
                input_string = repr(input_string)[2:-1] #debug: this was a utf-8 decoding which was changing the content of Unicode strings
            elif isinstance(input_string, str):
                input_dict = json.loads(input_string)
            elif isinstance(input_string, dict):
                input_dict = input_string
        except (json.JSONDecodeError, TypeError):
            raise

        if input_dict.get("p") == "src-721":
            return input_dict
        elif input_dict.get("p") == "src-20":
            tick_value = input_dict.get("tick")
            if not tick_value or not matches_any_pattern(tick_value, TICK_PATTERN_LIST) or len(tick_value) > 5:
                logger.warning(f"EXCLUSION: did not match tick pattern", input_dict)
                return None

            deploy_keys = {"op", "tick", "max", "lim"}
            transfer_keys = {"op", "tick", "amt"}
            mint_keys = {"op", "tick", "amt"}

            input_keys = set(input_dict.keys())

            uint64_max = Decimal(2 ** 64 - 1)
            key_sets = [deploy_keys, transfer_keys, mint_keys]
            key_to_check = {"deploy_keys": ["max", "lim"], "transfer_keys": ["amt"], "mint_keys": ["amt"]}

            for i, key_set in enumerate(key_sets):
                if input_keys >= key_set:
                    for key in key_to_check[list(key_to_check.keys())[i]]:
                        value = input_dict.get(key)
                        if value is None:
                            logger.warning(f"EXCLUSION: Missing or invalid value for {key}", input_dict)
                            return None

                        if isinstance(value, str):
                            try:
                                value = Decimal(''.join(c for c in value if c.isdigit() or c == '.')) if value else Decimal(0)
                            except InvalidOperation as e:
                                logger.warning(f"EXCLUSION: {key} not a valid decimal: {e}. Input dict: {input_dict}, {tx_hash}")
                                return None
                        elif isinstance(value, int):
                            value = Decimal(value)
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


def get_first_src20_deploy_lim_max(db, tick, processed_in_block):
    if tick in DEPLOY_CACHE:
        return DEPLOY_CACHE[tick]["lim"], DEPLOY_CACHE[tick]["max"]
    processed_blocks = {f"{item['tick']}-{item['op']}": item for item in processed_in_block}

    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            SELECT
                lim, max
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
            lim, max_value = result
            DEPLOY_CACHE[tick] = {"lim": lim, "max": max_value}
            return lim, max_value
        else:
            lim, max_value = get_first_src20_deploy_lim_max_in_block(processed_blocks, tick)
            if lim is None or max_value is None:
                return 0, 0
            DEPLOY_CACHE[tick] = {"lim": lim, "max": max_value}
            return lim, max_value


def get_first_src20_deploy_lim_max_in_block(processed_blocks, tick):
    key = f"{tick}-DEPLOY"
    if key in processed_blocks:
        item = processed_blocks[key]
        return item["lim"], item["max"]
    return None, None


def get_total_minted_from_db(db, tick):
    ''' this may be a relatively heavy operation compared to pulling from 
    the balances table it's  mostly for debug but perhaps also for a 
    x block comparison/validation of the balances table. '''
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


def get_running_mint_total(db, processed_in_block, tick):
    total_minted = 0
    if len(processed_in_block) > 0:
        for item in reversed(processed_in_block):
            if item["tick"] == tick and item["op"] == 'MINT' and "total_minted" in item:
                total_minted = item["total_minted"]
                break
    if total_minted == 0:
        total_minted = get_total_minted_from_db(db, tick)

    return Decimal(total_minted)


def get_running_user_balance(db, tick, tick_hash, creator, processed_in_block):
    total_balance = 0
    if len(processed_in_block) > 0:
        for item in reversed(processed_in_block):
            if item["creator"] == creator and item["tick"] == tick and item["tick_hash"] == tick_hash and "total_balance" in item:
                total_balance = item["total_balance"]
                break
    if total_balance == 0:
        total_balance, _, _ = get_total_user_balance_from_db(db, tick, tick_hash, creator)
    return Decimal(total_balance)


def get_total_user_balance_from_db(db, tick, tick_hash, address):
    ''' another heavy operation to be running on every creator/tick pair
        this is for validation, the speedy version should pull from the balances table 
        keep in mind balance table is not committed on each transaction '''
    total_balance = Decimal('0')
    highest_block_index = 0
    q_block_time_unix = None
    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
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
                AND ((destination = %s OR creator = %s) AND (op = 'TRANSFER' OR op = 'MINT'))
            ORDER BY block_index
                """, (tick, tick_hash, address, address))
        results = src20_cursor.fetchall()
        for result in results:
            q_amt = Decimal(result[0])
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
    return total_balance, highest_block_index, q_block_time_unix


def insert_into_src20_table(db, table_name, src20_dict):
    if table_name == SRC20_VALID_TABLE and src20_dict.get("op") == "MINT":
        TOTAL_MINTED_CACHE[src20_dict.get("tick")] += src20_dict.get("amt")

    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            INSERT INTO {table_name} (
                tx_hash,
                tx_index,
                amt,
                block_index,
                creator,
                deci,
                lim,
                max,
                op,
                p,
                tick,
                destination,
                block_time,
                status,
                tick_hash
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s
            )
            ON DUPLICATE KEY UPDATE
                tx_index = VALUES(tx_index),
                amt = VALUES(amt),
                block_index = VALUES(block_index),
                creator = VALUES(creator),
                deci = VALUES(deci),
                lim = VALUES(lim),
                max = VALUES(max),
                op = VALUES(op),
                p = VALUES(p),
                tick = VALUES(tick),
                destination = VALUES(destination),
                block_time = VALUES(block_time),
                status = VALUES(status),
                tick_hash = VALUES(tick_hash)
        """, (
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
            src20_dict.get("block_time"),
            src20_dict.get("status"),
            src20_dict.get("tick_hash")
        ))


def is_number(s):
    '''
    Check if the input string is a valid number.

    Args:
        s (str): The input string to be checked.

    Returns:
        bool: True if the input string is a valid number, False otherwise.
    '''
    pattern = r'^[-+]?[0-9]*\.?[0-9]+$'
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

    return hashlib.sha3_256(tick.encode()).hexdigest()


def process_src20_values(src20_dict):
    ''' 
    This function processes the values in the src20_dict dictionary and performs the following operations:
    - Validates all numbers in the string and invalidates those with commas, etc.
    - Converts certain keys to uppercase.
    - Converts 'max' and 'lim' values to integers.
    - Converts 'amt' values to Decimal.
    - updates or adds the 'status' key regarding any invalidations

    Args:
        src20_dict (dict): A dictionary containing the src20 key value pairs.

    Returns:
        dict: The updated src20_dict dictionary with processed values.
    '''
    updated_dict = {}
    for key, value in src20_dict.items():
        if value == '':
            updated_dict[key] = None
        elif key in ['tick']:
            updated_dict['tick'] = value.lower()
            updated_dict['tick_hash'] = create_tick_hash(value)
        elif key in ['p', 'op']:
            updated_dict[key] = value.upper()
        elif key in ['max', 'lim']:
            if not is_number(value):
                updated_dict[key] = None
                if 'status' in updated_dict:
                    updated_dict['status'] += f', NN: {key} not NUM'
                else:
                    updated_dict['status'] = f'NN: {key} not NUM'
            else:
                updated_dict[key] = int(Decimal(value))
        elif key == 'amt':
            if not is_number(value):
                updated_dict[key] = None
                if 'status' in updated_dict:
                    updated_dict['status'] += f', NN: {key} not NUM'
                else:
                    updated_dict['status'] = f'NN: {key} not NUM'
            else:
                updated_dict[key] = Decimal(value)
    src20_dict.update(updated_dict)
    return src20_dict

    
def insert_into_src20_tables(db, src20_dict, source, tx_hash, tx_index, block_index, block_time, destination, valid_src20_in_block):
    ''' this is to process all SRC-20 Tokens that pass check_format '''
    
    src20_dict['creator'] = source
    src20_dict['tx_hash'] = tx_hash
    src20_dict['tx_index'] = tx_index
    src20_dict['block_index'] = block_index
    src20_dict['block_time'] = block_time
    src20_dict['destination'] = destination
    src20_dict.setdefault('dec', '18')

    try:
        src20_dict = process_src20_values(src20_dict) # this does normalization of the tick patterns

        if src20_dict['op'] == 'DEPLOY' and src20_dict['tick_hash']:
            if (
                src20_dict['tick'] and
                (isinstance(src20_dict['max'], int) or isinstance(src20_dict['max'], str)) and
                (isinstance(src20_dict['lim'], int) or isinstance(src20_dict['lim'], str)) and
                src20_dict['max'] > 0 and
                src20_dict['lim'] > 0
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)

                if not deploy_lim and not deploy_max:
                    insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                    valid_src20_in_block.append(src20_dict)
                else:
                    logger.info(f"Invalid {src20_dict['tick']} DEPLOY - prior DEPLOY exists")
                    src20_dict['status'] = f'DE: prior {src20_dict["tick"]} DEPLOY exists'
            else:
                logger.info(f"Invalid {src20_dict['tick']} DEPLOY -  max or lim is not an integer or not >0")
                src20_dict['status'] = f'NE: max or lim not INT or not >0'

        elif src20_dict['op'] == 'MINT' and src20_dict['tick_hash']:
            if ( 
                src20_dict['tick'] and src20_dict['amt'] and 
                Decimal(src20_dict['amt']) > Decimal('0')
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)
                
                if deploy_lim and deploy_max:
                    deploy_lim = int(min(deploy_lim, deploy_max)) # deploy_lim cannot be > deploy_max
                    total_minted = int(get_running_mint_total(db, valid_src20_in_block, src20_dict['tick']))
                    # TODO: Possibly commit to balances table in a separate db connection to avoid the full
                    # query on the SRC20Valid Table each time. Will need to rollback changes on balances if block does not commit
                    total_balance = get_running_user_balance(db, src20_dict['tick'], src20_dict['tick_hash'], src20_dict['creator'], valid_src20_in_block)
                    mint_available = Decimal(deploy_max) - Decimal(total_minted)
     
                    if total_minted >= deploy_max:
                        logger.info(f" {src20_dict['tick']} OVERMINT: minted {total_minted} > max {deploy_max}")
                        src20_dict['status'] = f'OM: Over Max: {total_minted} >= {deploy_max}'
                    else:
                        if src20_dict['amt'] > deploy_lim:
                            src20_dict['status'] = f'OML: FROM {src20_dict["amt"]} TO {deploy_lim}'
                            src20_dict['amt'] = deploy_lim
                            logger.info(f"Reducing {src20_dict['tick']} OVERMINT: LIMIT - amt {src20_dict['amt']} > deploy_lim {deploy_lim}")

                        if src20_dict['amt'] > mint_available:
                            src20_dict['status'] = f'OMA:  FROM: {src20_dict["amt"]} TO: {mint_available}'
                            src20_dict['amt'] = mint_available
                            logger.info(f"Reducing {src20_dict['tick']} OVERMINT: minted {total_minted} + amt {src20_dict['amt']} > max {deploy_max} - remain {mint_available} ")

                        insert_into_src20_table(db, SRC20_TABLE, src20_dict)
                        running_total_mint = int(total_minted) + int(src20_dict['amt'])
                        running_user_balance = Decimal(total_balance) + Decimal(src20_dict['amt'])
                        src20_dict['status'] = f'OK: {running_total_mint} of {deploy_max}'
                        src20_dict['total_minted'] = running_total_mint
                        src20_dict['total_balance'] = running_user_balance
                        insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                        valid_src20_in_block.append(src20_dict)
                        return
                else:
                    logger.info(f"Invalid {src20_dict['tick']} MINT - no deploy_lim {deploy_lim} and deploy_max {deploy_max}")
                    src20_dict['status'] = f'NM: No Deploy {src20_dict["tick"]}'
            else:
                logger.info(f"Invalid {src20_dict['tick']} MINT - amt is not a number or not >0")

        # Any transfer over the users balance at the time of transfer is considered invalid and will not impact either users balance
        # if wallet x has 1 KEVIN token and attempts to transfer 10000 KEVIN tokens to address y the entire transaction is invalid
        elif src20_dict['op'] == 'TRANSFER' and src20_dict['tick_hash']:  
            if ( 
                src20_dict['tick'] and src20_dict['amt'] and 
                Decimal(src20_dict['amt']) > Decimal('0')
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)
                if deploy_lim and deploy_max:
                    if deploy_lim is not None:

                        total_balance = get_running_user_balance(db, src20_dict['tick'], src20_dict['tick_hash'], src20_dict['creator'], valid_src20_in_block)

                        if Decimal(total_balance) > Decimal('0') and Decimal(total_balance) >= Decimal(src20_dict['amt']):
                            insert_into_src20_table(db, SRC20_TABLE, src20_dict)
                            running_user_balance = Decimal(total_balance) - Decimal(src20_dict['amt'])
                            src20_dict['total_balance'] = running_user_balance
                            src20_dict['status'] = f'New Balance: {running_user_balance}'
                            insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                            valid_src20_in_block.append(src20_dict)
                            return
                        else:
                            logger.info(f"Invalid {src20_dict['tick']} TRANSFER - total_balance {total_balance} < xfer amt {src20_dict['amt']}")
                            src20_dict['status'] = f'BB: TRANSFER over user balance'
                    else:
                        logger.info(f"Invalid {src20_dict['tick']} TRANSFER - no balance for {src20_dict['creator']}")
                        src20_dict['status'] = f'NB: TRANSFER no user balance'

        insert_into_src20_table(db, SRC20_TABLE, src20_dict)
    except Exception as e:
        logger.error(f"Error inserting data into src tables: {e}")
        raise e
    
    
def update_src20_balances(db, block_index, block_time, valid_src20_in_block):
    balance_updates = []

    for src20_dict in valid_src20_in_block:
        try:
            if src20_dict['op'] == 'MINT':
                balance_dict = next((item for item in balance_updates if 
                                     item['tick'] == src20_dict['tick'] and 
                                     item['tick_hash'] == src20_dict['tick_hash'] and 
                                     item['creator'] == src20_dict['destination']), None)
                if balance_dict is None:
                    balance_dict = {
                        'tick': src20_dict['tick'],
                        'tick_hash': src20_dict['tick_hash'],
                        'creator': src20_dict['destination'],
                        'credit': Decimal(src20_dict['amt']),
                        'debit': Decimal(0)
                    }
                    balance_updates.append(balance_dict)
                else:
                    balance_dict['credit'] += Decimal(src20_dict['amt'])

            elif src20_dict['op'] == 'TRANSFER':
                # Debit from creator
                balance_dict = next((item for item in balance_updates if 
                                     item['tick'] == src20_dict['tick'] and 
                                     item['tick_hash'] == src20_dict['tick_hash'] and 
                                     item['creator'] == src20_dict['creator']), None)
                if balance_dict is None:
                    balance_dict = {
                        'tick': src20_dict['tick'],
                        'tick_hash': src20_dict['tick_hash'],
                        'creator': src20_dict['creator'],
                        'debit': Decimal(src20_dict['amt']),
                        'credit': Decimal(0)
                    }
                    balance_updates.append(balance_dict)
                else:
                    balance_dict['debit'] += Decimal(src20_dict['amt'])

                # Credit to destination
                balance_dict = next((item for item in balance_updates if 
                                     item['tick'] == src20_dict['tick'] and 
                                     item['tick_hash'] == src20_dict['tick_hash'] and 
                                     item['creator'] == src20_dict['destination']), None)
                if balance_dict is None:
                    balance_dict = {
                        'tick': src20_dict['tick'],
                        'tick_hash': src20_dict['tick_hash'],
                        'creator': src20_dict['destination'],
                        'credit': Decimal(src20_dict['amt']),
                        'debit': Decimal(0)
                    }
                    balance_updates.append(balance_dict)
                else:
                    balance_dict['credit'] += Decimal(src20_dict['amt'])

        except Exception as e:
            logger.error(f"Error updating SRC20 balances: {e}")
            raise e
    
    if balance_updates:
        update_balances(db, balance_updates, block_index, block_time)
    return


def update_balances(db, balance_updates, block_index, block_time):
    ''' update the balances table with the balance_updates list '''
    cursor = db.cursor()

    for balance_dict in balance_updates:
        try:
            net_change = balance_dict.get('credit', 0) - balance_dict.get('debit', 0)
            id_field = balance_dict['tick'] + '_' + balance_dict['creator']

            cursor.execute("""
                INSERT INTO balances
                (id, address, tick, amt, last_update, block_time, p, tick_hash)
                VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s)
                ON DUPLICATE KEY UPDATE
                    amt = amt + VALUES(amt),
                    last_update = VALUES(last_update)
            """, (id_field, balance_dict['creator'], balance_dict['tick'], net_change, block_index, block_time, 'SRC-20', balance_dict['tick_hash']))
        
        except Exception as e:
            logger.error("Error updating balances table:", e)
            raise e

    cursor.close()
    return
