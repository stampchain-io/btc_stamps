import logging
logger = logging.getLogger(__name__)


def insert_into_sends_table(cursor, send):
    cursor.execute(
        """
        INSERT INTO sends
        (
            `from`, `to`, `cpid`, `tick`, `memo`,`satoshirate`, `quantity`,
            `tx_hash`, `tx_index`, `block_index`
        )
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            send.get('from', None),
            send.get('to'),
            send.get('cpid', None),
            send.get('tick', None),
            send.get('memo', "send"),
            send.get('satoshirate', None),
            send.get('quantity'),
            send.get('tx_hash'),
            send.get('tx_index'),
            send.get('block_index'),
        ),
    )


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
                'satoshirate': send.get('satoshirate', None),
                'tx_hash': send.get('tx_hash'),
                'tx_index': tx.get('tx_index'),
                'block_index': send.get('block_index'),
            }
            insert_into_sends_table(
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


def parse_normal_issuance_to_send_table(cursor, issuance, tx):
    try:
        parsed_send = {
                'from': None,
                'to': issuance.get('issuer'),
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
    except Exception as e:
        logger.error(f"parse_normal_issuance_to_send_table: {e}")
        logger.error(f"{issuance}")
        logger.error(f"{tx}")
        raise e


def parse_issuance_with_transfer_with_quantity_to_send_table(
    cursor, issuance, tx
):
    try:
        parsed_issuance_send = {
            'from': None,
            'to': issuance.get('issuer'),
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
            send=parsed_issuance_send
        )
    except Exception as e:
        logger.error(
            f"parse_issuance_with_transfer_with_quantity_to_send_table: {e}"
        )
        logger.error(f"{issuance}")
        logger.error(f"{tx}")
        raise e


def parse_issuance_to_send_table(db, cursor, issuance, tx):
    if (
        issuance['quantity'] == 0
        and issuance['transfer'] is False
    ):
        return
    try:
        if (
            issuance['issuer'] != issuance['source']
            and issuance['transfer'] is True
            and issuance['quantity'] > 0
        ):
            return parse_issuance_with_transfer_with_quantity_to_send_table(
                cursor=cursor,
                issuance=issuance,
                tx=tx
            )
        elif (
            issuance['issuer'] != issuance['source']
            and issuance['transfer'] is True
            and issuance['quantity'] == 0
        ):
            return
        return parse_normal_issuance_to_send_table(
            cursor=cursor,
            issuance=issuance,
            tx=tx
        )
    except Exception as e:
        logger.error(f"parse_issuance_to_send_table: {e}")
        logger.error(f"{issuance}")
        logger.error(f"{tx}")
        raise e
