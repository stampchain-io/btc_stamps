import time

import config
import logging
from send import (
    parse_send_to_balance_table_to,
    parse_send_to_balance_table_from,
)


logger = logging.getLogger(__name__)


def check_balances_table(cursor, block_index):
    """
    Check if block_index is greater than genesis block
    and if balances table is empty so we need to reparse balances
    """
    if block_index > config.CP_STAMP_GENESIS_BLOCK:
        cursor.execute('''SELECT COUNT(*) FROM balances''')
        if cursor.fetchone()[0] == 0:
            return True
    return False


def check_to_reparse_balances(cursor, block_index):
    """
    check if we need to trigger reparse balances table
    """
    reparse_balances = check_balances_table(cursor, block_index)
    if reparse_balances:
        logger.info("Reparse balances table")
        trigger_reparse_balances(cursor)


def parse_send_from_db(send):
    """
    Parse send from database
    """
    return {
        'from': send[0],
        'to': send[1],
        'cpid': send[2],
        'tick': send[3],
        'memo': send[4],
        'satoshirate': send[5],
        'quantity': send[6],
        'tx_hash': send[7],
        'tx_index': send[8],
        'block_index': send[9],
    }


def trigger_reparse_balances(cursor):
    """
    Trigger reparse balances table
        1.- balances table is already dropped
        2.- get all sends from the database ordered by tx_index
        3.- create balances table from all the sends
    """
    cursor.execute(
        """
        SELECT * FROM sends ORDER BY tx_index
        """
    )
    sends = cursor.fetchall()
    logger.warning(f"Reparse balances table from {len(sends)} sends")
    time.sleep(5)
    for send in sends:
        parsed_send = parse_send_from_db(send)
        parse_send_to_balance_table_to(
            cursor=cursor,
            send=parsed_send
        )
        if (parsed_send['from'] is not None):
            parse_send_to_balance_table_from(
                cursor=cursor,
                send=parsed_send
            )
    cursor.execute("COMMIT")
