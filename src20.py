
from decimal import Decimal
import json
from config import TICK_PATTERN_LIST

''' this is not yet implemented - to directly import the src20 items into the srcx table. '''
''' currently done in the mysql_stv4_to_srcx.py script '''

def initialise(db):
    cursor = db.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS src20(
                      tx_index INTEGER PRIMARY KEY,
                      tx_hash TEXT UNIQUE,
                      block_index INTEGER,
                      source TEXT,
                      timestamp INTEGER,
                      value REAL,
                      fee_fraction_int INTEGER,
                      text TEXT,
                      locked BOOL,
                      status TEXT,
                      FOREIGN KEY (tx_index, tx_hash, block_index) REFERENCES transactions(tx_index, tx_hash, block_index))
                   ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS
                      block_index_idx ON broadcasts (block_index)
                   ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS
                      status_source_idx ON broadcasts (status, source)
                   ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS
                      status_source_index_idx ON broadcasts (status, source, tx_index)
                   ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS
                      timestamp_idx ON broadcasts (timestamp)
                   ''')


    # # Connect to the MySQL database
    # mysql_conn = mysql.connect(
    #     host='stamps-1.cluster-cbdenncm0tno.us-east-1.rds.amazonaws.com',
    #     user='admin',
    #     password='qh^PsfK&q9hiSWHz',
    #     port=3306,
    #     database='btc_stamps' # Replace with your database name
    # )

    # # Create the database if it does not exist
    # mysql_cursor = mysql_conn.cursor()


def parse (db, tx, message):
    cursor = db.cursor()

    # Unpack message and validate json string to insert into src20 table
    try:
        if util.enabled('broadcast_pack_text', tx['block_index']):
            timestamp, value, fee_fraction_int, rawtext = struct.unpack(FORMAT + '{}s'.format(len(message) - LENGTH), message)
            textlen = VarIntSerializer.deserialize(rawtext)
            if textlen == 0:
                text = b''
            else:
                text = rawtext[-textlen:]

            assert len(text) == textlen
        else:
            if len(message) - LENGTH <= 52:
                curr_format = FORMAT + '{}p'.format(len(message) - LENGTH)
            else:
                curr_format = FORMAT + '{}s'.format(len(message) - LENGTH)

            timestamp, value, fee_fraction_int, text = struct.unpack(curr_format, message)

        try:
            text = text.decode('utf-8')
        except UnicodeDecodeError:
            text = ''
        status = 'valid'
    except (struct.error) as e:
        timestamp, value, fee_fraction_int, text = 0, None, 0, None
        status = 'invalid: could not unpack'

    if status == 'valid':
        # For SQLite3
        timestamp = min(timestamp, config.MAX_INT)
        value = min(value, config.MAX_INT)

        problems = validate(db, tx['source'], timestamp, value, fee_fraction_int, text, tx['block_index'])
        if problems: status = 'invalid: ' + '; '.join(problems)

    # Lock?
    lock = False
    if text and text.lower() == 'lock':
        lock = True
        timestamp, value, fee_fraction_int, text = 0, None, None, None
    else:
        lock = False

    # Add parsed transaction to message-type–specific table.
    bindings = {
        'tx_index': tx['tx_index'],
        'tx_hash': tx['tx_hash'],
        'block_index': tx['block_index'],
        'source': tx['source'],
        'timestamp': timestamp,
        'value': value,
        'fee_fraction_int': fee_fraction_int,
        'text': text,
        'locked': lock,
        'status': status,
    }
    if "integer overflow" not in status:
        sql = 'insert into broadcasts values(:tx_index, :tx_hash, :block_index, :source, :timestamp, :value, :fee_fraction_int, :text, :locked, :status)'
        cursor.execute(sql, bindings)
    else:
        logger.warn("Not storing [broadcast] tx [%s]: %s" % (tx['tx_hash'], status))
        logger.debug("Bindings: %s" % (json.dumps(bindings), ))

    # stop processing if broadcast is invalid for any reason
    if util.enabled('broadcast_invalid_check') and status != 'valid':
        return

    # Options? Should not fail to parse due to above checks.
    if util.enabled('options_require_memo') and text and text.lower().startswith('options'):
        options = util.parse_options_from_string(text)
        if options is not False:
            op_bindings = {
                        'block_index': tx['block_index'],
                        'address': tx['source'],
                        'options': options
                       }
            sql = 'insert or replace into addresses(address, options, block_index) values(:address, :options, :block_index)'
            cursor = db.cursor()
            cursor.execute(sql, op_bindings)



    # stop processing if broadcast is invalid for any reason
    # @TODO: remove this check once broadcast_invalid_check has been activated
    if util.enabled('max_fee_fraction') and status != 'valid':
        return

    cursor.close()

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4


## This is the matching functions to validate the json strings


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


def check_format(input_string):
    try:
        start_index = input_string.find('{')
        end_index = input_string.rfind('}') + 1
        input_string = input_string[start_index:end_index]
        input_dict = json.loads(input_string)
        if input_dict.get("p") == "src-721":
            return input_dict

        if input_dict.get("p") == "src-20":
            tick_value = input_dict.get("tick")
            if not tick_value or not matches_any_pattern(tick_value, TICK_PATTERN_LIST) or len(tick_value) > 5:
                print("EXCLUSION: did not match tick pattern", input_dict)
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
                            print(input_string)
                            print(f"EXCLUSION: Missing or invalid value for {key}", input_dict)
                            return False

                        if isinstance(value, str):
                            try:
                                value = Decimal(''.join(c for c in value if c.isdigit() or c == '.')) if value else Decimal(0)
                            except ValueError:
                                print(input_string)
                                print(f"EXCLUSION: {key} not a valid decimal", input_dict)
                                return False
                        elif isinstance(value, int):
                            value = Decimal(value)
                        else:
                            print(input_string)
                            print(f"EXCLUSION: {key} not a string or integer", input_dict)
                            return False

                        if not (0 <= value <= uint64_max):
                            print(input_string)
                            print(f"EXCLUSION: {key} not in range", input_dict)
                            return False
            return input_dict

    except json.JSONDecodeError:
        return False

    return False

