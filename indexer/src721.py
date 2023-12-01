import textwrap
import logging
import copy
import json
import config
from src20 import get_srcbackground_data


logger = logging.getLogger(__name__)


def validate_src721_and_process(src721_data, block_cursor):
    src721_data = convert_to_dict(src721_data)
    op_val = src721_data.get("op", None).upper()
    file_suffix = None
    if 'symbol' in src721_data:
        src721_data['tick'] = src721_data.pop('symbol')
    if op_val == "MINT":
        svg_output = create_src721_mint_svg(src721_data, block_cursor)
        file_suffix = 'svg'
    elif op_val == "DEPLOY":
        deploy_description = src721_data.get("description", None)
        deploy_name = src721_data.get("name", None)
        svg_output = get_src721_svg_string(
            deploy_name,
            deploy_description,
            block_cursor
        )
        file_suffix = 'svg'
    else:
        svg_output = get_src721_svg_string(
            "SRC721",
            config.DOMAINNAME,
            block_cursor
        )
        file_suffix = 'svg'
    return  svg_output.encode('utf-8'), file_suffix


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


def fetch_src721_subasset_base64(asset_name, json_list, block_cursor):
    # check if stamp_base64 is already in the json_list for thc cpid
    collection_sub_asset_base64 = None
    #FIXME: this is the same block query, need to build the json_list, from create_src721_mint_svg
    # collection_sub_asset_base64 = next((item for item in json_list if item["asset"] == asset_name), None)
    # if collection_sub_asset_base64 is not None and collection_sub_asset_base64["stamp_base64"] is not None:
        # print("collection_sub_asset_base64", collection_sub_asset_base64)
        # return collection_sub_asset_base64["stamp_base64"]
    # else:
    try:
        # this assumes the collection asset is already commited to the db... 
        sql = f"SELECT stamp_base64 FROM {config.STAMP_TABLE} WHERE cpid = %s"
        block_cursor.execute(sql, (asset_name,))
        result = block_cursor.fetchone()
        if result:
            return result[0]  # Return the first column of the result (which should be the base64 string)
        else:
            # return None
            raise Exception(f"Failed to fetch asset src-721 base64 {asset_name} from database")
    except Exception as e:
        raise e


def fetch_src721_collection(tmp_collection_object, json_list, block_cursor):
    # this adds the tx-img key to the collection object
    output_object = copy.deepcopy(tmp_collection_object)
    
    for i in range(10):
        key = f"t{i}"
        if key in output_object:
            img_key = f"{key}-img"
            output_object[img_key] = []
            for j, asset_name in enumerate(output_object[key]):
                logger.debug(f"--- Loading t[{i}][{j}]")
                try:
                    # this assumes the image base64 is already in the block_cursor
                    img_data = fetch_src721_subasset_base64(asset_name, json_list, block_cursor)
                    # if img_data:
                    logger.warning(f'''
                        img_data: {img_data}
                        img_key: {img_key}
                        type_img_key: {type(img_key)}
                        output_object: {output_object}
                        i: {i}
                        j: {j}
                        asset_name: {asset_name}
                    ''')
                    output_object[img_key].append(img_data)
                except Exception as e:
                    raise Exception(f"Unable to load t{i}[{j}] {e}")
    # print("output_object collection with base64", output_object)
    return output_object


def get_src721_svg_string(src721_title, src721_desc, block_cursor):
    custom_background_result, text_color, font_size = get_srcbackground_data(
        block_cursor,
        'SRC721',
    )
    # print(f"SRC-721: {asset}, {tx_hash}, {tick_value}, {p_val}, {text_color}, {font_size}")
    svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420">
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
    svg_output = svg_output.replace('\n', '')
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


def create_src721_mint_svg(src_data, block_cursor):
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
                block_cursor.execute(f"SELECT src_data FROM {config.STAMP_TABLE} WHERE cpid = %s", (collection_asset,))
                result = block_cursor.fetchone() # pull the deploy details this one has no src_data when it should A12314949010946956252
                logger.warning(f"asset:{collection_asset}\nresult: {result}")
                if result[0]:
                    collection_asset_item = result[0] # Return the first column of the result
                    logger.debug("got collection asset item from db", collection_asset_item)
                else: 
                    collection_asset_item = None
                    logger.warning(f"Failed to fetch deploy src_data for cpid from database")
                    # raise Exception(f"Failed to fetch deploy src_data for asset {asset} from database")
            except Exception as e:
                raise e
        logger.info("collection_asset_item", collection_asset_item)
        if collection_asset_item is None or collection_asset_item == 'null':
            logger.debug("this is a mint without a v2 collection asset reference") #DEBUG
            svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, block_cursor)
        elif collection_asset_item:
            try:
                src_collection_data = convert_to_dict(collection_asset_item)
                src_collection_data = fetch_src721_collection(src_collection_data, src_data, block_cursor)
                svg_output = build_src721_stacked_svg(src_data, src_collection_data)
            except Exception as e:
                logger.warning(f"ERROR: processing SRC-721 data: {e}")
                raise
        else:
            logger.debug("this is a mint without a v2 collection asset reference") #DEBUG
            svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, block_cursor)
    else:
        logger.debug("this is a mint without a collection asset reference") #DEBUG
        svg_output = get_src721_svg_string("SRC-721", "config.DOMAINNAME", block_cursor)
    return svg_output