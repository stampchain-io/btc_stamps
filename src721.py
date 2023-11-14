
import textwrap

## Initial copy of SRC-721 related functions


def query_tokens_custom(token, mysql_conn):
    # TODO: Populate the srcbackground image table - either through a stampchain API call, or a bootstrap file
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

def get_src721_svg_string(src721_title, src721_desc):
    custom_background_result, text_color, font_size = query_tokens_custom('SRC721', mysql_conn)
    # print(f"SRC-721: {asset}, {tx_hash}, {tick_value}, {p_val}, {text_color}, {font_size}")
    svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420">
        <foreignObject font-size="{font_size}" width="100%" height="100%">
        <p xmlns="http://www.w3.org/1999/xhtml" style="background-image: url(data:{custom_background_result});color:{text_color};padding:20px;margin:0px;width:1000px;height:1000px;"><pre></pre></p>
        </foreignObject><title>{src721_title}</title><desc>{src721_desc} - provided by stampchain.io</desc>
        </svg>"""
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

def get_src721_svg_string(src721_title, src721_desc):
    custom_background_result, text_color, font_size = query_tokens_custom('SRC721', mysql_conn)
    # print(f"SRC-721: {asset}, {tx_hash}, {tick_value}, {p_val}, {text_color}, {font_size}")
    svg_output = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420">
        <foreignObject font-size="{font_size}" width="100%" height="100%">
        <p xmlns="http://www.w3.org/1999/xhtml" style="background-image: url(data:{custom_background_result});color:{text_color};padding:20px;margin:0px;width:1000px;height:1000px;"><pre></pre></p>
        </foreignObject><title>{src721_title}</title><desc>{src721_desc} - provided by stampchain.io</desc>
        </svg>"""
    return svg_output
