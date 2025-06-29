import logging
import os
import warnings
from typing import Dict

import config
import index_core.util as util
from index_core.fetch_utils import fetch_node_version_v2
from index_core.node_health import get_healthy_nodes, initialize_node_health

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
        "txlist_hash": "9f7191e5a59e56b5a7165a14e98af9d4c1f7107f4c5dcc8a871d330afe9975b4",
    },
    835000: {
        "ledger_hash": "78e5d16e8802ea0d751bee5d9df2411b71f64032ae5ad7b98aec1617ecb082a3",
        "txlist_hash": "49ed6c6c7fc2a7281727c2690abfc264a2c11f6b311929b69691372f8b7e46dd",
    },
    840000: {
        "ledger_hash": "",
        "txlist_hash": "901310b2b76b19bcdf56e36e3d871eb36aac11fbfe0cc11570e71378d6e65e59",
    },
    845000: {
        "ledger_hash": "d74c8f1ff0a99c4f361b9616a57f442aa19a19a5808753c4ee464a9a60289f0e",
        "txlist_hash": "6ae37614f9e78045984ccfa6113922cac5cde2bfa15d710050242a36e6a40741",
    },
    850000: {
        "ledger_hash": "35ddde0f2f791c14fe295017713372fa5f92a6980f9f54710068c99b4284939b",
        "txlist_hash": "d56c8259750b84e964f287b9e228a94138aab153089a762279e35b33fecb46d9",
    },
    855000: {
        "ledger_hash": "8e9c0ca34351ce59a0d5ee744f4115021c62a3dd5cbf791b063e4251d3cf4f42",
        "txlist_hash": "32a29f1f67a9a604d4dd2f25e980aac1ae2a30bf568ba8d21a8d1b96d54a7b84",
    },
    860000: {
        "ledger_hash": "dc257e7b5e06460bab3485ad1a845ac7ab6e2937ff04df11f3aaa55e653e5e17",
        "txlist_hash": "437b92262d9036173807a269b45f5d5b2b05ffc64e7109f0d1d37de02bede246",
    },
    865000: {
        "ledger_hash": "0cfab60c2426ec4007cc607099ada5808b6ef46374093bb93d2ed922e20c9b3c",
        "txlist_hash": "0653447013b5def1b13dab502d1a13ed4d67445abfbafe9a29b06366553107c0",
    },
    870000: {
        "ledger_hash": "d3316ac4ecbf022eb7656f58ca5fa6073d5f3a3fb899ee17084b0b4ede83d072",
        "txlist_hash": "a2087a247c2e62d5442f0e9f6fd0ef0f47c04ec0e4c921cdd5340368ecca1ba8",
    },
    875000: {
        "ledger_hash": "0994fdf27c5ee1c0ca42988a9aea2041b60ab0a6c0aa33409ae47abb0cde31a0",
        "txlist_hash": "009ead98f3f6e8dc17ba89dba42b5fc1a761a80e51a3d2221f375f8f820940a2",
    },
    880000: {
        "ledger_hash": "874fb734fa2ec72e0846457c1f5f0f8e754a284afb3a0101901c66fa21fa0e97",
        "txlist_hash": "9c616915cac2168cbcb7a42e601f95d452e281c7fba6ccac1a04f853bc7b905b",
    },
    885000: {
        "ledger_hash": "6f80bd0cc8b7a9a49cd49d7e1d371a80c11566e9800f3f601ff4793274109f96",
        "txlist_hash": "c13b5b98e47b4449b2a8fdf3221a7b905447e0820b658734ba8e8f87986d7e4a",
    },
}


CONSENSUS_HASH_VERSION_TESTNET = 7
CHECKPOINTS_TESTNET = {
    config.BLOCK_FIRST_TESTNET: {
        "ledger_hash": "",
        "txlist_hash": "1ef99f774eb89230b780eff7fa48b514de5e23353d7cd5810478636d961c5c86",
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

    # initialize previous hash on first block.
    if block_index <= config.BLOCK_FIRST and field != "ledger_hash":
        if previous_consensus_hash:
            error_msg = "Expected previous_consensus_hash to be unset for the first block."
            force_enabled = config.FORCE or os.environ.get("FORCE", "false").lower() == "true"
            if force_enabled:
                logger.warning(f"FORCE mode enabled - {error_msg}")
            else:
                raise ConsensusError(error_msg)
        previous_consensus_hash = util.dhash_string(CONSENSUS_HASH_SEED)
    elif block_index == config.CP_SRC20_GENESIS_BLOCK + 1 and field == "ledger_hash":
        if previous_consensus_hash:
            error_msg = "Expected previous_consensus_hash to be unset for the SRC20 genesis block."
            if config.FORCE:
                logger.warning(f"FORCE mode enabled - {error_msg}")
            else:
                raise ConsensusError(error_msg)
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
            error_msg = "Empty previous {} for block {}. Please launch a `reparse`.".format(field, block_index)
            if config.FORCE:
                logger.warning(f"FORCE mode enabled - {error_msg}")
                previous_consensus_hash = util.dhash_string(CONSENSUS_HASH_SEED)  # Use default seed
            else:
                raise ConsensusError(error_msg)
    elif not previous_consensus_hash and field == "ledger_hash" and content != "":
        cursor.execute(
            """SELECT ledger_hash FROM blocks WHERE ledger_hash IS NOT NULL AND ledger_hash <> '' ORDER BY block_index DESC LIMIT 1"""
        )
        result = cursor.fetchone()
        previous_consensus_hash = result[0] if result else None
        if not previous_consensus_hash:
            error_msg = f"Empty previous {field} for block {block_index}. Please launch a `reparse`."
            if config.FORCE:
                logger.warning(f"FORCE mode enabled - {error_msg}")
                previous_consensus_hash = util.shash_string("")  # Use empty hash for ledger_hash
            else:
                raise ConsensusError(error_msg)

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
        # For other hashes (messages, txlist), use the previous consensus hash in calculation
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
            error_msg = "Inconsistent {} for block {} (calculated {}, vs {} in database).".format(
                field, block_index, calculated_hash, found_hash
            )
            if config.FORCE:
                logger.warning(f"FORCE mode enabled - {error_msg}")
            else:
                raise ConsensusError(error_msg)
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
        error_msg = "Incorrect {} consensus hash for block {}.  Calculated {} but expected {}".format(
            field,
            block_index,
            calculated_hash,
            checkpoints[block_index][field],
        )
        # Check both config.FORCE and environment variable as fallback
        force_enabled = config.FORCE or os.environ.get("FORCE", "false").lower() == "true"
        logger.debug(
            f"Checking FORCE mode: config.FORCE={config.FORCE}, env FORCE={os.environ.get('FORCE')}, force_enabled={force_enabled}"
        )
        if force_enabled:
            logger.warning(f"FORCE mode enabled - {error_msg}")
            # Don't raise the error, just return the calculated hash
        else:
            logger.debug(f"FORCE not enabled, raising ConsensusError")
            raise ConsensusError(error_msg)

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
        explanation = "Your version of {} is v{}, but, as of block {}, the minimum version is v{}.{}.{}. Reason: '{}'. Please upgrade to the latest version and restart the server.".format(
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


def cp_version(log_connection=False):
    initialize_node_health()
    healthy_nodes = get_healthy_nodes()

    if not healthy_nodes:
        logger.warning("Could not determine Counterparty version: No healthy nodes available.")
        return None, None

    version_results = []
    successful_connections = 0

    for i, node in enumerate(healthy_nodes):
        node_name = node.get("name", f"Node {i + 1}")
        node_url = node.get("url")

        if not node_url:
            logger.warning(f"Skipping {node_name}: No URL configured")
            continue

        version_string, version_info = fetch_node_version_v2(node_url)

        if version_string and version_info:
            version_results.append(
                {
                    "name": node_name,
                    "url": node_url,
                    "version_string": version_string,
                    "version_info": version_info,
                    "status": "connected",
                }
            )
            successful_connections += 1
        else:
            version_results.append(
                {"name": node_name, "url": node_url, "version_string": None, "version_info": None, "status": "failed"}
            )

    # Log clean summary
    if successful_connections > 0:
        logger.info(f"Counterparty nodes ({successful_connections}/{len(healthy_nodes)} connected):")
        for result in version_results:
            if result["status"] == "connected":
                logger.info(f"  ✓ {result['name']}: {result['version_string']}")
            else:
                logger.warning(f"  ✗ {result['name']}: Connection failed")
    else:
        logger.warning("Could not connect to any Counterparty nodes")

    # Perform version validation checks
    connected_results = [r for r in version_results if r["status"] == "connected"]

    if len(connected_results) > 0:
        # Check minimum version requirement (11.0.0 or greater)
        minimum_version = (11, 0, 0)
        version_violations = []

        for result in connected_results:
            version_info = result["version_info"]
            node_name = result["name"]
            version_string = result["version_string"]

            if (
                version_info
                and "version_major" in version_info
                and "version_minor" in version_info
                and "version_revision" in version_info
            ):
                major = version_info["version_major"]
                minor = version_info["version_minor"]
                revision = version_info["version_revision"]
                node_version = (major, minor, revision)

                if node_version < minimum_version:
                    version_violations.append(
                        {"name": node_name, "version_string": version_string, "version_tuple": node_version}
                    )

        # Critical error if any node is below minimum version
        if version_violations:
            violation_details = [f"{v['name']} (v{v['version_string']})" for v in version_violations]
            error_msg = (
                f"CRITICAL: Counterparty node version requirement not met. "
                f"This Bitcoin Stamps indexer requires Counterparty version 11.0.0 or greater. "
                f"Nodes below minimum: {', '.join(violation_details)}. "
                f"Please upgrade your Counterparty nodes before continuing."
            )
            logger.critical(error_msg)
            raise VersionError(error_msg)

        # Check for version mismatches between nodes
        if len(connected_results) > 1:
            version_strings = [r["version_string"] for r in connected_results]
            unique_versions = set(version_strings)

            if len(unique_versions) > 1:
                node_version_details = [f"{r['name']} (v{r['version_string']})" for r in connected_results]
                logger.warning(
                    f"WARNING: Counterparty node version mismatch detected. "
                    f"All nodes should run the same version for consistent behavior. "
                    f"Found versions: {', '.join(node_version_details)}"
                )

    # Return the first successful connection for backward compatibility
    for result in version_results:
        if result["status"] == "connected":
            return result["version_string"], result["version_info"]

    logger.warning("Could not determine Counterparty version: All node connections failed.")
    return None, None


def software_version():
    logger.info("Software version: {}.".format(config.VERSION_STRING or ""))
