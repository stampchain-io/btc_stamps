import textwrap
import logging
import copy
import json
import config
from src.database import get_srcbackground_data

logger = logging.getLogger(__name__)


def parse_valid_src721_in_block(valid_stamps_in_block):
    valid_src721_in_block = []
    for stamp in valid_stamps_in_block:
        if stamp.get("op", "").upper() == "DEPLOY":
            valid_src721_in_block.append(stamp)
    return valid_src721_in_block


def validate_src721_and_process(src721_json, valid_stamps_in_block, db):
    if valid_stamps_in_block:
        valid_src721_in_block = parse_valid_src721_in_block(valid_stamps_in_block)
    else:
        valid_src721_in_block = []
    src721_json = convert_to_dict(src721_json)
    op_val = src721_json.get("op", "").upper()
    file_suffix = None
    if 'symbol' in src721_json:
        src721_json['tick'] = src721_json.pop('symbol')
    if op_val == "MINT":
        svg_output = create_src721_mint_svg(src721_json, valid_src721_in_block, db)
        file_suffix = 'svg'
    elif op_val == "DEPLOY":
        deploy_description = src721_json.get("description", None)
        deploy_name = src721_json.get("name", None)
        svg_output = get_src721_svg_string(
            deploy_name,
            deploy_description,
            db
        )
        file_suffix = 'svg'
    else:
        svg_output = get_src721_svg_string("SRC721", config.DOMAINNAME, db)
        file_suffix = 'svg'
    return svg_output.encode('utf-8'), file_suffix


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


def fetch_src721_subasset_base64(asset_name, valid_src721_in_block, db):
    if asset_name in fetch_src721_subasset_base64.cache:
        return fetch_src721_subasset_base64.cache[asset_name]
    collection_sub_asset_base64 = None
    collection_sub_asset_base64 = next((item for item in valid_src721_in_block if item["cpid"] == asset_name), None)
    if collection_sub_asset_base64 is not None and collection_sub_asset_base64["stamp_base64"] is not None:
        return collection_sub_asset_base64["stamp_base64"]
    else:
        # Fetch the asset from the database
        with db.cursor() as cursor:
            sql = f"SELECT stamp_base64 FROM {config.STAMP_TABLE} WHERE cpid = %s"
            cursor.execute(sql, (asset_name,))
            result = cursor.fetchone()
            if result:
                base64_string = result[0]
            else:
                raise RuntimeError(f"Failed to fetch asset src-721 base64 {asset_name} from database")

    fetch_src721_subasset_base64.cache[asset_name] = base64_string

    return base64_string


fetch_src721_subasset_base64.cache = {}


def fetch_src721_collection(tmp_collection_object, valid_src721_in_block, db):
    """
    Fetches the src721 collection by adding the tx-img key to the collection object.

    Args:
        tmp_collection_object (dict): The temporary collection object.
        json_list (list): The list of JSON objects.
        db: The database connection object.

    Returns:
        dict: The updated collection object with the tx-img key.
    """
    output_object = copy.deepcopy(tmp_collection_object)

    for i in range(10):
        key = f"t{i}"
        if key in output_object:
            img_key = f"{key}-img"
            output_object[img_key] = []
            for j, asset_name in enumerate(output_object[key]):
                logger.debug(f"--- Loading t[{i}][{j}]")
                try:
                    img_data = fetch_src721_subasset_base64(asset_name, valid_src721_in_block, db)
                    output_object[img_key].append(img_data)
                except Exception as e:
                    logging.exception('An error occurred during execution', e, stack_info=True, exc_info=True)
                    raise RuntimeError(f"Unable to load t{i}[{j}] {e}")

    return output_object


def get_src721_svg_string(src721_title, src721_desc, db):
    """
    Generate an SVG string for SRC721 with the provided title and description.

    Parameters:
    src721_title (str): The title of the SRC721.
    src721_desc (str): The description of the SRC721.
    db: The database object.

    Returns:
    str: The SVG string representing the SRC721.
    """
    custom_background_result, text_color, font_size = get_srcbackground_data(db, 'SRC721')
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
    """
    Build a stacked SVG string based on the given temporary NFT object and collection object.

    Args:
        tmp_nft_object (dict): Temporary NFT object containing information about the NFT.
        tmp_collection_object (dict): Temporary collection object containing information about the collection.

    Returns:
        str: Stacked SVG string.

    """
    tmp_coll_description = tmp_collection_object.get("description", None)
    tmp_coll_name = tmp_collection_object.get("name", "SRC-721")
    tmp_coll_img_render = tmp_collection_object.get("image-rendering", "pixelated")

    # Initialize the SVG string
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420" style="image-rendering:{tmp_coll_img_render}; width: 420px; height: 420px;">
            <foreignObject width="100%" height="100%">
            <style>img {{position:absolute;width:100%;height:100%;}}</style>
            <title>{tmp_coll_name}</title>

            <desc>{tmp_coll_description} - provided by stampchain.io</desc>
            <div xmlns="http://www.w3.org/1999/xhtml" style="width:420px;height:420px;position:relative;">"""

    for i in range(len(tmp_nft_object["ts"])):
        if tmp_collection_object['t' + str(i) + '-img'] and tmp_nft_object['ts'][i] < len(tmp_collection_object['t' + str(i) + '-img']):
            image_src_base64 = f"{tmp_collection_object['type']},{tmp_collection_object['t' + str(i) + '-img'][tmp_nft_object['ts'][i]]}"
            svg += f'<img src="{image_src_base64}"/>'
        else:
            continue

    svg += "</div></foreignObject></svg>"

    return textwrap.dedent(svg)


def create_src721_mint_svg(src_data, valid_src721_in_block, db):
    """
    Creates an SVG string for a minted SRC-721 token.

    Args:
        src_data (dict): The source data for the minted token.
        db: The database connection object.

    Returns:
        str: The SVG string for the minted token.
    """
    ts = src_data.get('ts', None)
    collection_asset = src_data.get('c')  # this is the CPID of the collection / parent asset
    collection_asset_item = None

    if collection_asset:
        collection_asset_dict = next((item for item in dict(valid_src721_in_block) if item.get("cpid") == collection_asset), None)
        if collection_asset_dict:
            collection_asset_item = collection_asset_dict.get("src_data", None)
        if collection_asset_item is None:
            collection_asset_item = fetch_collection_details(collection_asset, db)
        logger.info("collection_asset_item", collection_asset_item)
        if collection_asset_item is None or collection_asset_item == 'null':
            logger.debug("this is a mint without a v2 collection asset reference")  # DEBUG
            svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, db)
        elif collection_asset_item and ts:
            try:
                src_collection_data = convert_to_dict(collection_asset_item)
                src_collection_data = fetch_src721_collection(src_collection_data, valid_src721_in_block, db)
                svg_output = build_src721_stacked_svg(src_data, src_collection_data)
            except Exception as e:
                logger.warning(f"ERROR: processing SRC-721 data: {e}")
                raise
        else:
            logger.debug("this is a mint without a v2 collection asset reference, or missing ts")  # DEBUG
            svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, db)
    else:
        logger.debug("this is a mint without a collection asset reference")  # DEBUG
        svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, db)
    return svg_output


def fetch_collection_details(collection_cpid, db):
    """
    Fetches the collection asset item from the database.

    Args:
        collection_asset (str): The CPID of the collection / parent asset.
        db: The database connection object.

    Returns:
        str: The collection asset item.
    """
    if collection_cpid in fetch_collection_details.cache:
        return fetch_collection_details.cache[collection_cpid]

    try:
        with db.cursor() as cursor:
            cursor.execute(f"SELECT src_data FROM {config.STAMP_TABLE} WHERE cpid = %s", (collection_cpid,))
            result = cursor.fetchone()
            logger.info(f"asset:{collection_cpid}\nresult: {result}")
            if result is not None and result[0]:
                collection_asset_item = result[0]
                logger.debug(
                    f"collection asset item from db {collection_asset_item}"
                )
            else:
                collection_asset_item = None
                logger.warning("Failed to fetch deploy src_data for cpid from database")
    except Exception as e:
        raise e

    fetch_collection_details.cache[collection_cpid] = collection_asset_item
    return collection_asset_item


fetch_collection_details.cache = {}
