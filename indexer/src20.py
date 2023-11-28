
from decimal import Decimal, InvalidOperation
import json
import logging
from config import TICK_PATTERN_LIST

logger = logging.getLogger(__name__)



def build_src20_svg_string(cursor, src_20_dict):
    from src721 import convert_to_dict
    src_20_dict = convert_to_dict(src_20_dict)
    background_base64, font_size, text_color = get_srcbackground_data(cursor, src_20_dict.get('tick'))
    svg_image_data = generate_srcbackground_svg(src_20_dict, background_base64, font_size, text_color)
    return svg_image_data


# query the srcbackground mysql table for these columns tick, base64, font_size, text_color, unicode, p
def get_srcbackground_data(cursor, tick):
    query = "SELECT base64, IFNULL(font_size, '30px') as font_size, IFNULL(text_color, 'white') as text_color FROM srcbackground WHERE UPPER(tick) = UPPER(%s) AND UPPER(p) = UPPER(%s)"
    cursor.execute(query, (tick.upper(), "SRC-20"))
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


def check_format(input_string):
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
                logger.warning("EXCLUSION: did not match tick pattern", input_dict)
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
                                logger.warning(f"EXCLUSION: {key} not a valid decimal: {e}. Input dict: {input_dict}")
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

