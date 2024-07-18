import decimal
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, TypeVar, cast

import pymysql as mysql

import config
import index_core.exceptions as exceptions
import index_core.log as log
from config import (
    BLOCK_FIELDS_POSITION,
    BLOCKS_TABLE,
    SRC20_TABLE,
    SRC20_VALID_TABLE,
    SRC101_OWNERS_TABLE,
    SRC101_PRICE_TABLE,
    SRC101_RECIPIENTS_TABLE,
    SRC101_TABLE,
    SRC101_VALID_TABLE,
    SRC_BACKGROUND_TABLE,
    STAMP_TABLE,
    TRANSACTIONS_TABLE,
)
from index_core.exceptions import BlockAlreadyExistsError, BlockUpdateError, DatabaseInsertError

logger = logging.getLogger(__name__)
log.set_logger(logger)

D = decimal.Decimal
F = TypeVar("F", bound=Callable[..., Any])


class CacheMixin:
    block_cache: Dict[int, Any] = {}
    deploy_cache: Dict[str, Any] = {}
    cached_stamp: Dict[str, int] = {}
    cache: Dict[str, bool] = {}


def initialize(db):
    """initialize data, create and populate the database."""
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT MIN(block_index)
        FROM blocks
    """
    )
    block_index = cursor.fetchone()[0]

    if block_index is not None and block_index != config.BLOCK_FIRST:
        raise exceptions.DatabaseError("First block in database is not block " "{}.".format(config.BLOCK_FIRST))

    cursor.execute("""DELETE FROM blocks WHERE block_index < %s""", (config.BLOCK_FIRST,))

    cursor.execute("""DELETE FROM transactions WHERE block_index < %s""", (config.BLOCK_FIRST,))
    cursor.close()


TOTAL_MINTED_CACHE: dict[str, int] = {}


def reset_all_caches():
    """
    Clears all function-associated caches within the module.
    This includes deploy_cache, block_cache, and cached_stamp.
    """
    cache_attributes = [
        (get_src20_deploy, "deploy_cache"),
        (is_prev_block_parsed, "block_cache"),
        (get_next_stamp_number, "cached_stamp"),
        (check_reissue, "cache"),
    ]

    for func, attr in cache_attributes:
        if hasattr(func, attr):
            setattr(func, attr, {})

    global TOTAL_MINTED_CACHE
    TOTAL_MINTED_CACHE = {}


def update_parsed_block(db, block_index):
    """
    Update the 'indexed' flag of a block in the database.

    Args:
        db (database connection): The database connection object.
        block_index (int): The index of the block to update.

    Returns:
        None
    """
    cursor = db.cursor()
    cursor.execute(
        """
                    UPDATE blocks SET indexed = 1
                    WHERE block_index = %s
                    """,
        (block_index,),
    )
    db.commit()
    cursor.close()


def is_prev_block_parsed(db, block_index):
    """
    Check if the previous block has been parsed and indexed.

    Args:
        db (DatabaseConnection): The database connection object.
        block_index (int): The index of the current block.

    Returns:
        bool: True if the previous block has been parsed, False otherwise.
    """
    func = cast(CacheMixin, is_prev_block_parsed)
    if not hasattr(func, "block_cache"):
        func.block_cache = {}

    if block_index - 1 in func.block_cache:
        block = func.block_cache[block_index - 1]
    else:
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT * FROM blocks
            WHERE block_index = %s
            """,
            (block_index - 1,),
        )
        block = cursor.fetchone()
        cursor.close()
        func.block_cache[block_index - 1] = block

    if block is not None and block[BLOCK_FIELDS_POSITION["indexed"]] == 1:
        return True
    else:
        purge_block_db(db, block_index - 1)
        rebuild_balances(db)
        return False


def insert_into_src20_tables(db, processed_src20_in_block):
    with db.cursor() as src20_cursor:
        for i, src20_dict in enumerate(processed_src20_in_block):
            id = f"{i}_{src20_dict.get('tx_index')}_"
            id += f"{src20_dict.get('tx_hash')}"
            insert_into_src20_table(src20_cursor, SRC20_TABLE, id, src20_dict)
            if src20_dict.get("valid") == 1:
                insert_into_src20_table(src20_cursor, SRC20_VALID_TABLE, id, src20_dict)


def insert_into_src101_tables(db, processed_src101_in_block):
    with db.cursor() as src101_cursor:
        for i, src101_dict in enumerate(processed_src101_in_block):
            id = f"{i}_{src101_dict.get('tx_index')}_"
            id += f"{src101_dict.get('tx_hash')}"
            insert_into_src101_table(src101_cursor, SRC101_TABLE, id, src101_dict)
            if src101_dict.get("valid") == 1:
                insert_into_src101_table(src101_cursor, SRC101_VALID_TABLE, id, src101_dict)
            if src101_dict.get("rec"):
                insert_into_recipients(src101_cursor, SRC101_RECIPIENTS_TABLE, id, src101_dict)


def insert_into_src20_table(cursor, table_name, id, src20_dict):
    block_time = src20_dict.get("block_time")
    if isinstance(block_time, int):
        block_time = datetime.fromtimestamp(block_time, tz=timezone.utc)

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
        "status",
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
        block_time,
        src20_dict.get("tick_hash"),
        src20_dict.get("status"),
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
    """  # nosec

    cursor.execute(query, tuple(column_values))

    return


def insert_into_recipients(cursor, table_name, id, src101_dict):
    block_time = src101_dict.get("block_time")
    if isinstance(block_time, int):
        block_time = datetime.fromtimestamp(block_time, tz=timezone.utc)

    for rec in src101_dict["rec"]:
        _id = id + "_" + rec
        column_names = [
            "id",
            "p",
            "deploy_hash",
            "address",
        ]
        column_values = [
            _id,
            src101_dict.get("p"),
            src101_dict.get("tx_hash"),
            rec,
        ]
        placeholders = ", ".join(["%s"] * len(column_names))

        query = f"""
            INSERT INTO {table_name} ({", ".join(column_names)})
            VALUES ({placeholders})
        """  # nosec
        cursor.execute(query, tuple(column_values))
    return


def insert_into_src101_table(cursor, table_name, id, src101_dict):
    block_time = src101_dict.get("block_time")
    if isinstance(block_time, int):
        block_time = datetime.fromtimestamp(block_time, tz=timezone.utc)

    column_names = [
        "id",
        "tx_hash",
        "tx_index",
        "block_index",
        "p",
        "op",
        "name",
        "tokenid",
        "tokenid_utf8",
        "root",
        "description",
        "tick",
        "wll",
        "tick_hash",
        "deploy_hash",
        "creator",
        "pri",
        "dua",
        "lim",
        "mintstart",
        "mintend",
        "prim",
        "owner",
        "toaddress",
        "destination",
        "destination_nvalue",
        "block_time",
        "status",
    ]
    column_values = [
        id,
        src101_dict.get("tx_hash"),
        src101_dict.get("tx_index"),
        src101_dict.get("block_index"),
        src101_dict.get("p"),
        src101_dict.get("op"),
        src101_dict.get("name"),
        ";".join(src101_dict.get("tokenid")) if type(src101_dict.get("tokenid")) == list else src101_dict.get("tokenid"),
        (
            ";".join(src101_dict.get("tokenid_utf8"))
            if type(src101_dict.get("tokenid_utf8")) == list
            else src101_dict.get("tokenid_utf8")
        ),
        src101_dict.get("root"),
        src101_dict.get("desc"),
        src101_dict.get("tick"),
        src101_dict.get("wll"),
        src101_dict.get("tick_hash"),
        src101_dict.get("deploy_hash"),
        src101_dict.get("creator"),
        src101_dict.get("pri"),
        src101_dict.get("dua"),
        src101_dict.get("lim"),
        src101_dict.get("mintstart"),
        src101_dict.get("mintend"),
        src101_dict.get("prim"),
        src101_dict.get("owner"),
        src101_dict.get("toaddress"),
        src101_dict.get("destination"),
        src101_dict.get("destination_nvalue"),
        block_time,
        src101_dict.get("status"),
    ]

    placeholders = ", ".join(["%s"] * len(column_names))

    query = f"""
        INSERT INTO {table_name} ({", ".join(column_names)})
        VALUES ({placeholders})
    """  # nosec
    cursor.execute(query, tuple(column_values))

    return


def insert_transactions(db, transactions):
    """
    Insert multiple transactions into the database.

    Args:
        db (DatabaseConnection): The database connection object.
        transactions (list): A list of namedtuples representing transactions.

    Returns:
        int: The index of the last inserted transaction.
    """
    # assert transactions.block_index is not None
    try:
        values = []
        for tx in transactions:
            values.append(
                (
                    tx.tx_index,
                    tx.tx_hash,
                    tx.block_index,
                    tx.block_hash,
                    tx.block_time,
                    str(tx.source),
                    str(tx.destination),
                    tx.btc_amount,
                    tx.fee,
                    tx.data,
                    tx.keyburn,
                )
            )
        with db.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO transactions (
                    tx_index,
                    tx_hash,
                    block_index,
                    block_hash,
                    block_time,
                    source,
                    destination,
                    btc_amount,
                    fee,
                    data,
                    keyburn
                ) VALUES (%s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s, %s, %s, %s, %s)""",
                (values),
            )
    except Exception as e:
        raise ValueError(f"Error occurred while inserting transactions: {e}")


def insert_into_stamp_table(db, parsed_stamps: List):
    try:
        with db.cursor() as cursor:
            insert_query = f"""
                INSERT INTO {STAMP_TABLE}(
                    stamp, block_index, cpid, asset_longname,
                    creator, divisible, keyburn, locked,
                    message_index, stamp_base64,
                    stamp_mimetype, stamp_url, supply, block_time,
                    tx_hash, tx_index, ident, src_data,
                    stamp_hash, is_btc_stamp,
                    file_hash, is_valid_base64
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """  # nosec

            data = [
                (
                    parsed.stamp,
                    parsed.block_index,
                    parsed.cpid,
                    parsed.asset_longname,
                    parsed.creator,
                    parsed.divisible,
                    parsed.keyburn,
                    parsed.locked,
                    parsed.message_index,
                    parsed.stamp_base64,
                    parsed.stamp_mimetype,
                    parsed.stamp_url,
                    parsed.supply,
                    parsed.block_time,
                    parsed.tx_hash,
                    parsed.tx_index,
                    parsed.ident,
                    parsed.src_data,
                    parsed.stamp_hash,
                    parsed.is_btc_stamp,
                    parsed.file_hash,
                    parsed.is_valid_base64,
                )
                for parsed in parsed_stamps
            ]

            cursor.executemany(insert_query, data)
    except Exception as e:
        raise ValueError(f"Error occurred while inserting to StampTable: {e}")


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
        """  # nosec
        # NOTE: even SRC-721 placeholder has a 'SRC-20' p value for now
        cursor.execute(query, (tick, "SRC-20"))
        result = cursor.fetchone()
        if result:
            base64, font_size, text_color = result
            return base64, font_size, text_color
        else:
            return None, None, None


def get_existing_balances(cursor):
    query = """
    SELECT id, tick, tick_hash, address, amt, last_update
    FROM balances where p = 'SRC-20'
    """
    cursor.execute(query)
    return [tuple(row) for row in cursor.fetchall()]


def get_src20_valid_list(cursor, block_index=None):
    query = f"""
    SELECT op, creator, destination, tick, tick_hash, amt, block_time, block_index
    FROM {SRC20_VALID_TABLE}
    WHERE (op = 'TRANSFER' OR op = 'MINT') AND amt > 0
    """
    if block_index is not None:
        query += " AND block_index <= %s"
    query += " ORDER by block_index"

    if block_index is not None:
        cursor.execute(query, (block_index,))
    else:
        cursor.execute(query)

    return cursor.fetchall()


def calculate_balances(src20_valid_list):
    all_balances: dict[str, dict[str, Any]] = {}
    for [op, creator, destination, tick, tick_hash, amt, block_time, block_index] in src20_valid_list:
        destination_id = tick + "_" + destination
        destination_amt = D(0) if destination_id not in all_balances else all_balances[destination_id]["amt"]
        destination_amt += amt

        all_balances[destination_id] = {
            "tick": tick,
            "tick_hash": tick_hash,
            "address": destination,
            "amt": destination_amt,
            "last_update": block_index,
            "block_time": block_time,
        }

        if op == "TRANSFER":
            creator_id = tick + "_" + creator
            creator_amt = D(0) if creator_id not in all_balances else all_balances[creator_id]["amt"]
            creator_amt -= amt
            all_balances[creator_id] = {
                "tick": tick,
                "tick_hash": tick_hash,
                "address": creator,
                "amt": creator_amt,
                "last_update": block_index,
                "block_time": block_time,
            }

    return all_balances


def balances_need_update(existing_balances, all_balances):
    return set(existing_balances) != set((key,) + tuple(value.values())[:-1] for key, value in all_balances.items())


def purge_balances(cursor):
    logger.warning("Purging balances table")
    query = "DELETE FROM balances"
    cursor.execute(query)


def insert_balances(cursor, all_balances):
    logger.warning(f"Inserting {len(all_balances)} balances")
    values = [
        (
            key,
            value["tick"],
            value["tick_hash"],
            value["address"],
            value["amt"],
            value["last_update"],
            value["block_time"],
            "SRC-20",
        )
        for key, value in all_balances.items()
    ]

    cursor.executemany(
        """INSERT INTO balances(id, tick, tick_hash, address, amt, last_update, block_time, p)
                          VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
        values,
    )


def rebuild_balances(db, block_index=None):
    cursor = db.cursor()

    try:
        logger.info("Validating Balances Table..")
        db.begin()

        existing_balances = get_existing_balances(cursor)
        src20_valid_list = get_src20_valid_list(cursor, block_index)
        all_balances = calculate_balances(src20_valid_list)

        if not balances_need_update(existing_balances, all_balances):
            logger.info("No changes in balances. Skipping deletion and insertion.")
            return

        purge_balances(cursor)
        insert_balances(cursor, all_balances)

        db.commit()

    except Exception as e:
        db.rollback()
        raise e

    finally:
        cursor.close()


def purge_block_db(db, block_index):
    """Purge transactions from the database. This is for a reorg or
        where transactions were partially committed.

    Args:
        db (Database): The database object.
        block_index (int): The block index from which to start purging.

    Returns:
        None
    """
    reset_all_caches()
    cursor = db.cursor()

    # First, delete from collection_stamps
    logger.warning("Purging collection_stamps from database after block: {}".format(block_index))
    cursor.execute(
        """
        DELETE cs FROM collection_stamps cs
        JOIN StampTableV4 s ON cs.stamp = s.stamp
        WHERE s.block_index >= %s
        """,
        (block_index,),
    )

    tables = [
        SRC20_VALID_TABLE,
        SRC20_TABLE,
        STAMP_TABLE,
        TRANSACTIONS_TABLE,
        BLOCKS_TABLE,
    ]

    for table in tables:
        logger.warning("Purging {} from database after block: {}".format(table, block_index))
        cursor.execute(
            """
            DELETE FROM {}
            WHERE block_index >= %s
            """.format(
                table
            ),
            (block_index,),
        )  # nosec

    db.commit()
    cursor.close()


def get_src20_deploy(db, tick, src20_processed_in_block):
    """
    Retrieves the 'lim', 'max', and 'dec' values for a given 'tick' DEPLOY. The function first attempts to find these values
    from an internal cache. If not found in the cache, it then searches within a provided dictionary of processed blocks.
    As a last resort, it performs a database lookup. The result from any of these sources is cached for future queries.

    Args:
        db: A database connection object used for querying the database if necessary.
        tick (str): The tick value for which 'lim', 'max', and 'dec' values are being retrieved.
        src20_processed_in_block (dict): A dictionary containing processed blocks, used for in-memory lookup before querying the database.

    Returns:
        tuple: A tuple containing the 'lim', 'max', and 'dec' values for the given tick. If the tick is not found in any source,
               returns (None, None, None).

    """
    func = cast(CacheMixin, get_src20_deploy)
    if not hasattr(func, "deploy_cache"):
        func.deploy_cache = {}

    if tick in func.deploy_cache:
        return func.deploy_cache[tick]

    lim, max_value, dec = get_src20_deploy_in_block(src20_processed_in_block, tick)
    if lim is not None:
        func.deploy_cache[tick] = (lim, max_value, dec)
        return lim, max_value, dec

    lim, max_value, dec = get_src20_deploy_in_db(db, tick)
    if lim is not None:
        func.deploy_cache[tick] = (lim, max_value, dec)
    return lim, max_value, dec


def get_src20_deploy_in_block(processed_blocks, tick):
    for item in processed_blocks:
        if item.get("tick") == tick and item.get("op") == "DEPLOY" and item.get("valid") == 1:
            return item.get("lim"), item.get("max"), item.get("dec")
    return None, None, None


def get_src20_deploy_in_db(db, tick):
    with db.cursor() as src20_cursor:
        src20_cursor.execute(
            f"""
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
        """,
            (tick,),
        )  # nosec
        result = src20_cursor.fetchone()
        if result:
            return result
    return None, None, None


def get_total_src20_minted_from_db(db, tick):
    """Retrieve the total amount of tokens minted from the database for a given tick.

    This function performs a database query to fetch the total amount of tokens minted
    for a specific tick.

    Args:
        db (DatabaseConnection): The database connection object.
        tick (int): The tick value for which to retrieve the total minted tokens.

    Returns:
        int: The total amount of tokens minted for the given tick.
    """
    if tick in TOTAL_MINTED_CACHE:
        return TOTAL_MINTED_CACHE[tick]

    total_minted = 0
    with db.cursor() as src20_cursor:
        src20_cursor.execute(
            f"""
            SELECT
                amt
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND op = 'MINT'
        """,
            (tick,),
        )  # nosec
        for row in src20_cursor.fetchall():
            total_minted += row[0]
    TOTAL_MINTED_CACHE[tick] = total_minted
    return total_minted


def get_src101_deploy(db, deploy_hash, src101_processed_in_block):
    """
    Retrieves the 'lim', 'pri', 'mintstart', 'mintend' and 'rec' values for a given DEPLOY HASH. The function first attempts to find these values
    from an internal cache. If not found in the cache, it then searches within a provided dictionary of processed blocks.
    As a last resort, it performs a database lookup. The result from any of these sources is cached for future queries.

    Args:
        db: A database connection object used for querying the database if necessary.
        tick (str): The tick value for which 'lim', 'pri', 'mintstart', 'mintend' and 'rec' values are being retrieved.
        src101_processed_in_block (dict): A dictionary containing processed blocks, used for in-memory lookup before querying the database.

    Returns:
        tuple: A tuple containing the 'lim', 'pri', 'mintstart', 'mintend' and 'rec' values for the given tick. If the tick is not found in any source,
               returns (None, None, None).

    """
    # Initialize the cache if it doesn't exist
    if not hasattr(get_src101_deploy, "deploy_cache"):
        get_src101_deploy.deploy_cache = {}
    # Check if the result is already cached
    if deploy_hash in get_src101_deploy.deploy_cache:
        return get_src101_deploy.deploy_cache[deploy_hash]

    # Check in the processed_blocks dictionary
    lim, pri, mintstart, mintend, rec = get_src101_deploy_in_block(src101_processed_in_block, deploy_hash)
    if lim is not None:
        # Cache and return the result
        get_src101_deploy.deploy_cache[deploy_hash] = (lim, pri, mintstart, mintend, rec)
        return lim, pri, mintstart, mintend, rec

    # Database lookup if not found in cache or processed_blocks
    lim, pri, mintstart, mintend = get_src101_deploy_in_db(db, deploy_hash)
    rec = get_src101_recs_in_db(db, deploy_hash)
    if lim is not None:
        # Cache and return the result
        get_src101_deploy.deploy_cache[deploy_hash] = (lim, pri, mintstart, mintend, rec)
    return lim, pri, mintstart, mintend, rec


def get_src101_deploy_in_block(processed_blocks, deploy_hash):
    for item in processed_blocks:
        if item.get("deploy_hash") == deploy_hash and item.get("op") == "DEPLOY" and item.get("valid") == 1:
            return item.get("lim"), item.get("pri"), item.get("mintstart"), item.get("mintend"), item.get("rec")
    return None, None, None, None, None


def get_src101_deploy_in_db(db, deploy_hash):
    with db.cursor() as src101_cursor:
        src101_cursor.execute(
            f"""
            SELECT
                lim, pri, mintstart, mintend
            FROM
                {SRC101_VALID_TABLE}
            WHERE
                tx_hash = %s
                AND op = 'DEPLOY'
                AND p = 'SRC-101'
            ORDER BY
                block_index ASC
            LIMIT 1
        """,
            (deploy_hash,),
        )  # nosec
        result = src101_cursor.fetchone()
        if result:
            return result
    return None, None, None, None


def get_src101_recs_in_db(db, deploy_hash):
    with db.cursor() as src101_rec_cursor:
        src101_rec_cursor.execute(
            f"""
            SELECT
                address
            FROM
                {SRC101_RECIPIENTS_TABLE}
            WHERE
                deploy_hash = %s
                AND p = 'SRC-101'
        """,
            (deploy_hash,),
        )  # nosec
        results = src101_rec_cursor.fetchall()
        recipients = []
        for r in results:
            recipients.append(r[0])
        return recipients


def get_total_src101_minted_from_db(db, deploy_hash, blocktimestamp):
    if deploy_hash in TOTAL_MINTED_CACHE:
        return TOTAL_MINTED_CACHE[deploy_hash]
    total_minted = 0
    with db.cursor() as src101_cursor:
        src101_cursor.execute(
            f"""
            SELECT
            COUNT(*)
            FROM
                {SRC101_OWNERS_TABLE}
            WHERE
                deploy_hash = %s
                AND expire_timestamp <= {blocktimestamp}
        """,
            (deploy_hash),
        )  # nosec
        result = src101_cursor.fetchone()
        if result[0]:
            total_minted = result[0]
    TOTAL_MINTED_CACHE[deploy_hash] = total_minted
    return total_minted


def get_src101_price(db, deploy_hash, src101_processed_in_block):
    if not hasattr(get_src101_price, "price_cache"):
        get_src101_price.price_cache = {}
    # Check if the result is already cached
    if deploy_hash in get_src101_price.price_cache:
        return get_src101_price.price_cache[deploy_hash]

    # Check in the processed_blocks dictionary
    price = get_src101_price_in_block(src101_processed_in_block, deploy_hash)
    if price is not None:
        # Cache and return the result
        get_src101_price.price_cache[deploy_hash] = price
        return price

    # Database lookup if not found in cache or processed_blocks
    price = get_src101_price_in_db(db)
    if price is not None:
        # Cache and return the result
        get_src101_price.price_cache[deploy_hash] = price
    return price


def get_src101_price_in_block(processed_blocks, deploy_hash):
    for item in processed_blocks:
        if item.get("deploy_hash") == deploy_hash:
            return item.get("price")
    return None


def get_src101_price_in_db(db):
    with db.cursor() as cursor:
        query = f"""
            SELECT
                len,
                price
            FROM
                {SRC101_PRICE_TABLE}
            ORDER BY len ASC
            
        """
        cursor.execute(query)
        return [item[1] for item in cursor.fetchall()]


def get_next_stamp_number(db, identifier):
    """
    Return the index of the next transaction.

    Parameters:
    - db (database connection): The database connection object.
    - identifier (str): Either 'stamp' or 'cursed' to determine the type of transaction.

    Returns:
    int: The index of the next transaction.
    """
    func = cast(CacheMixin, get_next_stamp_number)
    if not hasattr(func, "cached_stamp"):
        func.cached_stamp = {}

    if identifier not in ["stamp", "cursed"]:
        raise ValueError("Invalid identifier. Must be either 'stamp' or 'cursed'.")

    if identifier in func.cached_stamp:
        if identifier == "cursed":
            next_number = func.cached_stamp[identifier] - 1
        else:
            next_number = func.cached_stamp[identifier] + 1
    else:
        with db.cursor() as cursor:
            if identifier == "stamp":
                query = f"""
                    SELECT MAX(stamp) from {STAMP_TABLE}
                """  # nosec
                increment = 1
                default_value = 0
            else:  # identifier == 'cursed'
                query = f"""
                    SELECT MIN(stamp) from {STAMP_TABLE}
                """  # nosec
                increment = -1
                default_value = -1

            cursor.execute(query)
            transactions = cursor.fetchone()
            next_number = transactions[0] + increment if transactions[0] is not None else default_value

    func.cached_stamp[identifier] = next_number
    return next_number


def check_reissue(db, cpid, valid_stamps_in_block):
    """
    Validate if there was a prior valid stamp for the given cpid in the database or block.

    Parameters:
    - db: The database connection object.
    - cpid: The unique identifier for the stamp.
    - valid_stamps_in_block: A list of CPID based stamps processed in the block.

    Returns:
    - is_btc_stamp: The adjusted value of is_btc_stamp after checking for reissue.
    - is_reissue: A boolean indicating if the stamp is a reissue.
    """
    func = cast(CacheMixin, check_reissue)
    if not hasattr(func, "cache"):
        func.cache = {}

    if cpid in func.cache:
        return True
    if check_reissue_in_block(valid_stamps_in_block, cpid):
        return True
    if check_reissue_in_db(db, cpid):
        return True


def check_reissue_in_block(valid_stamps_in_block, cpid):
    for item in reversed(valid_stamps_in_block):
        if item["cpid"] == cpid and (item["is_btc_stamp"] or item.get("is_cursed")):
            return True


def check_reissue_in_db(db, cpid):
    with db.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT stamp FROM {STAMP_TABLE}
            WHERE cpid = %s
            ORDER BY block_index DESC
            LIMIT 1
        """,
            (cpid,),
        )  # nosec
        result = cursor.fetchone()
        if result:
            return True


def last_db_index(db):
    """
    Retrieve the last block index from the database.

    Args:
        db: The database connection object.

    Returns:
        The last block index as an integer.
    """
    field_position = BLOCK_FIELDS_POSITION
    cursor = db.cursor()

    try:
        cursor.execute("""SELECT * FROM blocks WHERE block_index = (SELECT MAX(block_index) from blocks)""")
        blocks = cursor.fetchall()
        try:
            last_index = blocks[0][field_position["block_index"]]
        except IndexError:
            last_index = 0
    except mysql.Error:
        last_index = 0
    finally:
        cursor.close()
    return last_index


def next_tx_index(db):
    """
    Return the index of the next incremental transaction # from transactions table.

    Parameters:
    db (object): The database object.

    Returns:
    int: The index of the next transaction.
    """
    cursor = db.cursor()

    cursor.execute("""SELECT MAX(tx_index) FROM transactions""")
    max_tx_index = cursor.fetchone()[0]
    if max_tx_index is not None:
        tx_index = max_tx_index + 1
    else:
        tx_index = 0

    cursor.close()

    return tx_index


def insert_block(db, block_index, block_hash, block_time, previous_block_hash, difficulty):
    if difficulty is None:
        difficulty = 0.0
    else:
        difficulty = float(difficulty)
    args = (block_index, block_hash, block_time, previous_block_hash, difficulty)
    cursor = db.cursor()
    block_query = """INSERT INTO blocks(
                        block_index,
                        block_hash,
                        block_time,
                        previous_block_hash,
                        difficulty
                        ) VALUES(%s,%s,FROM_UNIXTIME(%s),%s,%s)"""
    try:
        cursor.execute(block_query, args)
    except mysql.IntegrityError as e:
        cursor.close()
        raise BlockAlreadyExistsError(f"Block {block_index} already exists in the database.") from e
    except Exception as e:
        cursor.close()
        raise DatabaseInsertError(f"Error executing query: {block_query} with arguments: {args}. Error message: {e}") from e


def update_block_hashes(db, block_index, txlist_hash, ledger_hash, messages_hash):
    """
    Update the hashes of a block in the MySQL database.
    This is for comoparison of hash tables across nodes.
    So we can validate that each node has the same data.

    Args:
        db (MySQLConnection): The MySQL database connection.
        block_index (int): The index of the block to update.
        txlist_hash (str): The new transaction list hash.
        ledger_hash (str): The new ledger hash.
        messages_hash (str): The new messages hash.
    Returns:
        None
    """
    cursor = db.cursor()
    # logger.info('Updating MySQL Block: {}'.format(block_index))
    block_query = """UPDATE blocks SET
                        txlist_hash = %s,
                        ledger_hash = %s,
                        messages_hash = %s
                        WHERE block_index = %s"""

    args = (txlist_hash, ledger_hash, messages_hash, block_index)

    try:
        cursor.execute(block_query, args)
    except Exception as e:
        raise BlockUpdateError(f"Error executing query: {block_query} with arguments: {args}. Error message: {e}")
    finally:
        cursor.close()


def get_balances_at_block(db, block_index):
    with db.cursor() as cursor:
        src20_valid_list = get_src20_valid_list(cursor, block_index)
    return calculate_balances(src20_valid_list)