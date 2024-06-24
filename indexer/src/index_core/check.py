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
        "txlist_hash": "008263ede1da9c74b4118c7daaaad6d68109146925b42ba0c4940477b17fb49f",
    },
    788041: {
        "ledger_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "txlist_hash": "dc7b1d35ec28cb3e27c5db6156b0426a56f01cf0489d92cc82c737280851bc81",
    },
    788127: {
        "ledger_hash": "32fac3ac1708f5ad22ee9537752e187307b692b069d68dc8fcaf93210421cd16",
        "txlist_hash": "977b9d1fe9ca2eff71d8d6d30adf2c0e4848a7aed48b69e5645618e1ad5aea95",
    },
    788134: {
        "ledger_hash": "1d9fd11b3fb6b96a1a9ae676bf84d674316f05dbec2d489709ebbbf48c1a0d84",
        "txlist_hash": "b7c94eb6ec9b803574d5d1852772a8bbae2fbcedd9844aaedc5e1a639cfa8839",
    },
    790000: {
        "ledger_hash": "",
        "txlist_hash": "388d2dcaa6133b2b5dd77bd1f8080fe2e8351c8175971466105609be1ef07fad",
    },
    795000: {
        "ledger_hash": "",
        "txlist_hash": "791227d2a457012cd389abf1cb993152d168138d50716ca4dfaa60d9aea11f36",
    },
    800000: {
        "ledger_hash": "",
        "txlist_hash": "4396be10d09e0ebab08511723e82d3d9c8af6febf645279e189df3198ded555b",
    },
    805000: {
        "ledger_hash": "",
        "txlist_hash": "21ffd7c9dccc484cbbd420f29267119695474e52fc3e20afcc3d214e57b88896",
    },
    810000: {
        "ledger_hash": "",
        "txlist_hash": "342e2c07717cdde3215313c82c3608a06a7041f20a2a18f465b559a75806b0b1",
    },
    815000: {
        "ledger_hash": "",
        "txlist_hash": "fbddbb8f01a9dd582d40511bc963d82e42fb5b5b6e426f62819dd258fde61ad0",
    },
    820000: {
        "ledger_hash": "aee64e20dc83d09852c78c3caa9c39a61e77c0fa946843f39838963046f15932",
        "txlist_hash": "3d0ff6fbdbf8eea6cbad13582e9a2fd4928d47c5345c6fc82943d12b45b0defa",
    },
    825000: {
        "ledger_hash": "68e0621468999995719b13a974ed53047c88b63bb4c211f30c63d7afd0a52159",
        "txlist_hash": "f82fabbab18175d458526e6404e60604c48f7ea16fbe73983b7a70ac71652015",
    },
    830000: {
        "ledger_hash": "e3bb684fba10cedf0dc5778a85aab66a42e500fad5405fe245a5bf80f313523b",
        "txlist_hash": "4ca0b22b3d22d8b40917c8bdce88f31df133347ba8fa1607c2317af8c5ad68dc",
    },
    835000: {
        "ledger_hash": "78e5d16e8802ea0d751bee5d9df2411b71f64032ae5ad7b98aec1617ecb082a3",
        "txlist_hash": "7cb2ce944ff66f7d016ebbcac53412c080bd2b384e313d98e1578c9080c43e31",
    },
    840000: {
        "ledger_hash": "",
        "txlist_hash": "3a5fe1c54d6e03f8dcbc490bfa80d1e5b9084f71cb7967b068dcfe2427e241f6",
    },
    845000: {
        "ledger_hash": "d74c8f1ff0a99c4f361b9616a57f442aa19a19a5808753c4ee464a9a60289f0e",
        "txlist_hash": "fd8e42be7e86defb57607bb4e75c43e148684268879a16e33a2520c4a72ecda7",
    },
    850000: {
        "ledger_hash": "35ddde0f2f791c14fe295017713372fa5f92a6980f9f54710068c99b4284939b",
        "txlist_hash": "5f425045e7e9b29bf3c75c59ecbf6638c715287cce749ba5e831c2b868a10ff3",
    },
}

CONSENSUS_HASH_VERSION_TESTNET = 7
CHECKPOINTS_TESTNET = {
    config.BLOCK_FIRST_TESTNET: {
        "ledger_hash": "",
        "txlist_hash": "3638e9fd18f288000a4076c74f9956a1d8f9db013578a9e1e906f4b333d7b5e2",
    },
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
