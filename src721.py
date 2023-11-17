import textwrap
import logging
import copy
import json

logger = logging.getLogger(__name__)

#  Initial copy of SRC-721 related functions


def sort_keys(key):
    priority_keys = ["p", "op", "tick"]
    if key in priority_keys:
        return priority_keys.index(key)
    return len(priority_keys)

# NOTE: we might be able to remove this function. legacy stuff
def convert_to_dict(json_string_or_dict):
    if isinstance(json_string_or_dict, str):
        try:
            return json.loads(json_string_or_dict)
        except json.JSONDecodeError:
            raise ValueError("Input is not a valid JSON-formatted string")
    elif isinstance(json_string_or_dict, dict):
        return json_string_or_dict
    else:
        raise TypeError("Input must be a JSON-formatted string or a Python dictionary object")
    

def query_tokens_custom(token, db):
    # TODO: Populate the srcbackground image table - either through a stampchain API call, or a bootstrap file
    try:
        with db, db.cursor() as src721_cursor:
            src721_cursor.execute(
                '''
                    SELECT base64, text_color, font_size
                    FROM srcbackground
                    WHERE tick = %s
                ''',
                (token.upper(),)
            )
            result = src721_cursor.fetchone()
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


def fetch_src721_subasset_base64(asset_name, json_list, db):
    # check if stamp_base64 is already in the json_list for thc cpid
    collection_sub_asset_base64 = None
    collection_sub_asset_base64 = next((item for item in json_list if item["asset"] == asset_name), None)
    if collection_sub_asset_base64 is not None and collection_sub_asset_base64["stamp_base64"] is not None:
        return collection_sub_asset_base64["stamp_base64"]
    else:
        try:
             with db, db.cursor() as src721_subasset_cursor:
                # this assumes the collection asset is already commited to the db... 
                sql = f"SELECT stamp_base64 FROM StampTableV4 WHERE cpid = %s"
                src721_subasset_cursor.execute(sql, (asset_name,))
                result = src721_subasset_cursor.fetchone()
                if result:
                    return result[0]  # Return the first column of the result (which should be the base64 string)
                else:
                    # return None
                    raise Exception(f"Failed to fetch asset src-721 base64 {asset_name} from database")
        except Exception as e:
            raise e
        finally:
            src721_subasset_cursor.close()


def fetch_src721_collection(tmp_collection_object, json_list, db):
    # this adds the tx-img key to the collection object
    output_object = copy.deepcopy(tmp_collection_object)
    
    for i in range(10):
        key = f"t{i}"
        if key in output_object:
            img_key = f"{key}-img"
            output_object[img_key] = []
            for j, asset_name in enumerate(output_object[key]):
                # print(f"--- Loading t[{i}][{j}]")
                try:
                    # this assumes the image base64 is already in the db
                    img_data = fetch_src721_subasset_base64(asset_name, json_list, db)
                    # if img_data:
                    output_object[img_key].append(img_data)
                except Exception as e:
                    raise Exception(f"Unable to load t{i}[{j}] {e}")
    
    # print("output_object collection with base64", output_object)
    return output_object


def get_src721_svg_string(src721_title, src721_desc, db):
    custom_background_result, text_color, font_size = query_tokens_custom(
        'SRC721',
        db
    )
    # print(f"SRC-721: {asset}, {tx_hash}, {tick_value}, {p_val}, {text_color}, {font_size}")
    svg_output = f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420">
        <foreignObject font-size="{font_size}" width="100%" height="100%">
            <p xmlns="http://www.w3.org/1999/xhtml"
                style="background-image: url(data:{custom_background_result});color:{text_color};padding:20px;margin:0px;width:1000px;height:1000px;">
                <pre></pre>
            </p>
        </foreignObject>
        <title>{src721_title}</title>
        <desc>{src721_desc} - provided by stampchain.io</desc>
    </svg>
    """
    return svg_output


def build_src721_stacked_svg(tmp_nft_object, tmp_collection_object):
    # Initialize the SVG string
    # svg = f'<div><svg xmlns="http://www.w3.org/2000/svg" viewbox="{tmp_collection_object["viewbox"]}" style="image-rendering:{tmp_collection_object["image-rendering"]}">'
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420" style="image-rendering:{tmp_collection_object["image-rendering"]}; width: 420px; height: 420px;">
            <foreignObject width="100%" height="100%">
            <style>img {{position:absolute;width:100%;height:100%;}}</style>
            <title>{tmp_collection_object["name"]}</title>
            <desc>{tmp_collection_object["description"]} - provided by stampchain.io</desc>
            <div xmlns="http://www.w3.org/1999/xhtml" style="width:420px;height:420px;position:relative;">"""

    # Loop to add the image elements
    for i in range(len(tmp_nft_object["ts"])):
        image_src_base64 = f"{tmp_collection_object['type']},{tmp_collection_object['t' + str(i) + '-img'][tmp_nft_object['ts'][i]]}"
        svg += f'<img src="{image_src_base64}"/>'
    
    # Add closing SVG tag
    svg += "</div></foreignObject></svg>"
    
    return textwrap.dedent(svg)


def create_src721_mint_svg(src_data, db):
    tick_value = src_data.get('tick', None).upper() if src_data.get('tick') else None
    collection_asset_item = None
    collection_asset = src_data.get('c') # this is the CPID of the collection / parent asset
    if collection_asset:
        ## FIXME: This is problematic if the collection asset is in the same block because the additional items will not show up in the src_data as in the current indexer
        # get the collection asset from the existing src_data if in the same block 
        # collection_asset_dict = next((item for item in dict(src_data) if item.get("asset") == collection_asset), None)
        # if collection_asset_dict:
            # collection_asset_item = collection_asset_dict.get("src_data", None)
        if collection_asset_item is None:
            # print("collection asset item is not in the src_data - fetching from db") #DEBUG
            try:
                db.ping(reconnect=True)
                cursor = db.cursor()
                cursor.execute("SELECT src_data FROM StampTableV4 WHERE cpid = %s", (collection_asset,))
                result = cursor.fetchone() # pull the deploy details this one has no src_data when it should A12314949010946956252
                logger.warning(f"asset:{collection_asset}\nresult: {result}")
                if result[0]:
                    collection_asset_item = result[0] # Return the first column of the result
                    print("got collection asset item from db", collection_asset_item)
                else: 
                    collection_asset_item = None
                    print(f"Failed to fetch deploy src_data for cpid from database")
                    # raise Exception(f"Failed to fetch deploy src_data for asset {asset} from database")
            except Exception as e:
                raise e
        print("collection_asset_item", collection_asset_item)
        if collection_asset_item is None or collection_asset_item == 'null':
            # print("this is a mint without a v2 collection asset reference") #DEBUG
            svg_output = get_src721_svg_string("SRC-721", "stampchain.io")
        elif collection_asset_item:
            try:
                src_collection_data = convert_to_dict(collection_asset_item)
                src_collection_data = fetch_src721_collection(src_collection_data, src_data, db)
                svg_output = build_src721_stacked_svg(src_data, src_collection_data)
            except Exception as e:
                print(f"ERROR: processing SRC-721 data: {e}")
                raise
        else:
            # print("this is a mint without a v2 collection asset reference") #DEBUG
            svg_output = get_src721_svg_string("SRC-721", "stampchain.io")
    else:
        print("this is a mint without a collection asset reference") #DEBUG
        svg_output = get_src721_svg_string("SRC-721", "stampchain.io")