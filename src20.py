
from decimal import Decimal
import json
from config import TICK_PATTERN_LIST

''' this is not yet implemented - intended to the src20 items into the srcx table.
    in production this is currently done in the mysql_stv4_to_srcx.py script 
    this will also serve as the basis for the src-20 balance table ''' 


def query_tokens_custom(token, mysql_conn):
    ''' used for pulling the src-20 background images for creation of the image '''
    try:
        with mysql_conn.cursor() as cursor:
            cursor.execute("SELECT base64, text_color, font_size FROM srcbackground WHERE tick = %s", (token.upper(),))
            result = cursor.fetchone()
            if result:
                base64 = result[0]
                text_color = result[1] if result[1] else 'white'
                font_size = result[2] if result[2] else '30px'
                return base64, text_color, font_size
            else:
                return None, 'white', '30px'
    except Exception as e:
        print(f"Error querying database: {e}")
        return None, 'white', '30px'



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

