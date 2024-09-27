import logging
import warnings
from typing import Dict

import config
import index_core.util as util

logger = logging.getLogger(__name__)

CONSENSUS_HASH_SEED = (
    "Through our eyes, the universe is perceiving itself. Through our ears, the universe is listening to its harmonies."
)

CONSENSUS_HASH_VERSION_MAINNET = 1
CHECKPOINTS_MAINNET: Dict[int, Dict[str, str]] = {
    config.CP_STAMP_GENESIS_BLOCK: {
        "ledger_hash": "",
        "txlist_hash": "f5277855a60219dfff0ea837e6835478cbbc32c3520cb1dc1f13c296594b3a05",
    },
    779700: {
        "ledger_hash": "",
        "txlist_hash": "340253f42a61d8020c7ef21c120e1cf78319c3b773bbacdf3610c4a7a67fef6c",
    },
    780000: {
        "ledger_hash": "",
        "txlist_hash": "aa8c5c358cae915b203534afe2d67ea523b680be243940e841de0573421ef90d",
    },
    781000: {
        "ledger_hash": "",
        "txlist_hash": "f52ed660840bcac55ea46be3e5c3d98a72339dad4b931569a126d053b50776ac",
    },
    781100: {
        "ledger_hash": "",
        "txlist_hash": "babf8057ba0f149f601d5b4a7922ddb196764b23760dd44631c8d6aa36a34371",
    },
    781141: {
        "ledger_hash": "",
        "txlist_hash": "f67c8a0a53d36b02d0b621b8f8d8e30edd49701d118af81f68b356685afbf44b",
    },
    781300: {
        "ledger_hash": "",
        "txlist_hash": "623b3ec08efd52fbf92fcb6425d622b0228f0f7c883dfa499f5f53b0c2695b2e",
    },
    782285: {
        "ledger_hash": "",
        "txlist_hash": "5e5c77b0a8ae2aef230faa948172b404af9fb1649fd46c287c378e62289045cf",
    },
    785000: {
        "ledger_hash": "",
        "txlist_hash": "ed6ad5bff1c195cc1bb654893ce59d4d45c773c939231e31cc415d1a8f611dd5",
    },
    788041: {
        "ledger_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "txlist_hash": "8f4376d0363e29d8a19693e65e9c033730dc29bc4aac78677c4b093ec4a63adc",
    },
    788127: {
        "ledger_hash": "32fac3ac1708f5ad22ee9537752e187307b692b069d68dc8fcaf93210421cd16",
        "txlist_hash": "6718b7eace95a1b3823c648b9a99a4ab1881d86ca412d823b48b92b168ebf9a9",
    },
    788134: {
        "ledger_hash": "1d9fd11b3fb6b96a1a9ae676bf84d674316f05dbec2d489709ebbbf48c1a0d84",
        "txlist_hash": "e92b73193854463dda53e92d23c9efb84e4757a4203af858e1f2b35c2849021c",
    },
    790000: {
        "ledger_hash": "",
        "txlist_hash": "c4dd0af160319ac00293add4f1dff9acab6051bb93dec1916e2478714756b663",
    },
    795000: {
        "ledger_hash": "",
        "txlist_hash": "bf7bbb8c498b4717be51bc636e753ad7afe94d062a0a811c8302f2031b7ea91a",
    },
    800000: {
        "ledger_hash": "",
        "txlist_hash": "eb79727fc63c126eef58c994fadd7a33bd5fc55e85ffd1490cfd19d69bd6ac50",
    },
    805000: {
        "ledger_hash": "",
        "txlist_hash": "9738b8482e012227aff59043466584a693c3ad79f3ad646a3de73b4619e965aa",
    },
    810000: {
        "ledger_hash": "",
        "txlist_hash": "c13355c538c4a2d36d7c5d45ac94f2d9351b543b1132d2ea47c8b7e77908d217",
    },
    815000: {
        "ledger_hash": "",
        "txlist_hash": "f712328e2326ee50d2b17df90aaad61761b72b1e44c233dbc25ab363146167f1",
    },
    820000: {
        "ledger_hash": "aee64e20dc83d09852c78c3caa9c39a61e77c0fa946843f39838963046f15932",
        "txlist_hash": "502fa4bad658fa745014b45aa64f546e4a8885fd7d0adcdfa6575eca54f1ea7a",
    },
    825000: {
        "ledger_hash": "68e0621468999995719b13a974ed53047c88b63bb4c211f30c63d7afd0a52159",
        "txlist_hash": "61f275aa6b571276f735a2dd1c083b4ff65291e25af54ca3c3a9f26d2a3f4702",
    },
    830000: {
        "ledger_hash": "e3bb684fba10cedf0dc5778a85aab66a42e500fad5405fe245a5bf80f313523b",
        "txlist_hash": "2e85610013ae8d4dc17d7e964728b4b8f853c58c0d4414ed0914f43010aebe98",
    },
    835000: {
        "ledger_hash": "78e5d16e8802ea0d751bee5d9df2411b71f64032ae5ad7b98aec1617ecb082a3",
        "txlist_hash": "8a5d2baddcaabc1240818f537ca646e3ca9070a601d43a4bff4d2c56aee32d6e",
    },
    840000: {
        "ledger_hash": "",
        "txlist_hash": "7f20fc83836a65547c54710229fea90f3200f859adc5fd30c297f96b17cb31e5",
    },
    845000: {
        "ledger_hash": "d74c8f1ff0a99c4f361b9616a57f442aa19a19a5808753c4ee464a9a60289f0e",
        "txlist_hash": "7f4bff436f15cf45ceaea7cd66dac0f02e9f8d293efcfb847238d7a8c522bf30",
    },
    850000: {
        "ledger_hash": "35ddde0f2f791c14fe295017713372fa5f92a6980f9f54710068c99b4284939b",
        "txlist_hash": "bf5ad20f038cff311999e7d16c2165de12efb0663a8e42f0d077621f7e3b1f17",
    },
    855000: {
        "ledger_hash": "8e9c0ca34351ce59a0d5ee744f4115021c62a3dd5cbf791b063e4251d3cf4f42",
        "txlist_hash": "4316b45083f4e74e6acf43efce255d1bff023a5ebcdb0999c63adb33d036dc80",
    },
    860000: {
        "ledger_hash": "dc257e7b5e06460bab3485ad1a845ac7ab6e2937ff04df11f3aaa55e653e5e17",
        "txlist_hash": "45aead95538e500966450718323728331b41ab8af5d6b80174a148ad8e780b60",
    },
}

CONSENSUS_HASH_VERSION_TESTNET = 7
CHECKPOINTS_TESTNET = {
    config.BLOCK_FIRST_TESTNET: {"ledger_hash": "", "txlist_hash": ""},
}

CONSENSUS_HASH_VERSION_REGTEST = 1
CHECKPOINTS_REGTEST = {
    config.BLOCK_FIRST_REGTEST: {"ledger_hash": "", "txlist_hash": ""},
}


class ConsensusError(Exception):
    pass


def consensus_hash(db, block_index, field, previous_consensus_hash, content):
    field_position = config.BLOCK_FIELDS_POSITION
    cursor = db.cursor()
    # block_index = util.CURRENT_BLOCK_INDEX

    # initialize previous hash on first block.
    if block_index <= config.BLOCK_FIRST and field != "ledger_hash":
        if previous_consensus_hash:
            raise ConsensusError("Expected previous_consensus_hash to be unset for the first block.")
        previous_consensus_hash = util.dhash_string(CONSENSUS_HASH_SEED)
    elif block_index == config.CP_SRC20_GENESIS_BLOCK + 1 and field == "ledger_hash":
        if previous_consensus_hash:
            raise ConsensusError("Expected previous_consensus_hash to be unset for the SRC20 genesis block.")
        previous_consensus_hash = util.shash_string("")

    # Get previous hash.
    if not previous_consensus_hash and field != "ledger_hash":
        try:
            cursor.execute("""SELECT * FROM blocks WHERE block_index = %s""", (block_index - 1,))
            results = cursor.fetchall()
            if results:
                previous_consensus_hash = results[0][field_position[field]]
            else:
                previous_consensus_hash = None
        except IndexError:
            previous_consensus_hash = None
        if not previous_consensus_hash:
            raise ConsensusError("Empty previous {} for block {}. Please launch a `reparse`.".format(field, block_index))
    elif not previous_consensus_hash and field == "ledger_hash" and content != "":
        cursor.execute(
            """SELECT ledger_hash FROM blocks WHERE ledger_hash IS NOT NULL AND ledger_hash <> '' ORDER BY block_index DESC LIMIT 1"""
        )
        result = cursor.fetchone()
        previous_consensus_hash = result[0] if result else None
        if not previous_consensus_hash:
            raise ConsensusError(f"Empty previous {field} for block {block_index}. Please launch a `reparse`.")

    # Calculate current hash.
    if config.TESTNET:
        consensus_hash_version = CONSENSUS_HASH_VERSION_TESTNET
    elif config.REGTEST:
        consensus_hash_version = CONSENSUS_HASH_VERSION_REGTEST
    else:
        consensus_hash_version = CONSENSUS_HASH_VERSION_MAINNET

    if field == "ledger_hash" and block_index == config.CP_SRC20_GENESIS_BLOCK:
        calculated_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    elif field == "ledger_hash" and block_index > config.CP_SRC20_GENESIS_BLOCK and content:
        concatenated_content = previous_consensus_hash.encode("utf-8") + content.encode("utf-8")
        calculated_hash = util.shash_string(concatenated_content)
    elif field == "ledger_hash" and content == "":
        calculated_hash = ""
    else:
        calculated_hash = util.dhash_string(previous_consensus_hash + "{}{}".format(consensus_hash_version, "".join(content)))

    # Verify hash (if already in database) or save hash (if not).
    cursor.execute("""SELECT * FROM blocks WHERE block_index = %s""", (block_index,))
    results = cursor.fetchall()
    if results:
        found_hash = results[0][config.BLOCK_FIELDS_POSITION[field]]
    else:
        found_hash = None
    if found_hash and field != "messages_hash":
        # Check against existing value.
        if calculated_hash != found_hash:
            raise ConsensusError(
                "Inconsistent {} for block {} (calculated {}, vs {} in database).".format(
                    field, block_index, calculated_hash, found_hash
                )
            )
    else:
        # Save new hash.
        cursor.execute(
            """UPDATE blocks SET {} = %s WHERE block_index = %s""".format(field),
            (calculated_hash, block_index),
        )  # nosec

    # Check against checkpoints.
    if config.TESTNET:
        checkpoints = CHECKPOINTS_TESTNET
    elif config.REGTEST:
        checkpoints = CHECKPOINTS_REGTEST
    else:
        checkpoints = CHECKPOINTS_MAINNET

    if field != "messages_hash" and block_index in checkpoints and checkpoints[block_index][field] != calculated_hash:
        raise ConsensusError(
            "Incorrect {} consensus hash for block {}.  Calculated {} but expected {}".format(
                field,
                block_index,
                calculated_hash,
                checkpoints[block_index][field],
            )
        )

    return calculated_hash, found_hash


class VersionError(Exception):
    pass


class VersionUpdateRequiredError(VersionError):
    pass


# TODO: https://github.com/stampchain-io/btc_stamps/issues/13
def check_change(protocol_change, change_name):

    # Check client version.
    passed = True
    if config.VERSION_MAJOR < protocol_change["minimum_version_major"]:
        passed = False
    elif config.VERSION_MAJOR == protocol_change["minimum_version_major"]:
        if config.VERSION_MINOR < protocol_change["minimum_version_minor"]:
            passed = False
        elif config.VERSION_MINOR == protocol_change["minimum_version_minor"]:
            if config.VERSION_REVISION < protocol_change["minimum_version_revision"]:
                passed = False
    # passed = True # Removing version check for now

    if not passed:
        explanation = "Your version of {} is v{}, but, as of block {}, the minimum version is v{}.{}.{}. Reason: ‘{}’. Please upgrade to the latest version and restart the server.".format(
            config.APP_NAME or "",
            config.VERSION_STRING or "",
            protocol_change["block_index"],
            protocol_change["minimum_version_major"],
            protocol_change["minimum_version_minor"],
            protocol_change["minimum_version_revision"],
            change_name or "",
        )
        if util.CURRENT_BLOCK_INDEX >= protocol_change["block_index"]:
            raise VersionUpdateRequiredError(explanation)
        else:
            warnings.warn(explanation)


def cp_version():
    # cp_version = get_cp_version()
    # FIXME: Finish version checking validation.
    return


def software_version():
    logger.warning("Software version: {}.".format(config.VERSION_STRING or ""))