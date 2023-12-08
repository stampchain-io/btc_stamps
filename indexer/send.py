import logging
logger = logging.getLogger(__name__)


def insert_into_sends_table(cursor, send):
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
            send.get('from', None),
            send.get('to'),
            send.get('cpid', None),
            send.get('tick', None),
            send.get('memo', "send"),
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
                # FIXME: this is a problem for reorgs as we are not saving
                # prev_quantity and prev_last_update
                # if result[0] == send.get('quantity'):
                #     cursor.execute(
                #         """
                #         DELETE FROM balances
                #         WHERE `address` = %s
                #         AND `cpid` <=> %s
                #         AND `tick` <=> %s
                #         """,
                #         (
                #             address,
                #             send.get('cpid'),
                #             send.get('tick'),
                #         )
                #     )
                #     return
            logger.warning(
                f"""
                Updating balance for {send.get('cpid')} {send.get('quantity')}
                """
            )
            cursor.execute(
                f"""
                UPDATE balances
                SET `prev_last_update` = `last_update`,
                `prev_quantity` = `quantity`,
                `quantity` = `quantity` {operation} %s,
                `last_update` = %s
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


def parse_tx_to_send_table(db, cursor, sends, tx):
    try:
        for send in sends:
            parsed_send = {
                'from': send.get('source'),
                'to': send.get('destination'),
                'cpid': send.get('cpid', None),
                'tick': send.get('tick', None),
                'memo': send.get('memo', "send"),
                'quantity': send.get('quantity'),
                'tx_hash': send.get('tx_hash'),
                'tx_index': tx.get('tx_index'),
                'block_index': send.get('block_index'),
            }
            insert_into_sends_table(
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


def insert_into_dispenser_table(cursor, dispenser):
    cursor.execute(
        """
        INSERT INTO dispensers
        (
            `tx_index`, `tx_hash`, `block_index`, `source`, `origin`,
            `cpid`, `give_quantity`, `escrow_quantity`,
            `satoshirate`, `status`, `give_remaining`,
            `oracle_address`
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            dispenser.get('tx_index'),
            dispenser.get('tx_hash'),
            dispenser.get('block_index'),
            dispenser.get('source'),
            dispenser.get('origin'),
            dispenser.get('cpid'),
            dispenser.get('give_quantity'),
            dispenser.get('escrow_quantity'),
            dispenser.get('satoshirate'),
            dispenser.get('status'),
            dispenser.get('give_remaining'),
            dispenser.get('oracle_address'),
        ),
    )


def parse_tx_to_dispenser_table(db, cursor, dispenser, tx):
    try:
        dispenser['tx_index'] = tx['tx_index']
        insert_into_dispenser_table(
            cursor=cursor,
            dispenser=dispenser
        )
    except Exception as e:
        logger.error(f"parse_tx_to_dispenser_table: {e}")
        logger.error(f"{dispenser}")
        logger.error(f"{tx}")
        raise e


def parse_issuance_to_send_table(db, cursor, issuance, tx):
    if (issuance['quantity'] == 0):
        return
    try:
        parsed_send = {
            'from': None,
            'to': issuance.get('source'),
            'cpid': issuance.get('cpid', None),
            'tick': issuance.get('tick', None),
            'memo': "issuance",
            'quantity': issuance['quantity'],
            'tx_hash': issuance['tx_hash'],
            'tx_index': tx['tx_index'],
            'block_index': tx['block_index'],
        }
        insert_into_sends_table(
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


def parse_src20_issuance_to_send_table(db, cursor, issuance):
    pass
