from decimal import Decimal, InvalidOperation
import json
import logging
from config import TICK_PATTERN_LIST, SRC20_TABLE, SRC20_VALID_TABLE, SRC20_BALANCES_TABLE
import src.log as log

logger = logging.getLogger(__name__)
log.set_logger(logger)  # set root logger


def build_src20_svg_string(cursor, src_20_dict):
    from src721 import convert_to_dict
    src_20_dict = convert_to_dict(src_20_dict)
    background_base64, font_size, text_color = get_srcbackground_data(cursor, src_20_dict.get('tick'))
    svg_image_data = generate_srcbackground_svg(src_20_dict, background_base64, font_size, text_color)
    return svg_image_data


# query the srcbackground mysql table for these columns tick, base64, font_size, text_color, unicode, p
def get_srcbackground_data(cursor, tick):
    query = """
        SELECT
            base64,
            CASE WHEN font_size IS NULL OR font_size = '' THEN '30px' ELSE font_size END AS font_size,
            CASE WHEN text_color IS NULL OR text_color = '' THEN 'white' ELSE text_color END AS text_color
        FROM
            srcbackground
        WHERE
            UPPER(tick) = UPPER(%s)
            AND UPPER(p) = UPPER(%s)
    """
    cursor.execute(query, (tick.upper(), "SRC-20")) # NOTE: even SRC-721 placeholder has a 'SRC-20' p value for now
    result = cursor.fetchone()
    if result:
        base64, font_size, text_color = result
        return base64, font_size, text_color
    else:
        return None, None, None


def generate_srcbackground_svg(input_dict, base64, font_size, text_color):
    # remove the s field so we don't add it to the image - this is sale price data
    s_val = input_dict.get("s", None)
    input_dict.pop("s", None)
    
    sorted_keys = sorted(input_dict.keys(), key=sort_keys)
    pretty_json = json.dumps({k: input_dict[k] for k in sorted_keys}, indent=1, separators=(',', ': '), sort_keys=False, ensure_ascii=False, default=str)

    if base64 is not None:
        svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><foreignObject font-size="{font_size}" width="100%" height="100%"><p xmlns="http://www.w3.org/1999/xhtml" style="background-image: url(data:{base64});color:{text_color};padding:20px;margin:0px;width:1000px;height:1000px;"><pre>{pretty_json}</pre></p></foreignObject></svg>"""
    else:
        svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><foreignObject font-size="30px" width="100%" height="100%"><p xmlns="http://www.w3.org/1999/xhtml" style="background: rgb(149,56,182); background: linear-gradient(138deg, rgba(149,56,182,1) 23%, rgba(0,56,255,1) 100%);padding:20px;margin:0px;width:1000px;height:1000px;"><pre>{pretty_json}</pre></p></foreignObject></svg>"""
    img_data = svg_output.encode('utf-8')

    input_dict["s"] = s_val

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
    try:
        # if the p value of is not SRC-20 return 
        # string to dict in '72fa9dacfd96d5ac604349a7e7435d484a2dac664c32cd60fcf49eb4bdcb52f4'
        if input_string is not None:
            input_dict = json.loads(input_string)
            if input_dict.get("p", "").upper() != "SRC-20" or input_dict.get("p") is None:
                # '50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1'
                return None
        if isinstance(input_string, dict):
            input_string = json.dumps(input_string) # FIXME: chaos with all the data types, need to normalize higher up
        if isinstance(input_string, bytes):
            input_string = input_string.decode('utf-8')
        start_index = input_string.find('{')
        end_index = input_string.rfind('}') + 1
        input_string = input_string[start_index:end_index]
        input_dict = json.loads(input_string)
        if input_dict.get("p") == "src-721":
            return input_dict

        if input_dict.get("p") == "src-20":
            ''' If the keys and values in the  string does not meet the requirements for src-20 we do not return or save the data in the Stamptable '''
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
            lim, max = result
            return lim, max
        else:
            return get_first_src20_deploy_lim_max_in_block(processed_in_block, tick)


def get_first_src20_deploy_lim_max_in_block(processed_in_block, tick):
    if len(processed_in_block) > 0:
        for item in processed_in_block:
            if item["tick"] == tick and item["op"] == 'DEPLOY':
                return item["lim"], item["max"]
    return None, None


def get_total_minted(db, tick, processed_in_block):
    total_minted_db = get_total_minted_from_db(db, tick)
    total_minted_block = get_total_minted_from_block(processed_in_block, tick)
    return total_minted_db + total_minted_block


def get_total_minted_from_db(db, tick):
    total_minted = 0
    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            SELECT
                SUM(amt) AS total_minted
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND op = 'MINT'
        """, (tick,))
        result = src20_cursor.fetchone()

        if result and result[0] is not None:
            total_minted = result[0]
        return total_minted


def get_total_minted_from_block(processed_in_block, tick):
    total_minted = 0
    if len(processed_in_block) > 0:
        for item in processed_in_block:
            if item["tick"] == tick:
                if item["op"] == 'MINT':
                    total_minted += item["amt"]
    return total_minted


def get_total_balance(db, tick, source, processed_in_block):
    total_balance_db = get_total_balance_from_db(db, tick, source)
    total_balance_block = get_total_balance_from_block(processed_in_block, tick, source)
    return total_balance_db + total_balance_block


def get_total_balance_from_db(db, tick, source):
    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            SELECT
                SUM(amt) AS total_balance
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND ((source = %s AND op = 'MINT') OR (destination = %s AND op = 'TRANSFER'))
        """, (tick, source, source))
        result = src20_cursor.fetchone()
        if result and result[0] is not None:
            total_balance = Decimal(result[0])
            return total_balance
        else:
            return Decimal('0')


def get_total_balance_from_block(processed_in_block, tick, source):
    total_balance = Decimal('0')
    if len(processed_in_block) > 0:
        for item in processed_in_block:
            if item["tick"] == tick:
                if item["op"] == 'MINT' and item["source"] == source:
                    total_balance += Decimal(item["amt"])
                elif item["op"] == 'TRANSFER' and item["destination"] == source:
                    total_balance += Decimal(item["amt"])
    return total_balance


def insert_into_src20_table(db, table_name, src20_dict):
    with db.cursor() as src20_cursor:
        src20_cursor.execute(f"""
            INSERT IGNORE INTO {table_name} (
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
                block_time
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
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
            src20_dict.get("block_time")
        ))

def is_number(s):
    ''' commas or invalid chars in the string are not allowed '''
    # '1bca62a4309e0c02c1a7feff053a1071b2c63c99aad237bf6b69cc0f01a784f1' is a tx with a comma in amt which will be invalid
    try:
        Decimal(s)
        return True
    except InvalidOperation:
        return False
    
def insert_into_src20_tables(db, src20_dict, source, tx_hash, tx_index, block_index, block_time, destination, valid_src20_in_block):
    ''' this is to process all SRC-20 Tokens that pass check_format '''
    
    src20_dict['creator'] = source
    src20_dict['tx_hash'] = tx_hash
    src20_dict['tx_index'] = tx_index
    src20_dict['block_index'] = block_index
    src20_dict['block_time'] = block_time
    src20_dict['destination'] = destination
    src20_dict.setdefault('dec', '18')

    for key, value in src20_dict.items():
        if value == '':
            src20_dict[key] = None
        elif key in ['p', 'tick', 'op']:
            src20_dict[key] = value.upper()
        elif key in ['max', 'lim']:
            if not is_number(value):
                return # possible we want to save in SRC20Table - will need to change row type to varchar
                # string float to int for  max (decimal) value in '18b808259a56004da679161145efeb223b06ea19486babd480d4885d942dd450'
            src20_dict[key] = int(float(value))
        elif key == 'amt':
            if not is_number(value):
                return
            src20_dict[key] = Decimal(value)
    try:
        insert_into_src20_table(db, SRC20_TABLE, src20_dict)

        if src20_dict['op'] == 'DEPLOY':
            if (
                src20_dict['tick'] and
                isinstance(src20_dict['max'], int) and
                isinstance(src20_dict['lim'], int) and
                src20_dict['max'] > 0 and
                src20_dict['lim'] > 0
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)

                if not deploy_lim and not deploy_max:
                    insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                    valid_src20_in_block.append(src20_dict)
                    return
                else:
                    logger.info(f"Invalid {src20_dict['tick']} DEPLOY - prior DEPLOY exists")
                    return
            else:
                logger.info(f"Invalid {src20_dict['tick']} DEPLOY -  max or lim is not an integer or >0")
                return

        elif src20_dict['op'] == 'MINT':
            if ( 
                src20_dict['tick'] and src20_dict['amt'] and 
                Decimal(src20_dict['amt']) > Decimal('0')
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)
                if deploy_lim and deploy_max:
                    
                    src20_dict['amt'] = Decimal(deploy_lim) if src20_dict['amt'] > Decimal(deploy_lim) else src20_dict['amt']
                    total_deployed = get_total_minted(db, src20_dict['tick'], valid_src20_in_block)

                    if Decimal(total_deployed) + Decimal(src20_dict['amt']) > Decimal(deploy_max):
                        src20_dict['amt'] = Decimal(deploy_max) - Decimal(total_deployed)
                        logger.info(f"Reducing {src20_dict['tick']} OVERMINT - total deployed {total_deployed} + amt {src20_dict['amt']} > deploy_max {deploy_max}")
                    elif total_deployed > deploy_max:
                        logger.info(f"Invalid {src20_dict['tick']} OVERMINTMINT - total deployed {total_deployed} > deploy_max {deploy_max}")
                        return
                    
                    insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                    valid_src20_in_block.append(src20_dict)
                    return
                else:
                    logger.info(f"Invalid {src20_dict['tick']} MINT - no valid DEPLOY exists")
                    return

        # Any transfer over the users balance at the time of transfer is considered invalid and will not impact either users balance
        # if wallet x has 1 KEVIN token and attempts to transfer 10000 KEVIN tokens to address y the entire transaction is invalid
        elif src20_dict['op'] == 'TRANSFER':  
            if ( 
                src20_dict['tick'] and src20_dict['amt'] and 
                Decimal(src20_dict['amt']) > Decimal('0')
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)
                if deploy_lim and deploy_max: # found a valid deploy transfer is ok if balance is > amt
                    if deploy_lim is not None and Decimal(src20_dict['amt']) > Decimal('0'):

                        total_balance = get_total_balance(db, src20_dict['tick'], src20_dict['creator'], valid_src20_in_block)

                        if Decimal(total_balance) > Decimal('0') and Decimal(total_balance) >= Decimal(src20_dict['amt']):
                            insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                            valid_src20_in_block.append(src20_dict)
                            return
                        else:
                            logger.info(f"Invalid {src20_dict['tick']} TRANSFER - total_balance {total_balance} < xfer amt {src20_dict['amt']}")
                            return
                    else:
                        logger.info(f"Invalid {src20_dict['tick']} TRANSFER - no balance for {src20_dict['creator']}")
                        return
        
    except Exception as e:
        logger.error(f"Error inserting data into src tables: {e}")
        raise e
    
    
def update_src20_balances(db, block_index, block_time, valid_src20_in_block):
    balance_updates = []

    for src20_dict in valid_src20_in_block:
        try:
            if src20_dict['op'] == 'MINT':
                balance_dict = next((item for item in balance_updates if item['tick'] == src20_dict['tick'] and item['creator'] == src20_dict['creator']), None)
                if balance_dict is None:
                    balance_dict = {
                        'tick': src20_dict['tick'],
                        'creator': src20_dict['creator'],
                        'credit': Decimal(src20_dict['amt']),
                        'debit': Decimal(0)
                    }
                    balance_updates.append(balance_dict)
                else:
                    balance_dict['credit'] += Decimal(src20_dict['amt'])

            elif src20_dict['op'] == 'TRANSFER':
                # Debit from creator
                balance_dict = next((item for item in balance_updates if item['tick'] == src20_dict['tick'] and item['creator'] == src20_dict['creator']), None)
                if balance_dict is None:
                    balance_dict = {
                        'tick': src20_dict['tick'],
                        'creator': src20_dict['creator'],
                        'debit': Decimal(src20_dict['amt']),
                        'credit': Decimal(0)
                    }
                    balance_updates.append(balance_dict)
                else:
                    balance_dict['debit'] += Decimal(src20_dict['amt'])

                # Credit to destination
                balance_dict = next((item for item in balance_updates if item['tick'] == src20_dict['tick'] and item['creator'] == src20_dict['destination']), None)
                if balance_dict is None:
                    balance_dict = {
                        'tick': src20_dict['tick'],
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
                (id, address, tick, amt, last_update, block_time, p)
                VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s)
                ON DUPLICATE KEY UPDATE
                    amt = amt + VALUES(amt),
                    last_update = VALUES(last_update)
            """, (id_field, balance_dict['creator'], balance_dict['tick'], net_change, block_index, block_time, 'SRC-20'))
        
        except Exception as e:
            logger.error("Error updating balances table:", e)
            raise e

    cursor.close()
    return