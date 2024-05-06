import logging
import warnings

import config
import index_core.util as util

logger = logging.getLogger(__name__)

CONSENSUS_HASH_SEED = 'Through our eyes, the universe is perceiving itself. Through our ears, the universe is listening to its harmonies.'

CONSENSUS_HASH_VERSION_MAINNET = 1

CHECKPOINTS_MAINNET = {
    config.CP_STAMP_GENESIS_BLOCK: {'ledger_hash': '', 'txlist_hash': '9054d12fff9a20677687906c91d1b196e2d834dc34fb275f2dc54d8c8834cf9d'},
    779700: {'ledger_hash': '', 'txlist_hash': '05b787543b02aa92aa2a243187a762e2f7a95b412a8ea105677fcc220680d302'},
    780000: {'ledger_hash': '', 'txlist_hash': 'dd5867614a040d3a90d2a19efe8ae2317cb60f6d7236bb20191de1e8b0a86ed6'},
    781000: {'ledger_hash': '', 'txlist_hash': 'fd8156664b44b54dba1364ce0a0a78eb0fd6d5bb2c831559337aab2370c0c294'},
    781100: {'ledger_hash': '', 'txlist_hash': 'facb1127746e4d82fbf47706c3fb4a4f38314251452991d5ba9be008d22812fd'},
    781300: {'ledger_hash': '', 'txlist_hash': 'dd70a1179c22ed68d15f906cf3fc2f1f72a0250d7bfcdfd00ba04e1339189756'},
    785000: {'ledger_hash': '', 'txlist_hash': '96f626e23f8f10b9349dba8250db9c7c48d1e5bad8e5997f8762ac2ead9586ab'},
    788041: {'ledger_hash': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'txlist_hash': '45589cad7fdb28b6ddeea9aa0ee297a58b0f3208e46f81321626a6e4c6826013'},
    788090: {'ledger_hash': '83c426eb5c4a6ac1886c54cd81e4f62f20f6e655e34fa324097111300ab3bc79', 'txlist_hash': 'f43e1933447846fd6797828997d0ab7be739670755c7c1393bbc212ae4af86f5'},
    788130: {'ledger_hash': 'f211278d9c26f4a0c01bc3b22b05ce898c09196f25f7dc601615ab815483bd9f', 'txlist_hash': '667b0fe52a4109c2c4a82789324e6056a909be6ffacf7463f2842d3988467c1d'},
    790000: {'ledger_hash': '', 'txlist_hash': '68d522a0eeebbe4fde146191613d18f5b26ca8372fe639ac4da0ceb3ab746ad5'},
    795000: {'ledger_hash': '', 'txlist_hash': 'e6b33fa56c627ebb96b4207113e70fb449ed86e05c77b43f2b1df3be7edf225b'},
    800000: {'ledger_hash': '', 'txlist_hash': 'e501d2da22d021d3adeb35b1ae10751454b94dce3a11402cca153c45955e40b1'},
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
        cursor.execute('''UPDATE blocks SET {} = %s WHERE block_index = %s'''.format(field), (calculated_hash, block_index))

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

