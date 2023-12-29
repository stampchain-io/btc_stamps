import logging
import warnings

import config
import src.util as util
from xcprequest import get_cp_version

logger = logging.getLogger(__name__)

CONSENSUS_HASH_SEED = 'Through our eyes, the universe is perceiving itself. Through our ears, the universe is listening to its harmonies.'

CONSENSUS_HASH_VERSION_MAINNET = 1

CHECKPOINTS_MAINNET = {
    config.BLOCK_FIRST_MAINNET: {'ledger_hash': 'f55ff4daaf67d34eea686f1869e49e06646bc2fc2590de8489ce16e9e537e5ca', 'txlist_hash': '54d3c971e7aa7cebab9cc07a1922e00c05ec3eb190f0384034719f268bffbf1b'},

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
    if block_index <= config.BLOCK_FIRST:
        assert not previous_consensus_hash
        previous_consensus_hash = util.dhash_string(CONSENSUS_HASH_SEED)

    # Get previous hash.
    if not previous_consensus_hash:
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

    # Calculate current hash.
    if config.TESTNET:
        consensus_hash_version = CONSENSUS_HASH_VERSION_TESTNET
    elif config.REGTEST:
        consensus_hash_version = CONSENSUS_HASH_VERSION_REGTEST
    else:
        consensus_hash_version = CONSENSUS_HASH_VERSION_MAINNET

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
    cp_version = get_cp_version()
    # FIXME: Finish version checking validation.
    return
