import os
import regex
import logging
from requests.auth import HTTPBasicAuth
import boto3
import re

logger = logging.getLogger(__name__)

# env vars to be set in docker, or locally if connecting to a local btc and/or cp_node
RPC_USER = os.environ.get("RPC_USER", 'rpc')
RPC_PASSWORD = os.environ.get("RPC_PASSWORD", 'rpc')
RPC_IP = os.environ.get("RPC_IP", '127.0.0.1')
RPC_PORT = os.environ.get("RPC_PORT", '8332')

CP_RPC_URL = os.environ.get("CP_RPC_URL", "https://public.coindaddy.io:4001/api/rest/") # 'http://127.0.0.1:4000/api/'
CP_RPC_USER = os.environ.get("CP_RPC_USER", "rpc")
CP_RPC_PASSWORD = os.environ.get("CP_RPC_PASSWORD", "1234")
CP_AUTH = HTTPBasicAuth(CP_RPC_USER, CP_RPC_PASSWORD)

AWS_ACCESS_KEY_ID=os.environ.get("AWS_ACCESS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY=os.environ.get("AWS_SECRET_ACCESS_KEY", None)

AWS_S3_CLIENT = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )

AWS_CLOUDFRONT_DISTRIBUTION_ID = os.environ.get('AWS_CLOUDFRONT_DISTRIBUTION_ID', None)
AWS_S3_BUCKETNAME = os.environ.get('AWS_S3_BUCKETNAME', None)
AWS_S3_IMAGE_DIR = os.environ.get('AWS_S3_IMAGE_DIR', None)
S3_OBJECTS = []

BLOCKS_TO_KEEP = int(os.environ.get("BLOCKS_TO_KEEP", 0))

# Define for Quicknode or simiilar remote nodes which use a token
QUICKNODE_URL = os.environ.get("QUICKNODE_URL", None)
RPC_TOKEN = os.environ.get("RPC_TOKEN", None)
if QUICKNODE_URL and RPC_TOKEN:
    RPC_URL = f"https://{RPC_USER}:{RPC_PASSWORD}@{QUICKNODE_URL}/{RPC_TOKEN}"
else:
    RPC_URL = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_IP}:{RPC_PORT}"

RPC_BATCH_SIZE = 20     # A 1 MB block can hold about 4200 transactions.

STAMP_TABLE = "StampTableV4"
SRC20_TABLE = "SRC20"
SRC20_VALID_TABLE = "SRC20Valid"
SRC20_BALANCES_TABLE = "SRC20Balances"

DOMAINNAME = os.environ.get("DOMAINNAME", "stampchain.io")
SUPPORTED_SUB_PROTOCOLS = ['SRC-721', 'SRC-20']
INVALID_BTC_STAMP_SUFFIX = ['plain', 'octet-stream', 'js', 'css', 'x-empty', 'json']

CP_STAMP_GENESIS_BLOCK = 779652 # block height of first valid stamp transaction on counterparty
CP_SRC20_BLOCK_END = 796000 # The last SRC-20 on CP  - IGNORE ALL SRC-20 on CP AFTER THIS BLOCK
BMN_BLOCKSTART = 815130 # This is the block where we start looking for BMN audio files

# Consensus changes
STRIP_WHITESPACE = 797200
STOP_BASE64_REPAIR = 784550

# Keep as ref
# BTC_STAMP_GENESIS_BLOCK = 793068 # block height of first stamp (src-20) transaction on btc
# CP_SRC20_BLOCK_START = 788041 # This initial start of SRC-20 on Counterparty
# CP_SRC721_BLOCK_START = 799434
# FIRST_KEYBURN_BLOCK = 784978

TESTNET = None
REGTEST = None

BURNKEYS = [
    "022222222222222222222222222222222222222222222222222222222222222222",
    "033333333333333333333333333333333333333333333333333333333333333333",
    "020202020202020202020202020202020202020202020202020202020202020202",
    "030303030303030303030303030303030303030303030303030303030303030302",
    "030303030303030303030303030303030303030303030303030303030303030303"
]

MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "tif": "image/tiff",
    "jfif": "image/jpeg",
    "jpe": "image/jpeg",
    "pbm": "image/x-portable-bitmap",
    "pgm": "image/x-portable-graymap",
    "ppm": "image/x-portable-pixmap",
    "pnm": "image/x-portable-anymap",
    "apng": "image/apng",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "heif": "image/heif",
    "heic": "image/heic",
    "avif": "image/avif",
    "ico": "image/x-icon",
    "tiff": "image/tiff",
    "svgz": "image/svg+xml",
    "wmf": "image/wmf",
    "emf": "image/emf",
    "pcx": "image/pcx",
    "djvu": "image/vnd.djvu",
    "djv": "image/vnd.djvu",
    "html": "text/html"
    # "eps": "image/eps",
    # "pdf": "application/pdf"
}

BLOCK_FIELDS_POSITION = {
    'block_index': 0,
    'block_hash': 1,
    'block_time': 2,
    'previous_block_hash': 3,
    'difficulty': 4,
    'ledger_hash': 5,
    'txlist_hash': 6,
    'messages_hash': 7,
    'indexed': 8
}

TXS_FIELDS_POSITION={
    'tx_index':0,
    'tx_hash':1,
    'block_index':2,
    'block_hash':3,
    'block_time':4,
    'source':5,
    'destination':6,
    'btc_amount':7,
    'fee':8,
    'data':9
}

SUPPORTED_EMOJIS = '🇦🇨|🇦🇩|🇦🇪|🇦🇫|🇦🇬|🇦🇮|🇦🇱|🇦🇲|🇦🇴|🇦🇶|🇦🇷|🇦🇸|🇦🇹|🇦🇺|🇦🇼|🇦🇽|🇦🇿|🇧🇦|🇧🇧|🇧🇩|🇧🇪|🇧🇫|🇧🇬|🇧🇭|🇧🇮|🇧🇯|🇧🇱|🇧🇲|🇧🇳|🇧🇴|🇧🇶|🇧🇷|🇧🇸|🇧🇹|🇧🇻|🇧🇼|🇧🇾|🇧🇿|🇨🇦|🇨🇨|🇨🇩|🇨🇫|🇨🇬|🇨🇭|🇨🇮|🇨🇰|🇨🇱|🇨🇲|🇨🇳|🇨🇴|🇨🇵|🇨🇷|🇨🇺|🇨🇻|🇨🇼|🇨🇽|🇨🇾|🇨🇿|🇩🇪|🇩🇬|🇩🇯|🇩🇰|🇩🇲|🇩🇴|🇩🇿|🇪🇦|🇪🇨|🇪🇪|🇪🇬|🇪🇭|🇪🇷|🇪🇸|🇪🇹|🇪🇺|🇫🇮|🇫🇯|🇫🇰|🇫🇲|🇫🇴|🇫🇷|🇬🇦|🇬🇧|🇬🇩|🇬🇪|🇬🇫|🇬🇬|🇬🇭|🇬🇮|🇬🇱|🇬🇲|🇬🇳|🇬🇵|🇬🇶|🇬🇷|🇬🇸|🇬🇹|🇬🇺|🇬🇼|🇬🇾|🇭🇰|🇭🇲|🇭🇳|🇭🇷|🇭🇹|🇭🇺|🇮🇨|🇮🇩|🇮🇪|🇮🇱|🇮🇲|🇮🇳|🇮🇴|🇮🇶|🇮🇷|🇮🇸|🇮🇹|🇯🇪|🇯🇲|🇯🇴|🇯🇵|🇰🇪|🇰🇬|🇰🇭|🇰🇮|🇰🇲|🇰🇳|🇰🇵|🇰🇷|🇰🇼|🇰🇾|🇰🇿|🇱🇦|🇱🇧|🇱🇨|🇱🇮|🇱🇰|🇱🇷|🇱🇸|🇱🇹|🇱🇺|🇱🇻|🇱🇾|🇲🇦|🇲🇨|🇲🇩|🇲🇪|🇲🇫|🇲🇬|🇲🇭|🇲🇰|🇲🇱|🇲🇲|🇲🇳|🇲🇴|🇲🇵|🇲🇶|🇲🇷|🇲🇸|🇲🇹|🇲🇺|🇲🇻|🇲🇼|🇲🇽|🇲🇾|🇲🇿|🇳🇦|🇳🇨|🇳🇪|🇳🇫|🇳🇬|🇳🇮|🇳🇱|🇳🇴|🇳🇵|🇳🇷|🇳🇺|🇳🇿|🇴🇲|🇵🇦|🇵🇪|🇵🇫|🇵🇬|🇵🇭|🇵🇰|🇵🇱|🇵🇲|🇵🇳|🇵🇷|🇵🇸|🇵🇹|🇵🇼|🇵🇾|🇶🇦|🇷🇪|🇷🇴|🇷🇸|🇷🇺|🇷🇼|🇸🇦|🇸🇧|🇸🇨|🇸🇩|🇸🇪|🇸🇬|🇸🇭|🇸🇮|🇸🇯|🇸🇰|🇸🇱|🇸🇲|🇸🇳|🇸🇴|🇸🇷|🇸🇸|🇸🇹|🇸🇻|🇸🇽|🇸🇾|🇸🇿|🇹🇦|🇹🇨|🇹🇩|🇹🇫|🇹🇬|🇹🇭|🇹🇯|🇹🇰|🇹🇱|🇹🇲|🇹🇳|🇹🇴|🇹🇷|🇹🇹|🇹🇻|🇹🇼|🇹🇿|🇺🇦|🇺🇬|🇺🇲|🇺🇳|🇺🇸|🇺🇾|🇺🇿|🇻🇦|🇻🇨|🇻🇪|🇻🇬|🇻🇮|🇻🇳|🇻🇺|🇼🇫|🇼🇸|🇽🇰|🇾🇪|🇾🇹|🇿🇦|🇿🇲|🇿🇼|😀|😃|😄|😁|😆|😅|🤣|😂|🙂|🙃|😉|😊|😇|🥰|😍|🤩|😘|😗|😚|😙|🥲|😋|😛|😜|🤪|😝|🤑|🤗|🤭|🤫|🤔|🤐|🤨|😐|😑|😶|😏|😒|🙄|😬|🤥|😌|😔|😪|🤤|😴|😷|🤒|🤕|🤢|🤮|🤧|🥵|🥶|🥴|😵|🤯|🤠|🥳|🥸|😎|🤓|🧐|😕|😟|🙁|😮|😯|😲|😳|🥺|😦|😧|😨|😰|😥|😢|😭|😱|😖|😣|😞|😓|😩|😫|🥱|😤|😡|😠|🤬|😈|👿|💀|💩|🤡|👹|👺|👻|👽|👾|🤖|😺|😸|😹|😻|😼|😽|🙀|😿|😾|🙈|🙉|🙊|💋|💌|💘|💝|💖|💗|💓|💞|💕|💟|💔|🧡|💛|💚|💙|💜|🤎|🖤|🤍|💯|💢|💥|💫|💦|💨|🕳|💣|💬|🗨|🗯|💭|💤|👋|🤚|🖐|🖖|👌|🤌|🤏|🤞|🤟|🤘|🤙|👈|👉|👆|🖕|👇|👍|👎|👊|🤛|🤜|👏|🙌|👐|🤲|🤝|🙏|💅|🤳|💪|🦾|🦿|🦵|🦶|👂|🦻|👃|🧠|🫀|🫁|🦷|🦴|👀|👁|👅|👄|👶|🧒|👦|👧|🧑|👱|👨|🧔|👩|🧓|👴|👵|🙍|🙎|🙅|🙆|💁|🙋|🧏|🙇|🤦|🤷|👮|🕵|💂|🥷|👷|🤴|👸|👳|👲|🧕|🤵|👰|🤰|🤱|👼|🎅|🤶|🦸|🦹|🧙|🧚|🧛|🧜|🧝|🧞|🧟|💆|💇|🚶|🧍|🧎|🏃|💃|🕺|🕴|👯|🧖|🧗|🤺|🏇|🏂|🏌|🏄|🚣|🏊|🏋|🚴|🚵|🤸|🤼|🤽|🤾|🤹|🧘|🛀|🛌|👭|👫|👬|💏|💑|👪|🗣|👤|👥|🫂|👣|🦰|🦱|🦳|🦲|🐵|🐒|🦍|🦧|🐶|🐕|🦮|🐩|🐺|🦊|🦝|🐱|🐈|🦁|🐯|🐅|🐆|🐴|🐎|🦄|🦓|🦌|🦬|🐮|🐂|🐃|🐄|🐷|🐖|🐗|🐽|🐏|🐑|🐐|🐪|🐫|🦙|🦒|🐘|🦣|🦏|🦛|🐭|🐁|🐀|🐹|🐰|🐇|🐿|🦫|🦔|🦇|🐻|🐨|🐼|🦥|🦦|🦨|🦘|🦡|🐾|🦃|🐔|🐓|🐣|🐤|🐥|🐦|🐧|🕊|🦅|🦆|🦢|🦉|🦤|🪶|🦩|🦚|🦜|🐸|🐊|🐢|🦎|🐍|🐲|🐉|🦕|🦖|🐳|🐋|🐬|🦭|🐟|🐠|🐡|🦈|🐙|🐚|🐌|🦋|🐛|🐜|🐝|🪲|🐞|🦗|🪳|🕷|🕸|🦂|🦟|🪰|🪱|🦠|💐|🌸|💮|🏵|🌹|🥀|🌺|🌻|🌼|🌷|🌱|🪴|🌲|🌳|🌴|🌵|🌾|🌿|🍀|🍁|🍂|🍃|🍇|🍈|🍉|🍊|🍋|🍌|🍍|🥭|🍎|🍏|🍐|🍑|🍒|🍓|🫐|🥝|🍅|🫒|🥥|🥑|🍆|🥔|🥕|🌽|🌶|🫑|🥒|🥬|🥦|🧄|🧅|🍄|🥜|🌰|🍞|🥐|🥖|🫓|🥨|🥯|🥞|🧇|🧀|🍖|🍗|🥩|🥓|🍔|🍟|🍕|🌭|🥪|🌮|🌯|🫔|🥙|🧆|🥚|🍳|🥘|🍲|🫕|🥣|🥗|🍿|🧈|🧂|🥫|🍱|🍘|🍙|🍚|🍛|🍜|🍝|🍠|🍢|🍣|🍤|🍥|🥮|🍡|🥟|🥠|🥡|🦀|🦞|🦐|🦑|🦪|🍦|🍧|🍨|🍩|🍪|🎂|🍰|🧁|🥧|🍫|🍬|🍭|🍮|🍯|🍼|🥛|🫖|🍵|🍶|🍾|🍷|🍸|🍹|🍺|🍻|🥂|🥃|🥤|🧋|🧃|🧉|🧊|🥢|🍽|🍴|🥄|🔪|🏺|🌍|🌎|🌏|🌐|🗺|🗾|🧭|🏔|🌋|🗻|🏕|🏖|🏜|🏝|🏞|🏟|🏛|🏗|🧱|🪨|🪵|🛖|🏘|🏚|🏠|🏡|🏢|🏣|🏤|🏥|🏦|🏨|🏩|🏪|🏫|🏬|🏭|🏯|🏰|💒|🗼|🗽|🕌|🛕|🕍|🕋|🌁|🌃|🏙|🌄|🌅|🌆|🌇|🌉|🎠|🎡|🎢|💈|🎪|🚂|🚃|🚄|🚅|🚆|🚇|🚈|🚉|🚊|🚝|🚞|🚋|🚌|🚍|🚎|🚐|🚑|🚒|🚓|🚔|🚕|🚖|🚗|🚘|🚙|🛻|🚚|🚛|🚜|🏎|🏍|🛵|🦽|🦼|🛺|🚲|🛴|🛹|🛼|🚏|🛣|🛤|🛢|🚨|🚥|🚦|🛑|🚧|🛶|🚤|🛳|🛥|🚢|🛩|🛫|🛬|🪂|💺|🚁|🚟|🚠|🚡|🛰|🚀|🛸|🛎|🧳|🕰|🕛|🕧|🕐|🕜|🕑|🕝|🕒|🕞|🕓|🕟|🕔|🕠|🕕|🕡|🕖|🕢|🕗|🕣|🕘|🕤|🕙|🕥|🕚|🕦|🌑|🌒|🌓|🌔|🌕|🌖|🌗|🌘|🌙|🌚|🌛|🌜|🌡|🌝|🌞|🪐|🌟|🌠|🌌|🌤|🌥|🌦|🌧|🌨|🌩|🌪|🌫|🌬|🌀|🌈|🌂|🔥|💧|🌊|🎃|🎄|🎆|🎇|🧨|🎈|🎉|🎊|🎋|🎍|🎎|🎏|🎐|🎑|🧧|🎀|🎁|🎗|🎟|🎫|🎖|🏆|🏅|🥇|🥈|🥉|🥎|🏀|🏐|🏈|🏉|🎾|🥏|🎳|🏏|🏑|🏒|🥍|🏓|🏸|🥊|🥋|🥅|🎣|🤿|🎽|🎿|🛷|🥌|🎯|🪀|🪁|🎱|🔮|🪄|🧿|🎮|🕹|🎰|🎲|🧩|🧸|🪅|🪆|🃏|🀄|🎴|🎭|🖼|🎨|🧵|🪡|🧶|🪢|👓|🕶|🥽|🥼|🦺|👔|👕|👖|🧣|🧤|🧥|🧦|👗|👘|🥻|🩱|🩲|🩳|👙|👚|👛|👜|👝|🛍|🎒|🩴|👞|👟|🥾|🥿|👠|👡|🩰|👢|👑|👒|🎩|🎓|🧢|🪖|📿|💄|💍|💎|🔇|🔈|🔉|🔊|📢|📣|📯|🔔|🔕|🎼|🎵|🎶|🎙|🎚|🎛|🎤|🎧|📻|🎷|🪗|🎸|🎹|🎺|🎻|🪕|🥁|🪘|📱|📲|📞|📟|📠|🔋|🔌|💻|🖥|🖨|🖱|🖲|💽|💾|💿|📀|🧮|🎥|🎞|📽|🎬|📺|📷|📸|📹|📼|🔍|🔎|🕯|💡|🔦|🏮|🪔|📔|📕|📖|📗|📘|📙|📚|📓|📒|📃|📜|📄|📰|🗞|📑|🔖|🏷|💰|🪙|💴|💵|💶|💷|💸|💳|🧾|💹|📧|📨|📩|📤|📥|📦|📫|📪|📬|📭|📮|🗳|🖋|🖊|🖌|🖍|📝|💼|📁|📂|🗂|📅|📆|🗒|🗓|📇|📈|📉|📊|📋|📌|📍|📎|🖇|📏|📐|🗃|🗄|🗑|🔒|🔓|🔏|🔐|🔑|🗝|🔨|🪓|🛠|🗡|🔫|🪃|🏹|🛡|🪚|🔧|🪛|🔩|🗜|🦯|🔗|🪝|🧰|🧲|🪜|🧪|🧫|🧬|🔬|🔭|📡|💉|🩸|💊|🩹|🩺|🚪|🛗|🪞|🪟|🛏|🛋|🪑|🚽|🪠|🚿|🛁|🪤|🪒|🧴|🧷|🧹|🧺|🧻|🪣|🧼|🪥|🧽|🧯|🛒|🚬|🪦|🗿|🪧|🏧|🚮|🚰|🚹|🚺|🚻|🚼|🚾|🛂|🛃|🛄|🛅|🚸|🚫|🚳|🚭|🚯|🚱|🚷|📵|🔞|🔃|🔄|🔙|🔚|🔛|🔜|🔝|🛐|🕉|🕎|🔯|🔀|🔁|🔂|🔼|🔽|🎦|🔅|🔆|📶|📳|📴|💱|💲|🔱|📛|🔰|🔟|🔠|🔡|🔢|🔣|🔤|🅰|🆎|🅱|🆑|🆒|🆓|🆔|🆕|🆖|🅾|🆗|🅿|🆘|🆙|🆚|🈁|🈂|🈷|🈶|🈯|🉐|🈹|🈚|🈲|🉑|🈸|🈴|🈳|🈺|🈵|🔴|🟠|🟡|🟢|🔵|🟣|🟤|🟥|🟧|🟨|🟩|🟦|🟪|🟫|🔶|🔷|🔸|🔹|🔺|🔻|💠|🔘|🔳|🔲|🏁|🚩|🎌|🏴|🏳'
SUPPORTED_CHARS = '!|#|$|%|&|(|)|*|0|1|2|3|4|5|6|7|8|9|<|=|>|?|@|A|B|C|D|E|F|G|H|I|J|K|L|M|N|O|P|Q|R|S|T|U|V|W|X|Y|Z|^|_|a|b|c|d|e|f|g|h|i|j|k|l|m|n|o|p|q|r|s|t|u|v|w|x|y|z|~'
SUPPORTED = SUPPORTED_CHARS + '|' + SUPPORTED_EMOJIS

TICK_PATTERN_LIST = {
    regex.compile('|'.join(re.escape(chars) for chars in SUPPORTED))
}


# Versions
VERSION_MAJOR = 0
VERSION_MINOR = 1
VERSION_REVISION = 2
VERSION_STRING = str(VERSION_MAJOR) + '.' + str(VERSION_MINOR) + '.' + str(VERSION_REVISION)


BTC_NAME = 'Bitcoin'
STAMPS_NAME = 'btc_stamps'
APP_NAME = STAMPS_NAME.lower()


DEFAULT_BACKEND_PORT_REGTEST = 28332
DEFAULT_BACKEND_PORT_TESTNET = 18332
DEFAULT_BACKEND_PORT = 8332

BLOCK_FIRST_TESTNET = 310000

BLOCK_FIRST_MAINNET = CP_STAMP_GENESIS_BLOCK # 791243 # 791510  # 791243  # 796000  # 790249  # 779650

BLOCK_FIRST_REGTEST = 0

DEFAULT_REQUESTS_TIMEOUT = 20   # 20 seconds

BACKEND_RAW_TRANSACTIONS_CACHE_SIZE = 20000
BACKEND_RPC_BATCH_NUM_WORKERS = 6

API_LIMIT_ROWS = 1000
