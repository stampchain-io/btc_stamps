import csv
import decimal
import json
import logging
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

import pymysql as mysql
import requests

try:
    from pymysql.connections import Connection
except ImportError:
    Connection = Any  # type: ignore
from pymysql.cursors import Cursor

import config
import index_core.exceptions as exceptions
import index_core.log as log
import index_core.util as util
from config import (
    BLOCK_FIELDS_POSITION,
    BLOCKS_TABLE,
    DEBUG_SKIP_REBUILD_BALANCES,
    SRC20_TABLE,
    SRC20_VALID_TABLE,
    SRC101_OWNERS_TABLE,
    SRC101_PRICE_TABLE,
    SRC101_RECIPIENTS_TABLE,
    SRC101_TABLE,
    SRC101_VALID_TABLE,
    SRC_BACKGROUND_TABLE,
    STAMP_TABLE,
    STAMP_VIEWS_TABLE,
    TRANSACTIONS_TABLE,
)
from index_core.caching import SRC101DeployResult, cache_manager, clear_all_caches
from index_core.database_manager import DatabaseManager
from index_core.exceptions import BlockAlreadyExistsError, BlockUpdateError, DatabaseInsertError
from index_core.memory_manager import memory_manager
from index_core.stamp_types import NO_DEPLOY, DeployResult

logger = logging.getLogger(__name__)
log.set_logger(logger)

D = decimal.Decimal
F = TypeVar("F", bound=Callable[..., Any])

db_manager = DatabaseManager()

# Cache directory for bootstrap data ETags
CACHE_DIR = (
    Path(config.USER_CACHE_DIR) / ".indexer_cache" if hasattr(config, "USER_CACHE_DIR") else Path.home() / ".btc_stamps_cache"
)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def initialize(db: Connection) -> None:
    """Initialize data, create and populate the database."""
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


def check_db_connection(db):
    """Check database connection and reconnect if necessary."""
    try:
        return db_manager.ensure_connection(db)
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        raise


def reset_all_caches() -> None:
    """Clear all caches in the system."""
    cache_manager.clear_all()


def update_parsed_block(db: Connection, block_index: int) -> None:
    """Update the 'indexed' flag of a block in the database."""
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


def is_prev_block_parsed(db: Connection, block_index: int) -> bool:
    """Check if the previous block has been parsed and indexed."""
    prev_block_index = block_index - 1
    cached_result = cache_manager.get_cache_value("block", str(prev_block_index))
    if cached_result is not None:
        return cached_result

    cursor = db.cursor()
    cursor.execute(
        """
        SELECT * FROM blocks
        WHERE block_index = %s
        """,
        (prev_block_index,),
    )
    block = cursor.fetchone()
    cursor.close()

    result = block is not None and block[BLOCK_FIELDS_POSITION["indexed"]] == 1
    cache_manager.set_cache_value("block", str(prev_block_index), result)

    if not result:
        purge_block_db(db, prev_block_index)
        rebuild_balances(db)
        rebuild_owners(db)

    return result


def insert_into_src20_tables(db: Connection, processed_src20_in_block: List[Dict[str, Any]]) -> None:
    """Insert processed SRC-20 transactions into their respective tables using batch operations."""
    if not processed_src20_in_block:
        return

    with db.cursor() as src20_cursor:
        # Prepare batch data for both tables
        src20_batch = []
        src20_valid_batch = []

        for i, src20_dict in enumerate(processed_src20_in_block):
            id = f"{i}_{src20_dict.get('tx_index')}_"
            id += f"{src20_dict.get('tx_hash')}"

            # Prepare data for SRC20 table
            src20_batch.append((id, src20_dict))

            # Prepare data for SRC20Valid table if valid
            if src20_dict.get("valid") == 1:
                src20_valid_batch.append((id, src20_dict))

        # Batch insert into SRC20 table
        if src20_batch:
            insert_into_src20_table_batch(src20_cursor, SRC20_TABLE, src20_batch)

        # Batch insert into SRC20Valid table
        if src20_valid_batch:
            insert_into_src20_table_batch(src20_cursor, SRC20_VALID_TABLE, src20_valid_batch)


def insert_into_src101_tables(db: Connection, processed_src101_in_block: List[Dict[str, Any]]) -> None:
    """Insert processed SRC-101 transactions into their respective tables."""
    with db.cursor() as src101_cursor:
        for i, src101_dict in enumerate(processed_src101_in_block):
            id = f"{i}_{src101_dict.get('tx_index')}_"
            id += f"{src101_dict.get('tx_hash')}"
            insert_into_src101_table(src101_cursor, SRC101_TABLE, id, src101_dict)
            if src101_dict.get("valid") == 1:
                insert_into_src101_table(src101_cursor, SRC101_VALID_TABLE, id, src101_dict)
            if src101_dict.get("rec"):
                insert_into_recipients(src101_cursor, SRC101_RECIPIENTS_TABLE, id, src101_dict)
            if src101_dict.get("pri"):
                insert_into_src101price(src101_cursor, SRC101_PRICE_TABLE, src101_dict)


def insert_into_src20_table(cursor: Cursor, table_name: str, id: str, src20_dict: Dict[str, Any]) -> None:
    """Insert a single SRC-20 transaction into the specified table."""
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


def insert_into_src20_table_batch(cursor: Cursor, table_name: str, batch_data: List[Tuple[str, Dict[str, Any]]]) -> None:
    """Insert multiple SRC-20 transactions into the specified table using batch operations."""
    if not batch_data:
        return

    # Prepare batch values
    values = []
    for id, src20_dict in batch_data:
        block_time = src20_dict.get("block_time")
        if isinstance(block_time, int):
            block_time = datetime.fromtimestamp(block_time, tz=timezone.utc)

        row_values = [
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

        # Add balance columns for SRC20Valid table
        if table_name == SRC20_VALID_TABLE:
            row_values.extend([src20_dict.get("total_balance_creator"), src20_dict.get("total_balance_destination")])

        values.append(tuple(row_values))

    # Build column list based on table type
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

    if table_name == SRC20_VALID_TABLE:
        column_names.extend(["creator_bal", "destination_bal"])

    placeholders = ", ".join(["%s"] * len(column_names))

    query = f"""
        INSERT INTO {table_name} ({", ".join(column_names)})
        VALUES ({placeholders})
    """  # nosec

    cursor.executemany(query, values)
    return


def insert_into_recipients(cursor: Cursor, table_name: str, id: str, src101_dict: Dict[str, Any]) -> None:
    """Insert recipients into the database."""
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
            "block_index",
        ]
        column_values = [
            _id,
            src101_dict.get("p"),
            src101_dict.get("tx_hash"),
            rec,
            src101_dict.get("block_index"),
        ]
        placeholders = ", ".join(["%s"] * len(column_names))

        query = f"""
            INSERT INTO {table_name} ({", ".join(column_names)})
            VALUES ({placeholders})
        """  # nosec
        cursor.execute(query, tuple(column_values))


def insert_into_src101price(cursor: Cursor, table_name: str, src101_dict: Dict[str, Any]) -> None:
    """Insert SRC-101 price data into the database."""
    if isinstance(src101_dict["pri"], dict):
        for key, value in src101_dict["pri"].items():
            deploy_hash = src101_dict["tx_hash"]
            _id = deploy_hash + "_" + key
            column_names = [
                "id",
                "len",
                "price",
                "deploy_hash",
                "block_index",
            ]
            column_values = [
                _id,
                int(key),
                value,
                deploy_hash,
                src101_dict.get("block_index"),
            ]
            placeholders = ", ".join(["%s"] * len(column_names))

            query = f"""
                INSERT INTO {table_name} ({", ".join(column_names)})
                VALUES ({placeholders})
            """  # nosec
            cursor.execute(query, tuple(column_values))


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
        "tokenid_origin",
        "tokenid",
        "tokenid_utf8",
        "root",
        "description",
        "tick",
        "wla",
        "imglp",
        "imgf",
        "tick_hash",
        "deploy_hash",
        "creator",
        "pri",
        "dua",
        "idua",
        "coef",
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

    tokenid_origin = src101_dict.get("tokenid_origin")
    if isinstance(tokenid_origin, str):
        result = tokenid_origin
    elif isinstance(tokenid_origin, list) and all(isinstance(item, str) for item in tokenid_origin):
        result = ";".join(tokenid_origin)
    else:
        result = str(tokenid_origin)

    column_values = [
        id,
        src101_dict.get("tx_hash"),
        src101_dict.get("tx_index"),
        src101_dict.get("block_index"),
        src101_dict.get("p"),
        src101_dict.get("op"),
        src101_dict.get("name"),
        result,
        ";".join(src101_dict.get("tokenid")) if type(src101_dict.get("tokenid")) == list else src101_dict.get("tokenid"),
        (
            ";".join(src101_dict.get("tokenid_utf8"))
            if type(src101_dict.get("tokenid_utf8")) == list
            else src101_dict.get("tokenid_utf8")
        ),
        src101_dict.get("root"),
        src101_dict.get("desc"),
        src101_dict.get("tick"),
        src101_dict.get("wla"),
        src101_dict.get("imglp"),
        src101_dict.get("imgf"),
        src101_dict.get("tick_hash"),
        src101_dict.get("deploy_hash"),
        src101_dict.get("creator"),
        json.dumps(src101_dict.get("pri")),
        src101_dict.get("dua"),
        src101_dict.get("idua"),
        src101_dict.get("coef"),
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


def insert_transactions(db, transactions):
    """
    Insert multiple transactions into the database using efficient bulk inserts.
    Uses optimized batch processing for better performance.
    """
    try:
        # Sort transactions by tx_index to maintain order
        sorted_transactions = sorted(transactions, key=lambda x: x.tx_index if x.tx_index is not None else float("inf"))

        BATCH_SIZE = config.DB_TRANSACTION_BATCH_SIZE

        values = []

        for tx in sorted_transactions:
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
            for i in range(0, len(values), BATCH_SIZE):
                batch = values[i : i + BATCH_SIZE]
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
                    batch,
                )

                batch.clear()

            values.clear()

    except Exception as e:
        raise ValueError(f"Error occurred while inserting transactions: {e}")


def insert_into_stamp_table(db, parsed_stamps: List):
    """
    Insert multiple stamps into the database.
    Does not commit - transaction boundaries are handled by the caller.

    Args:
        db (DatabaseConnection): The database connection object
        parsed_stamps (List): List of parsed stamp objects to insert

    Raises:
        ValueError: If error occurs during insertion
    """
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
                    file_hash, is_valid_base64, file_size_bytes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    parsed.file_size_bytes,
                )
                for parsed in parsed_stamps
            ]

            cursor.executemany(insert_query, data)
    except Exception as e:
        # Don't rollback here - let the caller handle it
        raise ValueError(f"Error occurred while inserting to StampTable: {e}")


def get_srcbackground_data(db: Connection, tick: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
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


def get_existing_balances(cursor: Cursor) -> List[Tuple[Any, ...]]:
    """Get existing balances, ensuring we only get SRC-20 records."""
    query = """
    SELECT id, tick, tick_hash, address, amt, last_update
    FROM balances
    WHERE p = 'SRC-20'  -- Explicitly filter for SRC-20 only
    AND amt != 0        -- Exclude zero balances
    ORDER BY id         -- Ensure consistent ordering
    """
    cursor.execute(query)
    return [tuple(row) for row in cursor.fetchall()]


def get_src20_valid_list(cursor: Cursor, block_index: Optional[int] = None) -> List[Tuple[Any, ...]]:
    """Get valid SRC-20 transactions up to the specified block index."""
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

    return list(cursor.fetchall())


def get_existing_owners(cursor: Cursor) -> List[Tuple[Any, ...]]:
    """Get existing owners from the database."""
    query = """
    SELECT owners.index, id, p, deploy_hash, tokenid, tokenid_utf8, img, preowner, owner, prim, address_btc, address_eth, txt_data, expire_timestamp, last_update
    FROM owners where p = 'SRC-101'
    """
    cursor.execute(query)
    return list(cursor.fetchall())


def get_src101_valid_list(cursor: Cursor, block_index: Optional[int] = None) -> List[Tuple[Any, ...]]:
    """Get valid SRC-101 transactions up to the specified block index."""
    query = f"""
    SELECT op, tokenid, tokenid_utf8, img, deploy_hash, creator, dua, toaddress, prim,
           address_btc, address_eth, txt_data, block_time, block_index, tx_index
    FROM {SRC101_VALID_TABLE}
    WHERE (op = 'TRANSFER' OR op = 'MINT' OR op = 'SETRECORD' OR op = 'RENEW')
    """
    if block_index is not None:
        query += " AND block_index <= %s"
    query += " ORDER by block_index ASC, tx_index ASC"

    if block_index is not None:
        cursor.execute(query, (block_index,))
    else:
        cursor.execute(query)

    results = cursor.fetchall()
    logger.info(f"Found {len(results)} SRC-101 transactions")
    logger.info(f"Operations breakdown: {Counter(r[0] for r in results)}")

    return list(results)


def calculate_owners(db, src101_valid_list: List[Tuple[Any, ...]]) -> Dict[str, Dict[str, Any]]:
    """Calculate owners from SRC-101 valid list.

    Args:
        src101_valid_list: List of tuples containing SRC-101 transaction data

    Returns:
        Dictionary mapping IDs to owner details
    """
    all_owners: Dict[str, Dict[str, Any]] = {}
    all_index: Dict[str, int] = {}
    for [
        op,
        tokenid,
        tokenid_utf8,
        img,
        deploy_hash,
        creator,
        dua,
        toaddress,
        prim,
        address_btc,
        address_eth,
        txt_data,
        block_time,
        block_index,
        tx_index,
    ] in src101_valid_list:
        id = "SRC-101" + "_" + deploy_hash + (tokenid or "")

        if op == "MINT":
            tokenid_split = (tokenid or "").split(";")
            tokenid_utf8_split = (tokenid_utf8 or "").split(";")
            if img is not None:
                img_split = img.split(";")
            else:
                img_split = []
                _, _, _, _, _, _, imglp, imgf, _ = get_src101_deploy(db, deploy_hash, {})
                for i in range(len(tokenid_utf8_split)):
                    img_split.append(str(imglp or "") + tokenid_utf8_split[i] + "." + str(imgf or ""))

            max_length = max(len(tokenid_split), len(tokenid_utf8_split), len(img_split))
            tokenid_split = tokenid_split + [""] * (max_length - len(tokenid_split))
            tokenid_utf8_split = tokenid_utf8_split + [""] * (max_length - len(tokenid_utf8_split))
            img_split = img_split + [""] * (max_length - len(img_split))

            for i in range(max_length):
                _index = all_index.get(deploy_hash, 0)
                id = "SRC-101" + "_" + deploy_hash + tokenid_split[i]
                all_owners[id] = {
                    "index": _index + 1,
                    "id": id,
                    "p": "SRC-101",
                    "deploy_hash": deploy_hash,
                    "tokenid": tokenid_split[i],
                    "tokenid_uft8": tokenid_utf8_split[i],
                    "img": img_split[i],
                    "preowner": None,
                    "owner": toaddress,
                    "prim": prim,
                    "address_btc": toaddress,
                    "address_eth": None,
                    "txt_data": None,
                    "expire_timestamp": 31536000 * dua + int(block_time.timestamp()),
                    "last_update": block_index,
                }
                all_index[deploy_hash] = _index + 1
        elif op == "TRANSFER":
            id = "SRC-101" + "_" + deploy_hash + tokenid
            if id in all_owners:
                all_owners[id]["preowner"] = all_owners[id]["owner"]
                all_owners[id]["owner"] = toaddress
                all_owners[id]["address_btc"] = None
                all_owners[id]["address_eth"] = None
                all_owners[id]["txt_data"] = None
                all_owners[id]["last_update"] = block_index
            else:
                logger.warning("Unexpected situations, there is no mint but can be transferred transactions")
        elif op == "SETRECORD":
            id = "SRC-101" + "_" + deploy_hash + tokenid
            if id in all_owners:
                all_owners[id]["prim"] = prim
                all_owners[id]["address_btc"] = address_btc if address_btc is not None else all_owners[id]["address_btc"]
                all_owners[id]["address_eth"] = address_eth if address_eth is not None else all_owners[id]["address_eth"]
                all_owners[id]["txt_data"] = txt_data if txt_data is not None else all_owners[id]["txt_data"]
                all_owners[id]["last_update"] = block_index
            else:
                logger.warning("Unexpected situations, there is no mint but can be transferred transactions")
        elif op == "RENEW":
            id = "SRC-101" + "_" + deploy_hash + tokenid
            if id in all_owners:
                all_owners[id]["expire_timestamp"] = all_owners[id]["expire_timestamp"] + 31536000 * dua
                all_owners[id]["last_update"] = block_index
            else:
                logger.warning("Unexpected situations, there is no mint but can be transferred transactions")
    return all_owners


def calculate_balances(src20_valid_list: List[Tuple[Any, ...]]) -> Dict[str, Dict[str, D]]:
    """Calculate balances from SRC-20 valid list with optimized performance."""
    # Use defaultdict for more efficient balance tracking
    balances: Dict[str, Dict[str, D]] = defaultdict(lambda: defaultdict(D))
    metadata: Dict[str, Dict[str, Any]] = {}

    # Process in chunks for better memory management
    CHUNK_SIZE = 5000
    for i in range(0, len(src20_valid_list), CHUNK_SIZE):
        chunk = src20_valid_list[i : i + CHUNK_SIZE]

        for [op, creator, destination, tick, tick_hash, amt, block_time, block_index] in chunk:
            # Track balances efficiently - exact same logic as original
            balances[tick][destination] += D(amt)
            if op == "TRANSFER":
                balances[tick][creator] -= D(amt)

            # Always update metadata to match original behavior
            destination_id = f"{tick}_{destination}"
            metadata[destination_id] = {
                "tick": tick,
                "tick_hash": tick_hash,
                "address": destination,
                "last_update": block_index,
                "block_time": block_time,
            }

            if op == "TRANSFER":
                creator_id = f"{tick}_{creator}"
                metadata[creator_id] = {
                    "tick": tick,
                    "tick_hash": tick_hash,
                    "address": creator,
                    "last_update": block_index,
                    "block_time": block_time,
                }

        # Clear chunk from memory
        del chunk

        # Check memory pressure and clear caches if needed
        if i > 0 and i % (CHUNK_SIZE * 5) == 0:
            memory_manager.clear_caches_if_needed()

    # Combine balances with metadata - exact same logic as original
    all_balances: Dict[str, Dict[str, Any]] = {}
    for tick, tick_balances in balances.items():
        for address, amt in tick_balances.items():
            if amt != D(0):  # Only include non-zero balances
                balance_id = f"{tick}_{address}"
                all_balances[balance_id] = metadata[balance_id] | {"amt": amt}

    # Clear intermediate data structures
    balances.clear()
    metadata.clear()

    # Final memory check
    memory_manager.clear_caches_if_needed()

    return all_balances


def owners_need_update(existing_owners, all_owners):
    """Compare existing owners with calculated owners"""
    try:
        existing_set = set()
        new_set = set()

        # Process existing owners
        logger.info(f"Processing {len(existing_owners)} existing owners")
        for owner in existing_owners:
            if len(owner) < 15:
                continue

            deploy_hash = owner[3]
            tokenid = owner[4]
            owner_address = owner[8]
            block_index = owner[14] or 0

            owner_tuple = (deploy_hash, tokenid, owner_address, block_index)
            existing_set.add(owner_tuple)

        # Process calculated owners
        logger.info(f"Processing {len(all_owners)} calculated owners")
        for key, value in all_owners.items():
            owner_tuple = (value["deploy_hash"], value["tokenid"], value["owner"], value.get("last_update", 0))
            new_set.add(owner_tuple)

        # Log comparison details
        logger.info(f"Comparing {len(existing_set)} existing owners with {len(new_set)} calculated owners")

        # Compare sets
        if existing_set != new_set:
            missing_in_new = existing_set - new_set
            missing_in_existing = new_set - existing_set

            if missing_in_new:
                logger.info(f"Found {len(missing_in_new)} owners in database that are not in calculated set")
                for diff in list(missing_in_new)[:5]:
                    logger.info(f"Missing in calculated: {diff}")

            if missing_in_existing:
                logger.info(f"Found {len(missing_in_existing)} calculated owners that are not in database")
                for diff in list(missing_in_existing)[:5]:
                    logger.info(f"Missing in database: {diff}")

            return True

        return False

    except Exception as e:
        logger.error(f"Error comparing owners: {str(e)}")
        return True


def insert_balances(cursor, all_balances):
    logger.info(f"Inserting {len(all_balances)} balances")

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

    BATCH_SIZE = config.DB_BALANCE_BATCH_SIZE
    total_rows = len(values)

    for i in range(0, total_rows, BATCH_SIZE):
        batch = values[i : i + BATCH_SIZE]
        logger.info(
            f"Processing batch balances update {i // BATCH_SIZE + 1}/{(total_rows + BATCH_SIZE - 1) // BATCH_SIZE} ({len(batch)} rows)"
        )

        cursor.executemany(
            """INSERT INTO balances(id, tick, tick_hash, address, amt, last_update, block_time, p)
               VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
            batch,
        )


def purge_owners(cursor):
    """Purge the owners table"""
    logger.warning("Purging owners table")
    cursor.execute("TRUNCATE TABLE owners")


def insert_owners(cursor, all_owners):
    logger.info(f"Inserting {len(all_owners)} owners")
    values = [
        (
            value.get("index"),
            value.get("id"),
            value.get("p"),
            value.get("deploy_hash"),
            value.get("tokenid"),
            value.get("tokenid_uft8"),
            value.get("img"),
            value.get("preowner"),
            value.get("owner"),
            value.get("prim"),
            value.get("address_btc"),
            value.get("address_eth"),
            value.get("txt_data"),
            value.get("expire_timestamp"),
            value.get("last_update"),
        )
        for key, value in all_owners.items()
    ]

    cursor.executemany(
        """INSERT INTO owners(owners.index, id, p, deploy_hash, tokenid, tokenid_utf8, img, preowner, owner, prim, address_btc, address_eth, txt_data, expire_timestamp, last_update)
                          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        values,
    )


def rebuild_owners(db, block_index=None):
    cursor = db.cursor()

    try:
        logger.info("Validating Owners Table..")
        db.begin()

        existing_owners = get_existing_owners(cursor)
        src101_valid_list = get_src101_valid_list(cursor, block_index)
        all_owners = calculate_owners(db, src101_valid_list)

        if not owners_need_update(existing_owners, all_owners):
            logger.info("No changes in owners. Skipping deletion and insertion.")
            return

        purge_owners(cursor)
        insert_owners(cursor, all_owners)

        db.commit()

    except Exception as e:
        db.rollback()
        raise e

    finally:
        cursor.close()


def rebuild_balances(db, block_index=None):
    """Rebuild the balances table with optimized performance for large datasets."""
    if DEBUG_SKIP_REBUILD_BALANCES:
        logger.warning("DEBUG MODE: Skipping rebuild_balances due to DEBUG_SKIP_REBUILD_BALANCES flag")
        return

    # Use dedicated connection for long operation
    long_db = db_manager.get_long_running_connection()
    cursor = long_db.cursor()

    try:
        logger.info("Starting Balances Table rebuild..")

        # Set extended timeouts
        cursor.execute("SET SESSION wait_timeout=86400")  # 24 hours
        cursor.execute("SET SESSION max_execution_time=8640000")  # 24 hours in milliseconds
        cursor.execute("SET SESSION innodb_lock_wait_timeout=600")
        cursor.execute("SET SESSION net_read_timeout=600")
        cursor.execute("SET SESSION net_write_timeout=600")

        BATCH_SIZE = config.DB_REBUILD_BATCH_SIZE
        COMMIT_INTERVAL = 25

        # Get all data first to maintain exact same logic
        existing_balances = get_existing_balances(cursor)
        src20_valid_list = get_src20_valid_list(cursor, block_index)
        all_balances = calculate_balances(src20_valid_list)

        if not balances_need_update(existing_balances, all_balances):
            logger.info("No changes in balances. Skipping deletion and insertion.")
            return

        # Create temp table
        temp_table = "temp_balances_" + str(int(time.time()))
        logger.debug(f"Creating temporary table: {temp_table}")
        cursor.execute(f"CREATE TABLE {temp_table} LIKE balances")

        # Insert into temp table in batches
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
            if value["amt"] != 0  # Skip zero balances
        ]

        # Use smaller batch size for inserts to prevent timeouts
        total_rows = len(values)

        for i in range(0, total_rows, BATCH_SIZE):
            batch = values[i : i + BATCH_SIZE]
            logger.info(
                f"Processing balance rebuild batch {i // BATCH_SIZE + 1}/{(total_rows + BATCH_SIZE - 1) // BATCH_SIZE}"
            )

            cursor.executemany(
                f"""
                INSERT INTO {temp_table}(id, tick, tick_hash, address, amt, last_update, block_time, p)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                batch,
            )

            # Commit periodically but not too frequently
            if (i // BATCH_SIZE) % COMMIT_INTERVAL == 0:
                long_db.commit()

        # Final commit
        long_db.commit()

        # Atomic swap
        logger.info("Performing atomic table swap")
        cursor.execute(
            f"""
            RENAME TABLE balances TO balances_old,
                         {temp_table} TO balances
            """
        )

        # Cleanup
        logger.debug("Cleaning up old table")
        cursor.execute("DROP TABLE IF EXISTS balances_old")

        logger.info("Balance rebuild completed successfully")

    except Exception as e:
        logger.error(f"Error during balance rebuild: {e}")
        long_db.rollback()
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {temp_table}")
        except Exception as drop_error:
            logger.error(f"Error dropping temp table: {drop_error}")
        raise e

    finally:
        try:
            cursor.close()
            long_db.close()  # Close dedicated connection
        except Exception as e:
            logger.error(f"Error closing long-running connection: {e}")


def insert_batch_to_temp(cursor, temp_table, balances_batch):
    """Helper function to insert a batch of balances into temp table."""
    if not balances_batch:
        return

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
        for key, value in balances_batch.items()
        if value["amt"] != 0  # Only insert non-zero balances
    ]

    if not values:
        return

    CHUNK_SIZE = 1000
    for i in range(0, len(values), CHUNK_SIZE):
        chunk = values[i : i + CHUNK_SIZE]
        cursor.executemany(
            f"""
            INSERT INTO {temp_table} (id, tick, tick_hash, address, amt, last_update, block_time, p)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                amt = VALUES(amt),
                last_update = VALUES(last_update),
                block_time = VALUES(block_time)
            """,
            chunk,
        )


def purge_block_db(db: Connection, block_index: int) -> None:
    """Purge transactions from the database for a reorg or where transactions were partially committed."""
    # Clear all caches using the centralized cache manager
    clear_all_caches()
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
        SRC101_VALID_TABLE,
        SRC101_TABLE,
        SRC101_PRICE_TABLE,
        SRC101_RECIPIENTS_TABLE,
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


def get_src20_deploy(db: Connection, tick: str, src20_processed_in_block: List[Dict[str, Any]]) -> DeployResult:
    """Get SRC20 deployment details with caching.

    Returns:
        DeployResult: (lim, max, dec) values for the deployment.
        Returns NO_DEPLOY if no valid deployment exists.
    """
    # Keep original cache key format
    cached_result = cache_manager.get_cache_value("deploy", f"src20:{tick}")
    if cached_result is not None and cached_result != NO_DEPLOY:
        return cached_result

    # Check blocks first, then DB - maintaining original order
    result = get_src20_deploy_in_block(src20_processed_in_block, tick)
    if result == NO_DEPLOY:
        result = get_src20_deploy_in_db(db, tick)

    # Cache only valid results, exactly as before
    if result != NO_DEPLOY:
        cache_manager.set_cache_value("deploy", f"src20:{tick}", result)
    return result


def get_src20_deploy_in_block(processed_blocks: List[Dict[str, Any]], tick: str) -> DeployResult:
    """Get SRC20 deployment details from processed blocks.

    Returns:
        DeployResult: (lim, max, dec) values for the deployment.
        Returns (None, None, None) if no valid deployment exists in the block.
    """
    for item in processed_blocks:
        if item.get("tick") == tick and item.get("op") == "DEPLOY" and item.get("valid") == 1:
            # For in-block deploys, we still use get() with None default since the data hasn't been validated by DB yet
            return item.get("lim"), item.get("max"), item.get("dec")
    return NO_DEPLOY


def get_src20_deploy_in_db(db: Connection, tick: str) -> DeployResult:
    """Get SRC20 deployment details from database.

    Returns:
        DeployResult: (lim, max, dec) values for the deployment.
        Returns (None, None, None) if no valid deployment exists in the DB.
        Note: If a deployment exists in the DB, all values will be non-None.
    """
    normalized_tick = tick.lower()

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
                AND lim IS NOT NULL
                AND max IS NOT NULL
                AND deci IS NOT NULL
            ORDER BY
                block_index ASC
            LIMIT 1
            """,
            (normalized_tick,),
        )  # nosec

        result = src20_cursor.fetchone()
        if result:
            # We know these are all non-None due to the SQL WHERE clause
            logger.debug(f"Found deployment for tick {tick}: lim={result[0]}, max={result[1]}, dec={result[2]}")
            return result
    return NO_DEPLOY


def get_total_src20_minted_from_db(db: Connection, tick: str) -> D:
    """Get the total minted amount for a given tick from the database."""
    cached_total = cache_manager.get_cache_value("total_minted", tick)
    if cached_total is not None:
        return cached_total

    with db.cursor() as src20_cursor:
        src20_cursor.execute(
            f"""
            SELECT
                SUM(amt)
            FROM
                {SRC20_VALID_TABLE}
            WHERE
                tick = %s
                AND op = 'MINT'
        """,
            (tick,),
        )  # nosec
        result = src20_cursor.fetchone()
        # Handle case where result is None or result[0] is None
        total_minted = D(0) if result is None or result[0] is None else D(str(result[0]))
        cache_manager.set_cache_value("total_minted", tick, total_minted)
        return total_minted


def get_src101_deploy(db: Connection, deploy_hash: str, src101_processed_in_block: List[Dict[str, Any]]) -> SRC101DeployResult:
    """Get SRC-101 deployment details with caching."""
    # Check if the result is already cached
    cached_result = cache_manager.get_cache_value("src101_deploy", deploy_hash)
    if cached_result is not None:
        return cached_result

    # Check in the processed_blocks dictionary
    result = get_src101_deploy_in_block(src101_processed_in_block, deploy_hash)
    if result[0] != 0:  # If lim is not 0
        cache_manager.set_cache_value("src101_deploy", deploy_hash, result)
        return result

    # Database lookup if not found in cache or processed_blocks
    db_result = get_src101_deploy_in_db(db, deploy_hash)
    if db_result[0] != 0:  # If lim is not 0
        rec = get_src101_recs_in_db(db, deploy_hash)
        # Replace None rec placeholder with actual rec list
        result = (
            db_result[0],  # lim
            db_result[1],  # pri
            db_result[2],  # mintstart
            db_result[3],  # mintend
            rec,  # rec
            db_result[5],  # wla
            db_result[6],  # imglp
            db_result[7],  # imgf
            db_result[8],  # idua
        )
        cache_manager.set_cache_value("src101_deploy", deploy_hash, result)
        return result
    return (0, None, 0, 0, None, None, None, None, 0)


def get_src101_deploy_in_block(processed_blocks: List[Dict[str, Any]], deploy_hash: str) -> SRC101DeployResult:
    """Get SRC-101 deployment details from processed blocks."""
    for item in processed_blocks:
        if item.get("deploy_hash") == deploy_hash and item.get("op") == "DEPLOY" and item.get("valid") == 1:
            return (
                item.get("lim", 0),
                item.get("pri"),
                item.get("mintstart", 0),
                item.get("mintend", 0),
                item.get("rec"),
                item.get("wla"),
                item.get("imglp"),
                item.get("imgf"),
                item.get("idua", 0),
            )
    return (0, None, 0, 0, None, None, None, None, 0)


def get_src101_deploy_in_db(
    db: Connection, deploy_hash: str
) -> Tuple[int, Optional[Any], int, int, Optional[Any], Optional[Any], Optional[Any], Optional[Any], int]:
    """Get SRC-101 deployment details from database.

    Returns:
        A tuple of (lim, pri, mintstart, mintend, None, wla, imglp, imgf, idua).
        The fifth element (rec) is always None as it's fetched separately.
    """
    with db.cursor() as src101_cursor:
        src101_cursor.execute(
            f"""
            SELECT
                lim, pri, mintstart, mintend, wla, imglp, imgf, idua
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
            # Convert to proper tuple with None for rec field
            lim, pri, mintstart, mintend, wla, imglp, imgf, idua = result
            return (
                int(lim) if lim is not None else 0,
                pri,
                int(mintstart) if mintstart is not None else 0,
                int(mintend) if mintend is not None else 0,
                None,  # rec placeholder  TODO: investigate why rec was not returned prior to this change
                wla,
                imglp,
                imgf,
                int(idua) if idua is not None else 0,
            )
    return (0, None, 0, 0, None, None, None, None, 0)


def get_src101_recs_in_db(db: Connection, deploy_hash: str) -> List[str]:
    """Get SRC-101 recipients from database."""
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


def get_total_src101_minted_from_db(db: Connection, deploy_hash: str, blocktimestamp: int) -> D:
    """Get the total minted amount for a given deploy_hash from the database."""
    cached_total = cache_manager.get_cache_value("total_minted", deploy_hash)
    if cached_total is not None:
        return cached_total

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
            (deploy_hash,),
        )  # nosec
        result = src101_cursor.fetchone()
        total_minted = D(result[0] if result[0] is not None else 0)
        cache_manager.set_cache_value("total_minted", deploy_hash, total_minted)
        return total_minted


def get_src101_price(
    db: Connection, deploy_hash: str, src101_processed_in_block: List[Dict[str, Any]]
) -> Optional[Dict[int, Any]]:
    """Get SRC-101 price details with caching."""
    # Check if the result is already cached
    cached_result = cache_manager.get_cache_value("price", deploy_hash)
    if cached_result is not None:
        return cached_result

    # Check in the processed_blocks dictionary
    price = get_src101_price_in_block(src101_processed_in_block, deploy_hash)
    if price is not None:
        # Cache and return the result
        cache_manager.set_cache_value("price", deploy_hash, price)
        return price

    # Database lookup if not found in cache or processed_blocks
    price = get_src101_price_in_db(db, deploy_hash)
    if price is not None:
        # Cache and return the result
        cache_manager.set_cache_value("price", deploy_hash, price)
    return price


def get_src101_price_in_block(processed_blocks: List[Dict[str, Any]], deploy_hash: str) -> Optional[Dict[int, Any]]:
    """Get SRC-101 price from processed blocks."""
    for item in processed_blocks:
        if item.get("deploy_hash") == deploy_hash:
            return item.get("price")
    return None


def get_src101_price_in_db(db: Connection, deploy_hash: str) -> Dict[int, Any]:
    """Get SRC-101 price from database."""
    with db.cursor() as cursor:
        query = f"""
            SELECT
                len,
                price
            FROM
                {SRC101_PRICE_TABLE}
            WHERE
                deploy_hash = %s
            ORDER BY len ASC

        """
        cursor.execute(
            query,
            (deploy_hash),
        )
        result = cursor.fetchall()
        return {r[0]: r[1] for r in result}


def get_next_stamp_number(db, identifier):
    """
    Return the index of the next transaction.

    Parameters:
    - db (database connection): The database connection object.
    - identifier (str): Either 'stamp' or 'cursed' to determine the type of transaction.

    Returns:
    int: The index of the next transaction.
    """
    if identifier not in ["stamp", "cursed"]:
        raise ValueError("Invalid identifier. Must be either 'stamp' or 'cursed'.")

    cached_result = cache_manager.get_cache_value("stamp", identifier)
    if cached_result is not None:
        if identifier == "cursed":
            next_number = cached_result - 1
        else:
            next_number = cached_result + 1
        cache_manager.set_cache_value("stamp", identifier, next_number)
        return next_number

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

    cache_manager.set_cache_value("stamp", identifier, next_number)
    return next_number


def check_reissue(db: Connection, cpid: str, valid_stamps_in_block: List[Dict[str, Any]]) -> bool:
    """Check for reissue with caching."""
    # If the CPID is already in the cache, it's a reissue
    reissue_cache = cache_manager.get_cache("reissue")
    if reissue_cache is not None and cpid in reissue_cache:
        return True

    if check_reissue_in_block(valid_stamps_in_block, cpid):
        cache_manager.set_cache_value("reissue", cpid, True)
        return True

    if check_reissue_in_db(db, cpid):
        cache_manager.set_cache_value("reissue", cpid, True)
        return True

    return False


def check_reissue_in_block(valid_stamps_in_block: List[Dict[str, Any]], cpid: str) -> Optional[bool]:
    """Check for reissue in processed blocks."""
    for item in reversed(valid_stamps_in_block):
        if item["cpid"] == cpid and (item["is_btc_stamp"] or item.get("is_cursed")):
            return True
    return None


def check_reissue_in_db(db: Connection, cpid: str) -> bool:
    """Check for reissue in database."""
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
    return False


def last_db_index(db: Connection) -> int:
    """Retrieve the last block index from the database."""
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


def next_tx_index(db: Connection) -> int:
    """Return the index of the next incremental transaction from transactions table."""
    cursor = db.cursor()

    cursor.execute("""SELECT MAX(tx_index) FROM transactions""")
    max_tx_index = cursor.fetchone()[0]
    if max_tx_index is not None:
        tx_index = max_tx_index + 1
    else:
        tx_index = 0

    cursor.close()

    return tx_index


def insert_block(
    db: Connection, block_index: int, block_hash: str, block_time: int, previous_block_hash: str, difficulty: Optional[float]
) -> None:
    """Insert a new block into the database."""
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


def update_block_hashes(db: Connection, block_index: int, txlist_hash: str, ledger_hash: str, messages_hash: str) -> None:
    """Update the hashes of a block in the MySQL database."""
    cursor = db.cursor()
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


def get_balances_at_block(db: Connection, block_index: int) -> Dict[str, Dict[str, D]]:
    """Get balances at a specific block index."""
    with db.cursor() as cursor:
        src20_valid_list = get_src20_valid_list(cursor, block_index)
    return calculate_balances(src20_valid_list)


def get_unlocked_cpids(db: Connection) -> List[Tuple[str, ...]]:
    """Get a list of unlocked CPIDs from the database."""
    with db.cursor() as cursor:
        cursor.execute(f"SELECT DISTINCT cpid FROM {STAMP_TABLE} WHERE locked != 1 AND (ident = 'SRC-721' or ident = 'STAMP')")
        return list(cursor.fetchall())


def update_assets_in_db(
    db: Connection, assets_details: List[Dict[str, Any]], chunk_size: int = 200, delay_between_chunks: int = 2
) -> None:
    """Update asset details in the database in chunks."""
    total_assets = len(assets_details)
    num_chunks = (total_assets + chunk_size - 1) // chunk_size

    for i in range(num_chunks):
        start = i * chunk_size
        end = min(start + chunk_size, total_assets)
        assets_chunk = assets_details[start:end]
        logger.info(f"Updating assets in database for chunk {i + 1}/{num_chunks}")

        try:
            updates = []
            with db.cursor() as cursor:
                for asset in assets_chunk:
                    cpid = asset.get("asset")
                    if cpid is None:
                        continue
                    set_clauses = []
                    params: List[Any] = []

                    if "locked" in asset:
                        locked = 1 if asset.get("locked") else 0
                        set_clauses.append("locked = %s")
                        params.append(locked)

                    if "divisible" in asset:
                        divisible = 1 if asset.get("divisible") else 0
                        set_clauses.append("divisible = %s")
                        params.append(divisible)

                    if "supply" in asset:
                        supply = asset.get("supply", 0)
                        set_clauses.append("supply = %s")
                        params.append(supply)

                    if not set_clauses:
                        continue

                    params.append(cpid)
                    set_clause = ", ".join(set_clauses)
                    sql = f"""
                        UPDATE {STAMP_TABLE} SET
                            {set_clause}
                        WHERE cpid = %s
                        """
                    updates.append((sql, params))

                for sql, params in updates:
                    cursor.execute(sql, params)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating assets in chunk {i + 1}: {e}")
            raise DatabaseInsertError(f"Failed to update assets in chunk {i + 1}: {e}")

        if i < num_chunks - 1:
            time.sleep(delay_between_chunks)


def update_src20_token_stats(db):
    """
    Updates the src20_token_stats table with latest balances data.
    This should be called after processing each block to keep stats current.
    """
    logger.debug("Updating src20_token_stats table")

    query = """
        INSERT INTO src20_token_stats (tick, total_minted, holders_count)
        SELECT * FROM v_src20_token_stats
        ON DUPLICATE KEY UPDATE
            total_minted = VALUES(total_minted),
            holders_count = VALUES(holders_count)
    """

    with db.cursor() as cursor:
        cursor.execute(query)


def balances_need_update(existing_balances, all_balances):
    """
    Compare existing balances with calculated balances, accounting for in-progress updates
    """
    try:
        # Normalize the balance data for comparison
        existing_set = set()
        new_set = set()

        # Process existing balances
        for balance in existing_balances:
            if len(balance) < 6:
                continue

            id, tick, tick_hash, address, amt, last_update = balance[:6]

            try:
                # Normalize amount
                amt = D(str(amt)) if amt else D("0")

                # Skip zero balances
                if amt == D("0"):
                    continue

                # Create comparable tuple
                balance_tuple = (tick, tick_hash, address, amt)
                existing_set.add(balance_tuple)

            except (ValueError, TypeError, decimal.InvalidOperation) as e:
                logger.debug(f"Skipping invalid existing balance: {balance}, error: {e}")
                continue

        # Process calculated balances
        for key, value in all_balances.items():
            try:
                amt = D(str(value.get("amt", "0")))

                # Skip zero balances
                if amt == D("0"):
                    continue

                # Create comparable tuple
                balance_tuple = (value.get("tick", ""), value.get("tick_hash", ""), value.get("address", ""), amt)
                new_set.add(balance_tuple)

            except (ValueError, TypeError, decimal.InvalidOperation) as e:
                logger.debug(f"Skipping invalid calculated balance: {key}: {value}, error: {e}")
                continue

        # Log set sizes after normalization
        logger.info(
            f"Comparing {len(existing_set)} non-zero existing balances with {len(new_set)} non-zero calculated balances"
        )

        # Compare sets
        if existing_set != new_set:
            # Calculate specific differences
            missing_in_new = existing_set - new_set
            missing_in_existing = new_set - existing_set

            if missing_in_new:
                logger.info(f"Found {len(missing_in_new)} balances in database that are not in calculated set")
                for diff in list(missing_in_new)[:5]:
                    logger.debug(f"Missing in calculated: {diff}")

            if missing_in_existing:
                logger.info(f"Found {len(missing_in_existing)} calculated balances that are not in database")
                for diff in list(missing_in_existing)[:5]:
                    logger.debug(f"Missing in database: {diff}")

            return True

        return False

    except Exception as e:
        logger.error(f"Error comparing balances: {str(e)}")
        return True


def increment_stamp_view_count(db: Connection, stamp_id: int) -> None:
    """
    Increment the view count for a specific stamp.
    Creates a new record if the stamp doesn't exist in the stamp_views table.

    Args:
        db: Database connection
        stamp_id: The stamp ID to increment views for
    """
    try:
        with db.cursor() as cursor:
            # Use INSERT ... ON DUPLICATE KEY UPDATE to handle both new and existing records
            query = f"""
                INSERT INTO {STAMP_VIEWS_TABLE} (stamp, view_count, last_viewed)
                VALUES (%s, 1, NOW())
                ON DUPLICATE KEY UPDATE
                    view_count = view_count + 1,
                    last_viewed = NOW()
            """  # nosec
            cursor.execute(query, (stamp_id,))
            db.commit()
            logger.debug(f"Incremented view count for stamp {stamp_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error incrementing view count for stamp {stamp_id}: {e}")
        raise DatabaseInsertError(f"Failed to increment view count for stamp {stamp_id}: {e}")


def get_stamp_view_count(db: Connection, stamp_id: int) -> int:
    """
    Get the current view count for a specific stamp.

    Args:
        db: Database connection
        stamp_id: The stamp ID to get view count for

    Returns:
        The current view count (0 if stamp has no views recorded)
    """
    try:
        with db.cursor() as cursor:
            query = f"""
                SELECT view_count
                FROM {STAMP_VIEWS_TABLE}
                WHERE stamp = %s
            """  # nosec
            cursor.execute(query, (stamp_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting view count for stamp {stamp_id}: {e}")
        return 0


def get_popular_stamps(db: Connection, limit: int = 10) -> List[Tuple[int, int]]:
    """
    Get the most popular stamps by view count.

    Args:
        db: Database connection
        limit: Maximum number of stamps to return (default: 10)

    Returns:
        List of tuples (stamp_id, view_count) ordered by view count descending
    """
    try:
        with db.cursor() as cursor:
            query = f"""
                SELECT stamp, view_count
                FROM {STAMP_VIEWS_TABLE}
                ORDER BY view_count DESC, last_viewed DESC
                LIMIT %s
            """  # nosec
            cursor.execute(query, (limit,))
            return list(cursor.fetchall())
    except Exception as e:
        logger.error(f"Error getting popular stamps: {e}")
        return []


def get_recently_viewed_stamps(db: Connection, limit: int = 10) -> List[Tuple[int, int]]:
    """
    Get the most recently viewed stamps.

    Args:
        db: Database connection
        limit: Maximum number of stamps to return (default: 10)

    Returns:
        List of tuples (stamp_id, view_count) ordered by last_viewed descending
    """
    try:
        with db.cursor() as cursor:
            query = f"""
                SELECT stamp, view_count
                FROM {STAMP_VIEWS_TABLE}
                ORDER BY last_viewed DESC
                LIMIT %s
            """  # nosec
            cursor.execute(query, (limit,))
            return list(cursor.fetchall())
    except Exception as e:
        logger.error(f"Error getting recently viewed stamps: {e}")
        return []


def get_stamp_view_stats(db: Connection) -> Dict[str, Any]:
    """
    Get overall statistics about stamp views.

    Args:
        db: Database connection

    Returns:
        Dictionary with statistics: total_stamps_with_views, total_views, avg_views_per_stamp
    """
    try:
        with db.cursor() as cursor:
            query = f"""
                SELECT
                    COUNT(*) as total_stamps_with_views,
                    SUM(view_count) as total_views,
                    AVG(view_count) as avg_views_per_stamp
                FROM {STAMP_VIEWS_TABLE}
                WHERE view_count > 0
            """  # nosec
            cursor.execute(query)
            result = cursor.fetchone()

            if result:
                return {
                    "total_stamps_with_views": int(result[0]) if result[0] else 0,
                    "total_views": int(result[1]) if result[1] else 0,
                    "avg_views_per_stamp": float(result[2]) if result[2] else 0.0,
                }
            else:
                return {"total_stamps_with_views": 0, "total_views": 0, "avg_views_per_stamp": 0.0}
    except Exception as e:
        logger.error(f"Error getting stamp view statistics: {e}")
        return {"total_stamps_with_views": 0, "total_views": 0, "avg_views_per_stamp": 0.0}


# =====================================================================
# MARKET DATA ACCESS FUNCTIONS
# =====================================================================
# These functions provide direct database access for market data operations
# and complement the MarketDataService for external API integrations
# =====================================================================


def get_stamp_market_data_raw(db: Connection, cpid: str) -> Optional[Tuple]:
    """
    Get raw stamp market data from database.

    Args:
        db: Database connection
        cpid: Counterparty asset ID

    Returns:
        Raw database row or None if not found
    """
    try:
        with db.cursor() as cursor:
            query = """
                SELECT
                    cpid, floor_price_btc, recent_sale_price_btc,
                    open_dispensers_count, closed_dispensers_count, total_dispensers_count,
                    holder_count, unique_holder_count, top_holder_percentage, holder_distribution_score,
                    volume_24h_btc, volume_7d_btc, volume_30d_btc, total_volume_btc,
                    price_source, volume_sources, data_quality_score, confidence_level,
                    last_updated, last_dispenser_block, last_balance_block, last_price_update,
                    update_frequency_minutes, created_at
                FROM stamp_market_data
                WHERE cpid = %s
            """  # nosec
            cursor.execute(query, (cpid,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting raw stamp market data for {cpid}: {e}")
        return None


def get_src20_market_data_raw(db: Connection, tick: str) -> Optional[Tuple]:
    """
    Get raw SRC-20 market data from database.

    Args:
        db: Database connection
        tick: SRC-20 token ticker

    Returns:
        Raw database row or None if not found
    """
    try:
        with db.cursor() as cursor:
            query = """
                SELECT
                    tick, price_btc, price_usd, floor_price_btc, market_cap_btc, market_cap_usd,
                    volume_24h_btc, volume_7d_btc, volume_30d_btc, total_volume_btc,
                    price_change_24h_percent, price_change_7d_percent, price_change_30d_percent,
                    holder_count, circulating_supply, max_supply,
                    primary_exchange, exchange_sources, data_quality_score, confidence_level,
                    last_updated, last_price_update, update_frequency_minutes, created_at
                FROM src20_market_data
                WHERE tick = %s
            """  # nosec
            cursor.execute(query, (tick,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting raw SRC-20 market data for {tick}: {e}")
        return None


def insert_stamp_market_data(db: Connection, market_data: Dict[str, Any]) -> None:
    """
    Insert or update stamp market data in the database.

    Args:
        db: Database connection
        market_data: Dictionary containing market data fields
    """
    try:
        with db.cursor() as cursor:
            # Build dynamic insert/update query
            fields = []
            values = []
            update_fields = []

            # Required field
            cpid = market_data.get("cpid")
            if not cpid:
                raise ValueError("cpid is required for stamp market data")

            # Map of allowed fields
            field_mapping = {
                "floor_price_btc": "floor_price_btc",
                "recent_sale_price_btc": "recent_sale_price_btc",
                "open_dispensers_count": "open_dispensers_count",
                "closed_dispensers_count": "closed_dispensers_count",
                "total_dispensers_count": "total_dispensers_count",
                "holder_count": "holder_count",
                "unique_holder_count": "unique_holder_count",
                "top_holder_percentage": "top_holder_percentage",
                "holder_distribution_score": "holder_distribution_score",
                "volume_24h_btc": "volume_24h_btc",
                "volume_7d_btc": "volume_7d_btc",
                "volume_30d_btc": "volume_30d_btc",
                "total_volume_btc": "total_volume_btc",
                "price_source": "price_source",
                "volume_sources": "volume_sources",
                "data_quality_score": "data_quality_score",
                "confidence_level": "confidence_level",
                "last_dispenser_block": "last_dispenser_block",
                "last_balance_block": "last_balance_block",
                "last_price_update": "last_price_update",
                "update_frequency_minutes": "update_frequency_minutes",
            }

            # Build field lists
            fields.append("cpid")
            values.append(cpid)

            for field, db_field in field_mapping.items():
                if field in market_data:
                    fields.append(db_field)
                    values.append(market_data[field])
                    update_fields.append(f"{db_field} = VALUES({db_field})")

            # Add timestamps
            fields.extend(["last_updated", "created_at"])
            values.extend([None, None])  # Will be replaced by NOW()
            update_fields.append("last_updated = NOW()")

            # Build query
            placeholders = ", ".join(["%s"] * (len(fields) - 2)) + ", NOW(), NOW()"
            field_list = ", ".join(fields)
            update_clause = ", ".join(update_fields)

            query = f"""
                INSERT INTO stamp_market_data ({field_list})
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE {update_clause}
            """  # nosec

            cursor.execute(query, values[:-2])  # Exclude the None values for timestamps
            db.commit()
            logger.debug(f"Inserted/updated stamp market data for: {cpid}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting stamp market data for {cpid}: {e}")
        raise DatabaseInsertError(f"Failed to insert stamp market data: {e}")


def insert_src20_market_data(db: Connection, market_data: Dict[str, Any]) -> None:
    """
    Insert or update SRC-20 market data in the database.

    Args:
        db: Database connection
        market_data: Dictionary containing market data fields
    """
    try:
        with db.cursor() as cursor:
            # Build dynamic insert/update query
            fields = []
            values = []
            update_fields = []

            # Required field
            tick = market_data.get("tick")
            if not tick:
                raise ValueError("tick is required for SRC-20 market data")

            # Map of allowed fields
            field_mapping = {
                "price_btc": "price_btc",
                "price_usd": "price_usd",
                "floor_price_btc": "floor_price_btc",
                "market_cap_btc": "market_cap_btc",
                "market_cap_usd": "market_cap_usd",
                "volume_24h_btc": "volume_24h_btc",
                "volume_7d_btc": "volume_7d_btc",
                "volume_30d_btc": "volume_30d_btc",
                "total_volume_btc": "total_volume_btc",
                "price_change_24h_percent": "price_change_24h_percent",
                "price_change_7d_percent": "price_change_7d_percent",
                "price_change_30d_percent": "price_change_30d_percent",
                "holder_count": "holder_count",
                "circulating_supply": "circulating_supply",
                "max_supply": "max_supply",
                "primary_exchange": "primary_exchange",
                "exchange_sources": "exchange_sources",
                "data_quality_score": "data_quality_score",
                "confidence_level": "confidence_level",
                "last_price_update": "last_price_update",
                "update_frequency_minutes": "update_frequency_minutes",
            }

            # Build field lists
            fields.append("tick")
            values.append(tick)

            for field, db_field in field_mapping.items():
                if field in market_data:
                    fields.append(db_field)
                    values.append(market_data[field])
                    update_fields.append(f"{db_field} = VALUES({db_field})")

            # Add timestamps
            fields.extend(["last_updated", "created_at"])
            values.extend([None, None])  # Will be replaced by NOW()
            update_fields.append("last_updated = NOW()")

            # Build query
            placeholders = ", ".join(["%s"] * (len(fields) - 2)) + ", NOW(), NOW()"
            field_list = ", ".join(fields)
            update_clause = ", ".join(update_fields)

            query = f"""
                INSERT INTO src20_market_data ({field_list})
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE {update_clause}
            """  # nosec

            cursor.execute(query, values[:-2])  # Exclude the None values for timestamps
            db.commit()
            logger.debug(f"Inserted/updated SRC-20 market data for: {tick}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting SRC-20 market data for {tick}: {e}")
        raise DatabaseInsertError(f"Failed to insert SRC-20 market data: {e}")


def get_stamp_holders_raw(db: Connection, cpid: str, limit: int = 100) -> List[Tuple]:
    """
    Get raw stamp holder data from database.

    Args:
        db: Database connection
        cpid: Counterparty asset ID
        limit: Maximum number of holders to return

    Returns:
        List of raw database rows
    """
    try:
        with db.cursor() as cursor:
            query = """
                SELECT
                    cpid, address, quantity, percentage, rank_position,
                    balance_source, last_updated, last_tx_block
                FROM stamp_holder_cache
                WHERE cpid = %s
                ORDER BY rank_position ASC
                LIMIT %s
            """  # nosec
            cursor.execute(query, (cpid, limit))
            return list(cursor.fetchall())
    except Exception as e:
        logger.error(f"Error getting raw stamp holders for {cpid}: {e}")
        return []


def insert_stamp_holder_data(db: Connection, holder_data: Dict[str, Any]) -> None:
    """
    Insert or update stamp holder data in the database.

    Args:
        db: Database connection
        holder_data: Dictionary containing holder data fields
    """
    try:
        with db.cursor() as cursor:
            # Required fields
            cpid = holder_data.get("cpid")
            address = holder_data.get("address")
            if not cpid or not address:
                raise ValueError("cpid and address are required for stamp holder data")

            query = """
                INSERT INTO stamp_holder_cache (
                    cpid, address, quantity, percentage, rank_position,
                    balance_source, last_updated, last_tx_block
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                ON DUPLICATE KEY UPDATE
                    quantity = VALUES(quantity),
                    percentage = VALUES(percentage),
                    rank_position = VALUES(rank_position),
                    balance_source = VALUES(balance_source),
                    last_updated = NOW(),
                    last_tx_block = VALUES(last_tx_block)
            """  # nosec

            values = (
                cpid,
                address,
                holder_data.get("quantity", 0),
                holder_data.get("percentage", 0),
                holder_data.get("rank_position", 0),
                holder_data.get("balance_source", "counterparty"),
                holder_data.get("last_tx_block"),
            )

            cursor.execute(query, values)
            db.commit()
            logger.debug(f"Inserted/updated holder data for {cpid}:{address}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting holder data for {cpid}:{address}: {e}")
        raise DatabaseInsertError(f"Failed to insert holder data: {e}")


def get_market_data_sources(db: Connection, asset_type: Optional[str] = None, asset_id: Optional[str] = None) -> List[Tuple]:
    """
    Get market data sources from database.

    Args:
        db: Database connection
        asset_type: Optional filter by asset type ('stamp' or 'src20')
        asset_id: Optional filter by asset ID

    Returns:
        List of raw database rows
    """
    try:
        with db.cursor() as cursor:
            where_conditions = []
            params = []

            if asset_type:
                where_conditions.append("asset_type = %s")
                params.append(asset_type)

            if asset_id:
                where_conditions.append("asset_id = %s")
                params.append(asset_id)

            where_clause = ""
            if where_conditions:
                where_clause = "WHERE " + " AND ".join(where_conditions)

            query = f"""
                SELECT
                    id, asset_type, asset_id, source_name,
                    price_btc, volume_24h_btc, holder_count, market_cap_btc,
                    source_confidence, api_response_time_ms, success_rate_24h,
                    last_success, last_failure, consecutive_failures,
                    last_updated, update_count_24h, created_at
                FROM market_data_sources
                {where_clause}
                ORDER BY source_confidence DESC, success_rate_24h DESC
            """  # nosec

            cursor.execute(query, params)
            return list(cursor.fetchall())
    except Exception as e:
        logger.error(f"Error getting market data sources: {e}")
        return []


def insert_market_data_source(db: Connection, source_data: Dict[str, Any]) -> None:
    """
    Insert or update market data source information.

    Args:
        db: Database connection
        source_data: Dictionary containing source data fields
    """
    try:
        with db.cursor() as cursor:
            # Required fields
            asset_type = source_data.get("asset_type")
            asset_id = source_data.get("asset_id")
            source_name = source_data.get("source_name")

            if not all([asset_type, asset_id, source_name]):
                raise ValueError("asset_type, asset_id, and source_name are required")

            query = """
                INSERT INTO market_data_sources (
                    asset_type, asset_id, source_name,
                    price_btc, volume_24h_btc, holder_count, market_cap_btc,
                    source_confidence, api_response_time_ms, success_rate_24h,
                    last_success, last_failure, consecutive_failures,
                    last_updated, update_count_24h, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, NOW()
                )
                ON DUPLICATE KEY UPDATE
                    price_btc = VALUES(price_btc),
                    volume_24h_btc = VALUES(volume_24h_btc),
                    holder_count = VALUES(holder_count),
                    market_cap_btc = VALUES(market_cap_btc),
                    source_confidence = VALUES(source_confidence),
                    api_response_time_ms = VALUES(api_response_time_ms),
                    success_rate_24h = VALUES(success_rate_24h),
                    last_success = VALUES(last_success),
                    last_failure = VALUES(last_failure),
                    consecutive_failures = VALUES(consecutive_failures),
                    last_updated = NOW(),
                    update_count_24h = VALUES(update_count_24h)
            """  # nosec

            values = (
                asset_type,
                asset_id,
                source_name,
                source_data.get("price_btc"),
                source_data.get("volume_24h_btc", 0),
                source_data.get("holder_count", 0),
                source_data.get("market_cap_btc", 0),
                source_data.get("source_confidence", 5.0),
                source_data.get("api_response_time_ms", 0),
                source_data.get("success_rate_24h", 100.0),
                source_data.get("last_success"),
                source_data.get("last_failure"),
                source_data.get("consecutive_failures", 0),
                source_data.get("update_count_24h", 0),
            )

            cursor.execute(query, values)
            db.commit()
            logger.debug(f"Inserted/updated market data source: {asset_type}:{asset_id}:{source_name}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error inserting market data source: {e}")
        raise DatabaseInsertError(f"Failed to insert market data source: {e}")


def get_stamps_needing_market_update(db: Connection, update_interval_minutes: int, limit: int) -> List[str]:
    """
    Get list of stamp CPIDs that need market data updates.
    Includes stamps with ident='STAMP' or ident='SRC-721'.

    Args:
        db: Database connection
        update_interval_minutes: Minutes since last update
        limit: Maximum number of stamps to return

    Returns:
        List of CPIDs needing updates
    """
    try:
        with db.cursor() as cursor:
            # Include stamps with ident='STAMP' or 'SRC-721'
            # Named assets like FUCKTHAT already have ident='STAMP'
            query = """
                SELECT DISTINCT s.cpid, s.block_index
                FROM StampTableV4 s
                LEFT JOIN stamp_market_data smd ON s.cpid = smd.cpid
                WHERE s.ident IN ('STAMP', 'SRC-721')
                AND (
                    smd.last_updated IS NULL
                    OR smd.last_updated < DATE_SUB(NOW(), INTERVAL %s MINUTE)
                )
                ORDER BY s.block_index DESC
                LIMIT %s
            """  # nosec

            cursor.execute(query, (update_interval_minutes, limit))
            results = cursor.fetchall()
            return [row[0] for row in results]

    except Exception as e:
        logger.error(f"Error getting stamps needing market update: {e}")
        return []


def get_trending_stamps(db: Connection, limit: int = 20) -> List[Tuple]:
    """
    Get trending stamps using the optimized view.

    Args:
        db: Database connection
        limit: Maximum number of stamps to return

    Returns:
        List of tuples with trending stamp data
    """
    try:
        with db.cursor() as cursor:
            query = """
                SELECT
                    cpid, stamp, creator, floor_price_btc, holder_count,
                    volume_24h_btc, volume_7d_btc, holder_distribution_score,
                    trending_score
                FROM v_trending_stamps
                LIMIT %s
            """  # nosec
            cursor.execute(query, (limit,))
            return list(cursor.fetchall())
    except Exception as e:
        logger.error(f"Error getting trending stamps: {e}")
        return []


def get_stamp_market_overview(db: Connection, limit: int = 100) -> List[Tuple]:
    """
    Get stamp market overview using the optimized view.

    Args:
        db: Database connection
        limit: Maximum number of stamps to return

    Returns:
        List of tuples with market overview data
    """
    try:
        with db.cursor() as cursor:
            query = """
                SELECT
                    cpid, stamp, creator, stamp_url, stamp_mimetype,
                    floor_price_btc, holder_count, volume_24h_btc,
                    data_quality_score, last_updated, cache_status
                FROM v_stamp_market_overview
                LIMIT %s
            """  # nosec
            cursor.execute(query, (limit,))
            return list(cursor.fetchall())
    except Exception as e:
        logger.error(f"Error getting stamp market overview: {e}")
        return []


def import_csv_data(cursor, csv_url, insert_query, is_url=False):
    """Import CSV data from URL or local file with ETag caching."""
    max_int = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_int)
            break
        except OverflowError:
            max_int = int(max_int / 10)

    if not is_url:
        # Handle local file case (unchanged)
        with open(csv_url, "r") as file:
            csv_reader = csv.reader(file)
            for row in csv_reader:
                cursor.execute(insert_query, tuple(row))
        return

    # Handle URL case with ETag checking
    try:
        filename = Path(csv_url).name
        etag_file = CACHE_DIR / f".{filename}.etag"
        headers = {}
        current_etag = None

        if etag_file.exists():
            try:
                current_etag = etag_file.read_text().strip()
                if current_etag:
                    headers["If-None-Match"] = current_etag
                    logger.debug(f"Found local ETag for {filename}: '{current_etag}'")
                else:
                    logger.debug(f"ETag file {etag_file} was empty.")
            except Exception as e:
                logger.warning(f"Could not read ETag file {etag_file}: {e}")
        else:
            logger.debug(f"ETag file {etag_file} not found.")

        logger.info(f"Checking bootstrap data from {csv_url}")
        logger.debug(f"Sending request headers: {headers}")
        response = requests.get(csv_url, headers=headers, timeout=config.REQUESTS_TIMEOUT)
        logger.debug(f"Received response status: {response.status_code}")
        logger.debug(f"Received response headers: {response.headers}")

        if response.status_code == 304:
            logger.info(f"Bootstrap data for {filename} is unchanged (ETag: {current_etag}). Skipping download/processing.")
            return  # File hasn't changed, nothing more to do

        response.raise_for_status()  # Raise an exception for other HTTP errors (4xx, 5xx)

        # Process the CSV data if status code was 200 OK
        logger.info(f"Processing bootstrap data from {csv_url} (ETag: {response.headers.get('ETag') or 'None'})")
        new_etag = response.headers.get("ETag")
        logger.debug(f"Received new ETag from server: '{new_etag}'")
        csv_reader = csv.reader(response.text.splitlines())

        # Execute the insert_query for each row.
        # The query itself (passed as argument) handles INSERT or UPDATE logic.
        rows_processed = 0
        for row in csv_reader:
            # Skip empty rows if any
            if not any(field.strip() for field in row):
                continue
            try:
                cursor.execute(insert_query, tuple(row))
                rows_processed += 1
            except Exception as e:
                logger.error(f"Error processing row {row} from {filename}: {e}")
                # Decide if you want to continue or raise the exception
                # raise # Uncomment to stop processing on the first error
                continue  # Comment out to stop processing on the first error

        logger.info(f"Finished processing {rows_processed} rows from {filename}")

        # Save the new ETag
        if new_etag:
            try:
                etag_file.write_text(new_etag)
                logger.debug(f"Saved new ETag '{new_etag}' to {etag_file}")
            except Exception as e:
                logger.warning(f"Could not write ETag file {etag_file}: {e}")
        elif current_etag:  # If server didn't send ETag, remove old one
            logger.debug(f"Server did not send ETag for {filename}. Removing local ETag file {etag_file}.")
            try:
                etag_file.unlink()
            except OSError as e:
                logger.warning(f"Could not remove ETag file {etag_file}: {e}")

    except requests.RequestException as e:
        logger.error(f"Error checking/downloading bootstrap data from {csv_url}: {e}")
        # Optionally: Add logic here to use a cached local version if download fails
        raise


def initialize_tables(db):
    """Initialize database tables from schema file."""
    try:
        logger.info("initializing tables...")
        cursor = db.cursor()

        # Check if tables already exist to avoid unnecessary schema execution
        required_tables = [
            "blocks",
            "transactions",
            "StampTableV4",
            "srcbackground",
            "creator",
            "SRC20",
            "SRC20Valid",
            "balances",
            "s3objects",
            "collections",
            "collection_creators",
            "collection_stamps",
            "src20_metadata",
            "SRC101",
            "SRC101Valid",
            "owners",
            "recipients",
            "src101price",
            "src20_token_stats",
            "stamp_views",
            # Enhanced Market Data Cache Tables
            "stamp_market_data",
            "stamp_holder_cache",
            "market_data_sources",
            "src20_market_data",
            "collection_market_data",
        ]

        # Quick check if all tables exist
        cursor.execute(
            """
            SELECT COUNT(*) as table_count
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name IN ({})
        """.format(
                ",".join(["%s"] * len(required_tables))
            ),
            required_tables,
        )

        existing_count = cursor.fetchone()[0]

        if existing_count == len(required_tables):
            logger.info(f"All {len(required_tables)} required tables already exist, skipping schema execution")
        else:
            logger.info(f"Found {existing_count}/{len(required_tables)} tables, executing schema...")
            # Get the path to table_schema.sql relative to this file
            schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "table_schema.sql")
            with open(schema_path, "r") as file:
                sql_script = file.read()
            sql_commands = [cmd.strip() for cmd in sql_script.split(";") if cmd.strip()]
            for command in sql_commands:
                try:
                    db_manager.execute_with_retry(cursor, command)
                except Exception as e:
                    logger.error(f"Error executing command:{command};\nerror:{e}")
                    raise e

        import_csv_data(
            cursor,
            config.BOOTSTRAP_CREATOR_CSV_URL,
            """
            INSERT INTO creator (address, creator)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE creator = VALUES(creator)
            """,
            is_url=True,
        )
        import_csv_data(
            cursor,
            config.BOOTSTRAP_SRCBACKGROUND_CSV_URL,
            """INSERT INTO srcbackground
            (tick, tick_hash, base64, font_size, text_color, unicode, p)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            base64 = VALUES(base64),
            font_size = VALUES(font_size),
            text_color = VALUES(text_color),
            unicode = VALUES(unicode),
            p = VALUES(p)""",
            is_url=True,
        )
        db.commit()
        cursor.close()
    except Exception as e:
        logger.error("Error initializing tables: {}".format(e))
        raise e


def initialize_db():
    """Initialize database connection and tables."""
    logger.info("Initializing database...")
    if config.FORCE:
        logger.warning("THE OPTION `--force` IS NOT FOR USE ON PRODUCTION SYSTEMS.")

    max_retries = 5
    retry_delay = 5
    attempt = 0

    while attempt < max_retries:
        try:
            # Get connection from database manager
            db = db_manager.connect()

            # Test connection first
            with db.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
                logger.info("Successfully connected to database server")

            # Now try to create and use the database
            with db.cursor() as cursor:
                database_name = os.environ.get("RDS_DATABASE", "btc_stamps")
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
                cursor.execute(f"USE `{database_name}`")
                db.commit()
                logger.info(f"Successfully initialized database: {database_name}")

            util.CURRENT_BLOCK_INDEX = last_db_index(db)

            # Initialize tables from schema
            initialize_tables(db)

            return db

        except Exception as e:
            attempt += 1
            if attempt >= max_retries:
                logger.error(f"Failed to initialize database after {max_retries} attempts: {e}")
                raise
            else:
                logger.warning(f"Database initialization attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
