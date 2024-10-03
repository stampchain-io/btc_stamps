import copy
import json
import logging
from typing import Any

from cachetools import LRUCache, cached
from cachetools.keys import hashkey

import config
from index_core.database import get_srcbackground_data

logger = logging.getLogger(__name__)

MAX_LAYERS = 10  # Define a maximum number of layers


def parse_valid_src721_in_block(valid_stamps_in_block):
    valid_src721_in_block = []
    for stamp in valid_stamps_in_block:
        if stamp.get("op", "").upper() == "DEPLOY" and stamp.get("is_btc_stamp", False):
            valid_src721_in_block.append(stamp)
    return valid_src721_in_block


def validate_src721_and_process(src721_json, valid_stamps_in_block, db):
    collection_name, collection_description, collection_website, collection_onchain = None, None, None, None
    if valid_stamps_in_block:
        valid_src721_in_block = parse_valid_src721_in_block(valid_stamps_in_block)
    else:
        valid_src721_in_block = []
    src721_json = convert_to_dict(src721_json)
    op_val = src721_json.get("op", "").upper()
    file_suffix, collection_name, collection_description = None, None, None
    if "symbol" in src721_json:
        src721_json["tick"] = src721_json.pop("symbol")
    if op_val == "MINT":
        svg_output, collection_name = create_src721_mint_svg(src721_json, valid_src721_in_block, db)
        file_suffix = "svg"
    elif op_val == "DEPLOY":
        collection_name = src721_json.get("name", None)
        collection_description = src721_json.get("description", None)
        collection_website = src721_json.get("website", None)
        svg_output = get_src721_svg_string(collection_name, collection_description, db)
        file_suffix = "svg"
    else:
        svg_output = get_src721_svg_string("SRC721", config.DOMAINNAME, db)
        file_suffix = "svg"

    # Set collection_onchain to 1 if collection_name is found
    collection_onchain = 1 if collection_name is not None else None

    return (
        svg_output.encode("utf-8"),
        file_suffix,
        collection_name,
        collection_description,
        collection_website,
        collection_onchain,
    )


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


subasset_cache: LRUCache[str, str] = LRUCache(maxsize=256)


@cached(
    subasset_cache,
    key=lambda asset_name, valid_src721_in_block, db: str(hashkey(asset_name)),
)
def fetch_src721_subasset_base64(asset_name: str, valid_src721_in_block: list, db: Any) -> str:
    collection_sub_asset_base64 = next((item for item in valid_src721_in_block if item["cpid"] == asset_name), None)
    if collection_sub_asset_base64 is not None and collection_sub_asset_base64["stamp_base64"] is not None:
        return collection_sub_asset_base64["stamp_base64"]
    else:
        # Fetch the asset from the database
        with db.cursor() as cursor:
            sql = f"SELECT stamp_base64 FROM {config.STAMP_TABLE} WHERE cpid = %s"  # nosec
            cursor.execute(sql, (asset_name,))
            result = cursor.fetchone()
            if result:
                base64_string = result[0]
            else:
                raise RuntimeError(f"Failed to fetch asset src-721 base64 {asset_name} from database")

    return base64_string


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
                    logging.exception(
                        "An error occurred during execution",
                        e,
                        stack_info=True,
                        exc_info=True,
                    )
                    raise RuntimeError(f"Unable to load t{i}[{j}] {e}")

    return output_object


def get_src721_svg_string(src721_title, src721_desc, db):
    """
    Generate a simplified SVG string for SRC721 with the provided title and description.

    Parameters:
    src721_title (str): The title of the SRC721.
    src721_desc (str): The description of the SRC721.
    db: The database object.

    Returns:
    str: The SVG string representing the SRC721.
    """
    custom_background_result, _, _ = get_srcbackground_data(db, "SRC721")
    image_data = custom_background_result

    svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420">
    <image x="0" y="0" width="420" height="420" href="data:image/png;base64,{image_data}"/>
    <title>{src721_title}</title>
    <desc>{src721_desc} - provided by stampchain.io</desc>
</svg>"""

    svg_output = svg_output.replace("\n", "").replace("    ", "")
    return svg_output


def build_src721_stacked_svg(tmp_nft_object, tmp_collection_object):
    """
    Build a stacked SVG string based on the given temporary NFT object and collection object.

    Args:
        tmp_nft_object (dict): Temporary NFT object containing information about the NFT.
        tmp_collection_object (dict): Temporary collection object containing information about the collection.

    Returns:
        tuple: A tuple containing the stacked SVG string and the collection name.
    """
    tmp_coll_description = tmp_collection_object.get("description", "")
    tmp_coll_name = tmp_collection_object.get("name", "SRC-721")
    tmp_coll_img_render = tmp_collection_object.get("image-rendering", "pixelated")

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 420 420" style="image-rendering:{tmp_coll_img_render}; width: 420px; height: 420px;">
    <title>{tmp_coll_name}</title>
    <desc>{tmp_coll_description} - provided by stampchain.io</desc>
    """

    for i, t in enumerate(tmp_nft_object.get("ts", [])):
        if i >= MAX_LAYERS:
            logger.warning(f"Exceeded maximum number of layers ({MAX_LAYERS}). Truncating.")
            break
        img_key = f"t{i}-img"
        if img_key in tmp_collection_object and t < len(tmp_collection_object[img_key]):
            image_src_base64 = tmp_collection_object[img_key][t]
            svg += f'<image x="0" y="0" width="420" height="420" xlink:href="data:image/png;base64,{image_src_base64}"/>'

    svg += "</svg>"
    return svg, tmp_coll_name


def create_src721_mint_svg(src_data, valid_src721_in_block, db):
    """
    Creates an SVG string for a minted SRC-721 token.

    Args:
        src_data (dict): The source data for the minted token.
        db: The database connection object.

    Returns:
        str: The SVG string for the minted token.
    """
    ts = src_data.get("ts", None)
    collection_asset = src_data.get("c")  # this is the CPID of the collection / parent asset
    collection_asset_item, collection_name, svg_output = None, None, None

    if collection_asset:
        collection_asset_dict = next(
            (item for item in valid_src721_in_block if item.get("cpid") == collection_asset),
            None,
        )
        if collection_asset_dict:
            collection_asset_item = collection_asset_dict.get("src_data", None)
        if collection_asset_item is None:
            collection_asset_item = fetch_collection_details(collection_asset, db)
        if collection_asset_item is None or collection_asset_item == "null":
            svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, db)
        elif collection_asset_item and ts:
            try:
                src_collection_data = convert_to_dict(collection_asset_item)
                src_collection_data = fetch_src721_collection(src_collection_data, valid_src721_in_block, db)
                svg_output, collection_name = build_src721_stacked_svg(src_data, src_collection_data)
            except Exception as e:
                logger.warning("ERROR: processing SRC-721 data: %s", e)
                raise
        else:
            logger.debug("this is a mint without a v2 collection asset reference, or missing ts")
            svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, db)
    else:
        logger.debug("this is a mint without a collection asset reference")
        svg_output = get_src721_svg_string("SRC-721", config.DOMAINNAME, db)
    return svg_output, collection_name


collection_cache: LRUCache[str, str] = LRUCache(maxsize=256)


@cached(collection_cache, key=lambda collection_cpid, db: str(hashkey(collection_cpid)))
def fetch_collection_details(collection_cpid: str, db: Any) -> str:
    """
    Fetches the collection asset item from the database.

    Args:
        collection_cpid (str): The CPID of the collection / parent asset.
        db: The database connection object.

    Returns:
        str: The collection asset item.
    """
    try:
        with db.cursor() as cursor:
            cursor.execute(
                f"SELECT src_data FROM {config.STAMP_TABLE} WHERE cpid = %s",
                (collection_cpid,),
            )  # nosec
            result = cursor.fetchone()
            logger.info(f"asset:{collection_cpid}\nresult: {result}")
            if result is not None and result[0]:
                collection_asset_item = result[0]
                logger.debug("got collection asset item from db", collection_asset_item)
            else:
                collection_asset_item = None
                logger.warning("Failed to fetch deploy src_data for cpid from database")
    except Exception as e:
        raise e

    return collection_asset_item
