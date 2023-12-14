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
    input_dict.pop("s", None)
    
    sorted_keys = sorted(input_dict.keys(), key=sort_keys)
    pretty_json = json.dumps({k: input_dict[k] for k in sorted_keys}, indent=1, separators=(',', ': '), sort_keys=False, ensure_ascii=False, default=str)

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
    try:
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
                return False

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
                            return False
            return input_dict

    except json.JSONDecodeError:
        return None

    return None


def get_first_src20_deploy_lim_max(db, tick, processed_in_block):
    with db.cursor() as src20_cursor:
        src20_cursor.execute("""
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
    with db.cursor() as src20_cursor:
        src20_cursor.execute("""
            SELECT
                SUM(amt) AS total_minted
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND op = 'MINT'
        """, (tick,))
        result = src20_cursor.fetchone()

        if result:
            total_minted = result[0]
            return total_minted
        else:
            return 0


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
        src20_cursor.execute("""
            SELECT
                SUM(amt) AS total_balance
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND ((source = %s AND op = 'MINT') OR (destination = %s AND op = 'TRANSFER'))
        """, tick, source, source)
        result = src20_cursor.fetchone()
        if result:
            total_balance = result[0]
            return total_balance
        else:
            return 0


def get_total_balance_from_block(processed_in_block, tick, source):
    total_balance = 0
    if len(processed_in_block) > 0:
        for item in processed_in_block:
            if item["tick"] == tick:
                if item["op"] == 'MINT' and item["source"] == source:
                    total_balance += item["amt"]
                elif item["op"] == 'TRANSFER' and item["destination"] == source:
                    total_balance += item["amt"]
    return total_balance


def insert_into_src20_table(db, table_name, src20_dict):
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
                destination
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                amt = VALUES(amt),
                block_index = VALUES(block_index),
                creator = VALUES(creator),
                deci = VALUES(deci),
                lim = VALUES(lim),
                max = VALUES(max),
                op = VALUES(op),
                p = VALUES(p),
                tick = VALUES(tick),
                destination = VALUES(destination)
        """, (
            src20_dict["tx_hash"],
            src20_dict["amt"],
            src20_dict["block_index"],
            src20_dict["creator"],
            src20_dict["dec"],
            src20_dict["lim"],
            src20_dict["max"],
            src20_dict["op"],
            src20_dict["p"],
            src20_dict["tick"],
            src20_dict["destination"]
        ))

    
def insert_into_src20_tables(db, src20_dict, source, tx_hash, tx_index, block_index, destination, valid_src20_in_block):
    ''' this is to process all SRC-20 Tokens that pass check_format '''
    
    src20_dict['creator'] = source
    src20_dict['tx_hash'] = tx_hash
    src20_dict['tx_index'] = tx_index
    src20_dict['block_index'] = block_index
    src20_dict['destination'] = destination
    src20_dict.setdefault('dec', '18')

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

                if deploy_lim and deploy_max:
                    insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                    valid_src20_in_block.append(src20_dict)
                    return
                else:
                    logger.debug(f"Invalid {src20_dict['tick']} DEPLOY - prior DEPLOY exists")
                    return
            else:
                logger.debug(f"Invalid {src20_dict['tick']} DEPLOY -  max or lim is not an integer or >0")
                return

        elif src20_dict['op'] == 'MINT':
            if ( 
                src20_dict['tick'] and src20_dict['amt'] and 
                src20_dict['amt'] > 0
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)
                if deploy_lim and deploy_max:
                    
                    src20_dict['amt'] = deploy_lim if src20_dict['amt'] > deploy_lim else src20_dict['amt']
                    total_deployed = get_total_minted(db, src20_dict['tick'], valid_src20_in_block)

                    if total_deployed > deploy_max:
                        logger.debug(f"Invalid {src20_dict['tick']} MINT - total deployed {total_deployed} > deploy_max {deploy_max}")
                        return
                    elif total_deployed + src20_dict['amt'] > deploy_max:
                        src20_dict['amt'] = deploy_max - total_deployed
                        logger.debug(f"Reducing {src20_dict['tick']} MINT - total deployed {total_deployed} + amt {src20_dict['atm']} > deploy_max {deploy_max}")

                    insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                    valid_src20_in_block.append(src20_dict)
                    return
                else:
                    logger.debug(f"Invalid {src20_dict['tick']} MINT - no valid DEPLOY exists")
                    return

        elif src20_dict['op'] == 'TRANSFER':  
            if ( 
                src20_dict['tick'] and src20_dict['amt'] and 
                src20_dict['amt'] > 0
            ):
                deploy_lim, deploy_max = get_first_src20_deploy_lim_max(db, src20_dict['tick'], valid_src20_in_block)
                if deploy_lim and deploy_max: # we found a valid deploy
                    if deploy_lim is not None and src20_dict['amt'] > 0:

                        total_balance = get_total_balance(db, src20_dict['tick'], src20_dict['creator'], valid_src20_in_block)

                        if total_balance > 0 and total_balance >= src20_dict['amt']:
                            insert_into_src20_table(db, SRC20_VALID_TABLE, src20_dict)
                            valid_src20_in_block.append(src20_dict)
                            return
                        else:
                            logger.debug(f"Invalid {src20_dict['tick']} TRANSFER - total_balance {total_balance} < xfer amt {src20_dict['amt']}")
                            return
                    else:
                        logger.debug(f"Invalid {src20_dict['tick']} TRANSFER - no balance for {src20_dict['creator']}")
                        return
        
        # TODO: Update balance table

    except Exception as e:
        print(f"Error inserting data into src tables: {e}")
        return None
    