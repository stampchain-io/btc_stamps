import logging
import warnings

import config
import src.util as util
# from src.xcprequest import get_cp_version

logger = logging.getLogger(__name__)

CONSENSUS_HASH_SEED = 'Through our eyes, the universe is perceiving itself. Through our ears, the universe is listening to its harmonies.'

CONSENSUS_HASH_VERSION_MAINNET = 1

CHECKPOINTS_MAINNET = {
    config.BLOCK_FIRST_MAINNET: {'ledger_hash': '', 'txlist_hash': '40591672fcfed80ef211c245290bf1545078ad6a2403a74ef7491a8c69df969c'},
    779700: {'ledger_hash': '', 'txlist_hash': '689bab1f3e4e3ac1ed3de15a63cadfc506afa83b3a138de15efc671b34940f66'},
    781000: {'ledger_hash': '', 'txlist_hash': 'a39aa5e61811269e294cc8d71382c9c6faec630a5b959d63f3721d2a305b23e4'},
    781100: {'ledger_hash': '', 'txlist_hash': '4a48e68419e983b88f32975631b917e2f5b28aa3b7de784e5297faa44782bdf4'},
    781300: {'ledger_hash': '', 'txlist_hash': '19238b49941bb884b06b6f7b39f7741f76651c56d63cd0645cc059d2d4991ef2'},
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


def consensus_hash(db, field, previous_consensus_hash, content):
    field_position = config.BLOCK_FIELDS_POSITION
    cursor = db.cursor()
    block_index = util.CURRENT_BLOCK_INDEX

    # initialize previous hash on first block.
    if block_index <= config.BLOCK_FIRST and field != 'ledger_hash':
        assert not previous_consensus_hash
        previous_consensus_hash = util.dhash_string(CONSENSUS_HASH_SEED)
    elif block_index == config.CP_SRC20_GENESIS_BLOCK + 1 and field == 'ledger_hash':
        assert not previous_consensus_hash
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
        raise ConsensusError('Incorrect {} hash for block {}.  Calculated {} but expected {}'.format(field, block_index, calculated_hash, checkpoints[block_index][field],))

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
