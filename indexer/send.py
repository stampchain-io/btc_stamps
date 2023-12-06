import logging
logger = logging.getLogger(__name__)


def insert_into_sends_table(db, cursor, send):
    cursor.execute(
        """
        INSERT INTO sends
        (
            `from`, `to`, `cpid`, `tick`, `memo`, `quantity`,
            `tx_hash`, `tx_index`, `block_index`
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            None,
            send.get('source'),
            send.get('cpid', None),
            send.get('tick', None),
            send.get('memo', None),
            send.get('quantity'),
            send.get('tx_hash'),
            send.get('tx_index'),
            send.get('block_index'),
        ),
    )


def insert_into_balances_table(cursor, send, op):
    try:
        if op == 'to':
            operation = '+'
        elif op == 'from':
            operation = '-'
        else:
            raise Exception(f"Invalid operation: {op}")

        address = send.get('to') if op == 'to' else send.get('from')

        cursor.execute(
            """
            SELECT 1 FROM balances
            WHERE `address` = %s AND `cpid` <=> %s AND `tick` <=> %s
            """,
            (
                address,
                send.get('cpid'),
                send.get('tick'),
            )
        )
        result = cursor.fetchone()

        if result:
            if op == 'from':
                cursor.execute(
                    """
                    SELECT `quantity` FROM balances
                    WHERE `address` = %s
                    AND `cpid` <=> %s
                    AND `tick` <=> %s
                    """,
                    (
                        address,
                        send.get('cpid'),
                        send.get('tick'),
                    )
                )
                result = cursor.fetchone()
                if result[0] < send.get('quantity'):
                    raise Exception(
                        f"Not enough balance for {send.get('tx_hash')}"
                    )
                if result[0] == send.get('quantity'):
                    cursor.execute(
                        """
                        DELETE FROM balances
                        WHERE `address` = %s
                        AND `cpid` <=> %s
                        AND `tick` <=> %s
                        """,
                        (
                            address,
                            send.get('cpid'),
                            send.get('tick'),
                        )
                    )
                    return
            cursor.execute(
                f"""
                UPDATE balances
                SET `quantity` = `quantity` {operation} %s, `last_update` = %s
                WHERE `address` = %s
                AND `cpid` <=> %s
                AND `tick` <=> %s
                """,
                (
                    send.get('quantity'),
                    send.get('block_index'),
                    address,
                    send.get('cpid'),
                    send.get('tick'),
                )
            )
        # Si no, inserta
        else:
            cursor.execute(
                """
                INSERT INTO balances
                (
                    `address`,
                    `cpid`,
                    `tick`,
                    `quantity`,
                    `last_update`
                )
                VALUES
                (%s, %s, %s, %s, %s)
                """,
                (
                    address,
                    send.get('cpid'),
                    send.get('tick'),
                    send.get('quantity'),
                    send.get('block_index'),
                )
            )
    except Exception as e:
        logger.error(f"insert_into_balances_table: {e}")
        logger.error(f"{send}")
        raise e


def parse_tx_to_send_table(db, cursor, send, tx):
    try:
        parsed_send = {
            'from': send.get('source'),
            'to': send.get('destination'),
            'cpid': send.get('cpid', None),
            'tick': send.get('tick', None),
            'memo': send.get('memo', None),
            'quantity': send.get('quantity'),
            'tx_hash': send.get('tx_hash'),
            'tx_index': tx.get('tx_index'),
            'block_index': send.get('block_index'),
        }
        insert_into_sends_table(
            db=db,
            cursor=cursor,
            send=parsed_send
        )
        parse_send_to_balance_table_to(
            db=db,
            cursor=cursor,
            send=parsed_send
        )
        parse_send_to_balance_table_from(
            db=db,
            cursor=cursor,
            send=parsed_send
        )
    except Exception as e:
        logger.error(f"parse_tx_to_send_table: {e}")
        logger.error(f"{send}")
        logger.error(f"{tx}")
        raise e


def parse_issuance_to_send_table(db, cursor, issuance, tx):
    if (issuance['quantity'] == 0):
        return
    try:
        parsed_send = {
            'from': None,
            'to': issuance['source'],
            'cpid': issuance.get('cpid', None),
            'tick': issuance.get('tick', None),
            'memo': "issuance",
            'quantity': issuance['quantity'],
            'tx_hash': issuance['tx_hash'],
            'tx_index': tx['tx_index'],
            'block_index': tx['block_index'],
        }
        insert_into_sends_table(
            db=db,
            cursor=cursor,
            send=parsed_send
        )
        parse_send_to_balance_table_to(
            db=db,
            cursor=cursor,
            send=parsed_send
        )
    except Exception as e:
        logger.error(f"parse_issuance_to_send_table: {e}")
        logger.error(f"{issuance}")
        logger.error(f"{tx}")
        raise e


def parse_send_to_balance_table_to(db, cursor, send):
    try:
        insert_into_balances_table(
            cursor=cursor,
            send=send,
            op='to'
        )
    except Exception as e:
        logger.error(f"parse_send_to_balance_table: {e}")
        logger.error(f"{send}")
        raise e


def parse_send_to_balance_table_from(db, cursor, send):
    try:
        insert_into_balances_table(
            cursor=cursor,
            send=send,
            op='from'
        )
    except Exception as e:
        logger.error(f"parse_send_to_balance_table: {e}")
        logger.error(f"{send}")
        raise e
