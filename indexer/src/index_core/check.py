import logging
import warnings

import src.config as config
import src.index_core.util as util

logger = logging.getLogger(__name__)

CONSENSUS_HASH_SEED = 'Through our eyes, the universe is perceiving itself. Through our ears, the universe is listening to its harmonies.'

CONSENSUS_HASH_VERSION_MAINNET = 1

CHECKPOINTS_MAINNET = {
    config.CP_STAMP_GENESIS_BLOCK: {'ledger_hash': '', 'txlist_hash': '9054d12fff9a20677687906c91d1b196e2d834dc34fb275f2dc54d8c8834cf9d'},
    779700: {'ledger_hash': '', 'txlist_hash': '05b787543b02aa92aa2a243187a762e2f7a95b412a8ea105677fcc220680d302'},
    780000: {'ledger_hash': '', 'txlist_hash': 'dd5867614a040d3a90d2a19efe8ae2317cb60f6d7236bb20191de1e8b0a86ed6'},
    781000: {'ledger_hash': '', 'txlist_hash': 'fd8156664b44b54dba1364ce0a0a78eb0fd6d5bb2c831559337aab2370c0c294'},
    781141: {'ledger_hash': '', 'txlist_hash': 'cf5d627ffb6a8eea2065884a56810e1a696a97228a24319b1743da43aee18f14'},  # first cursed
    781100: {'ledger_hash': '', 'txlist_hash': 'facb1127746e4d82fbf47706c3fb4a4f38314251452991d5ba9be008d22812fd'},
    781300: {'ledger_hash': '', 'txlist_hash': 'dd70a1179c22ed68d15f906cf3fc2f1f72a0250d7bfcdfd00ba04e1339189756'},
    782285: {'ledger_hash': '', 'txlist_hash': 'f712708dd191802e9e1903cbad19ca58fc159fbec4eeb2026bfed917815ff38d'},  # first svg stamp
    785000: {'ledger_hash': '', 'txlist_hash': '96f626e23f8f10b9349dba8250db9c7c48d1e5bad8e5997f8762ac2ead9586ab'},
    788041: {'ledger_hash': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'txlist_hash': '45589cad7fdb28b6ddeea9aa0ee297a58b0f3208e46f81321626a6e4c6826013'},

    788127: {'ledger_hash': '32fac3ac1708f5ad22ee9537752e187307b692b069d68dc8fcaf93210421cd16', 'txlist_hash': '6e10dbd660ed929dc32e430d010e300d39c92018d99f63d1d5e83a52be327410'},
    788134: {'ledger_hash': '1d9fd11b3fb6b96a1a9ae676bf84d674316f05dbec2d489709ebbbf48c1a0d84', 'txlist_hash': '93a3dbef0ec5f194c461f0c9448269d670b5063983842c1dff5cb3bb73a5d0ef'},

    790000: {'ledger_hash': '', 'txlist_hash': '68d522a0eeebbe4fde146191613d18f5b26ca8372fe639ac4da0ceb3ab746ad5'},
    795000: {'ledger_hash': '', 'txlist_hash': '8d28ff2c1ba020bada48c6b9fe191b64f0442f5dc4b1d968b5656bd640868e00'},
    800000: {'ledger_hash': '', 'txlist_hash': 'ac420148167f197e17841387b81685162c0dda13dcc5671867af842a4a466540'},
    805000: {'ledger_hash': '', 'txlist_hash': 'b673db6ec0f2790b24b896248a54eaefcd47b970a474806f5f340d12ae095650'},
    810000: {'ledger_hash': '', 'txlist_hash': '41ab342679fac87a4f35a8ecf43b575ad700b65b98817d9acf3d710bf19a9102'},
    815000: {'ledger_hash': '', 'txlist_hash': '9fdef899ae689dc8dcd567fbf642dbced3759c8596e2639c19a27c7e23b87d08'},
    820000: {'ledger_hash': 'aee64e20dc83d09852c78c3caa9c39a61e77c0fa946843f39838963046f15932', 'txlist_hash': '1570e6066de3a38161b583533d59d37f42e9b758a3799bbda6947b10332ef1fd'},
    825000: {'ledger_hash': '68e0621468999995719b13a974ed53047c88b63bb4c211f30c63d7afd0a52159', 'txlist_hash': '7dbe4be3a8bff790618a4453f3a10ab0d0f9f865d40a5b0df80ef5a7d745d368'},
    830000: {'ledger_hash': 'e3bb684fba10cedf0dc5778a85aab66a42e500fad5405fe245a5bf80f313523b', 'txlist_hash': 'dfb1ce285bae78e5910569a3eff13e6476e7f0ba33002540e76d458944e00e0a'},
    835000: {'ledger_hash': '78e5d16e8802ea0d751bee5d9df2411b71f64032ae5ad7b98aec1617ecb082a3', 'txlist_hash': '152292be3ef84e2aa636ad3476db1c6a345c47179cf9c84734cd15a1e8280a0d'},
    840000: {'ledger_hash': '', 'txlist_hash': '971ea871bc0c5a6a2c89fe74d038cf1957d2d655328efd65e53101e4e256b868'},

}

CONSENSUS_HASH_VERSION_TESTNET = 7
CHECKPOINTS_TESTNET = {
    config.BLOCK_FIRST_TESTNET: {'ledger_hash': '', 'txlist_hash': ''},
}

CONSENSUS_HASH_VERSION_REGTEST = 1
CHECKPOINTS_REGTEST = {
    config.BLOCK_FIRST_REGTEST: {'ledger_hash': '', 'txlist_hash': ''},
}


class ConsensusError(Exception):
    pass


def consensus_hash(db, block_index, field, previous_consensus_hash, content):
    field_position = config.BLOCK_FIELDS_POSITION
    cursor = db.cursor()
    # block_index = util.CURRENT_BLOCK_INDEX

    # initialize previous hash on first block.
    if block_index <= config.BLOCK_FIRST and field != 'ledger_hash':
        if previous_consensus_hash:
            raise ConsensusError('Expected previous_consensus_hash to be unset for the first block.')
        previous_consensus_hash = util.dhash_string(CONSENSUS_HASH_SEED)
    elif block_index == config.CP_SRC20_GENESIS_BLOCK + 1 and field == 'ledger_hash':
        if previous_consensus_hash:
            raise ConsensusError('Expected previous_consensus_hash to be unset for the SRC20 genesis block.')
        previous_consensus_hash = util.shash_string('')

    # Get previous hash.
    if not previous_consensus_hash and field != 'ledger_hash':
        try:
            cursor.execute('''SELECT * FROM blocks WHERE block_index = %s''', (block_index - 1,))
            results = cursor.fetchall()
            if results:
                previous_consensus_hash = results[0][field_position[field]]
            else:
                previous_consensus_hash = None
        except IndexError:
            previous_consensus_hash = None
        if not previous_consensus_hash:
            raise ConsensusError('Empty previous {} for block {}. Please launch a `reparse`.'.format(field, block_index))
    elif not previous_consensus_hash and field == 'ledger_hash' and content != '':
        cursor.execute('''SELECT ledger_hash FROM blocks WHERE ledger_hash IS NOT NULL AND ledger_hash <> '' ORDER BY block_index DESC LIMIT 1''')
        result = cursor.fetchone()
        previous_consensus_hash = result[0] if result else None
        if not previous_consensus_hash:
            raise ConsensusError(f'Empty previous {field} for block {block_index}. Please launch a `reparse`.')

    # Calculate current hash.
    if config.TESTNET:
        consensus_hash_version = CONSENSUS_HASH_VERSION_TESTNET
    elif config.REGTEST:
        consensus_hash_version = CONSENSUS_HASH_VERSION_REGTEST
    else:
        consensus_hash_version = CONSENSUS_HASH_VERSION_MAINNET

    if field == 'ledger_hash' and block_index == config.CP_SRC20_GENESIS_BLOCK:
        calculated_hash = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    elif field == 'ledger_hash' and block_index > config.CP_SRC20_GENESIS_BLOCK and content:
        concatenated_content = previous_consensus_hash.encode('utf-8') + content.encode('utf-8')
        calculated_hash = util.shash_string(concatenated_content)
    elif field == 'ledger_hash' and content == '':
        calculated_hash = ''
    else:
        calculated_hash = util.dhash_string(previous_consensus_hash + '{}{}'.format(consensus_hash_version, ''.join(content)))
    # Verify hash (if already in database) or save hash (if not).
    cursor.execute('''SELECT * FROM blocks WHERE block_index = %s''', (block_index,))
    results = cursor.fetchall()
    if results:
        found_hash = results[0][config.BLOCK_FIELDS_POSITION[field]]
    else:
        found_hash = None
    if found_hash and field != 'messages_hash':
        # Check against existing value.
        if calculated_hash != found_hash:
            raise ConsensusError('Inconsistent {} for block {} (calculated {}, vs {} in database).'.format(
                field, block_index, calculated_hash, found_hash))
    else:
        # Save new hash.
        cursor.execute('''UPDATE blocks SET {} = %s WHERE block_index = %s'''.format(field), (calculated_hash, block_index))  # nosec

    # Check against checkpoints.
    if config.TESTNET:
        checkpoints = CHECKPOINTS_TESTNET
    elif config.REGTEST:
        checkpoints = CHECKPOINTS_REGTEST
    else:
        checkpoints = CHECKPOINTS_MAINNET

    if field != 'messages_hash' and block_index in checkpoints and checkpoints[block_index][field] != calculated_hash:
        raise ConsensusError('Incorrect {} consensus hash for block {}.  Calculated {} but expected {}'.format(field, block_index, calculated_hash, checkpoints[block_index][field],))

    return calculated_hash, found_hash


class VersionError(Exception):
    pass


class VersionUpdateRequiredError(VersionError):
    pass


# TODO: https://github.com/stampchain-io/btc_stamps/issues/13
def check_change(protocol_change, change_name):

    # Check client version.
    passed = True
    if config.VERSION_MAJOR < protocol_change['minimum_version_major']:
        passed = False
    elif config.VERSION_MAJOR == protocol_change['minimum_version_major']:
        if config.VERSION_MINOR < protocol_change['minimum_version_minor']:
            passed = False
        elif config.VERSION_MINOR == protocol_change['minimum_version_minor']:
            if config.VERSION_REVISION < protocol_change['minimum_version_revision']:
                passed = False
    # passed = True # Removing version check for now

    if not passed:
        explanation = 'Your version of {} is v{}, but, as of block {}, the minimum version is v{}.{}.{}. Reason: ‘{}’. Please upgrade to the latest version and restart the server.'.format(
            config.APP_NAME, config.VERSION_STRING, protocol_change['block_index'], protocol_change['minimum_version_major'], protocol_change['minimum_version_minor'],
            protocol_change['minimum_version_revision'], change_name)
        if util.CURRENT_BLOCK_INDEX >= protocol_change['block_index']:
            raise VersionUpdateRequiredError(explanation)
        else:
            warnings.warn(explanation)


def cp_version():
    # cp_version = get_cp_version()
    # FIXME: Finish version checking validation.
    return


def software_version():
    logger.warning('Software version: {}.'.format(config.VERSION_STRING))
