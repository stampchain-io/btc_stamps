import logging
import warnings

import config
import src.util as util
from xcprequest import get_cp_version

logger = logging.getLogger(__name__)

''' this is the consensus hash for counterparty. needs to be updated for stamps'''

CONSENSUS_HASH_SEED = 'We can only see a short distance ahead, but we can see plenty there that needs to be done.'

CONSENSUS_HASH_VERSION_MAINNET = 2

# TODO: https://github.com/stampchain-io/btc_stamps/issues/12 # NOTE: the txlist_hash is the same because we have not implemented in the consensus_hash check from balances StampTable, etc.
CHECKPOINTS_MAINNET = {
    config.BLOCK_FIRST_MAINNET: {'ledger_hash': '766ff0a9039521e3628a79fa669477ade241fc4c0ae541c3eae97f34b547b0b7', 'txlist_hash': '766ff0a9039521e3628a79fa669477ade241fc4c0ae541c3eae97f34b547b0b7'},
    779800: {'ledger_hash': '45b2b6391c08346a15a07cc7c8a270e917368141a2c1876bdb02752a0e127fa0', 'txlist_hash': '45b2b6391c08346a15a07cc7c8a270e917368141a2c1876bdb02752a0e127fa0'},
    780000: {'ledger_hash': '59ac77426870194dad46425f54344a3e80ae2de28d9fe72cdb607173219bd27c', 'txlist_hash': '59ac77426870194dad46425f54344a3e80ae2de28d9fe72cdb607173219bd27c'},
    785000: {'ledger_hash': 'a1f50cf22c62addc5b1c41c21fbc85b2e59a1c7e95acf306376f7bcc6a5ad045', 'txlist_hash': 'a1f50cf22c62addc5b1c41c21fbc85b2e59a1c7e95acf306376f7bcc6a5ad045'},
    790000: {'ledger_hash': '2cf5d02635f4d91bc3e35ec27b120ad45f2c753f0e3d15cbbe01bedd09e33e72', 'txlist_hash': '2cf5d02635f4d91bc3e35ec27b120ad45f2c753f0e3d15cbbe01bedd09e33e72'},
    795000: {'ledger_hash': 'e9cf3bcb17392954f03072b12908a58dd73b28e40e2e8d18d4d7ecc9d38131da', 'txlist_hash': 'e9cf3bcb17392954f03072b12908a58dd73b28e40e2e8d18d4d7ecc9d38131da'},
    800000: {'ledger_hash': 'fd87fd227eaa2ea2374f1d5db632a7ffe92e1c01080f2c7d6a71ee00ff96a063', 'txlist_hash': 'fd87fd227eaa2ea2374f1d5db632a7ffe92e1c01080f2c7d6a71ee00ff96a063'},
    805000: {'ledger_hash': '336896ddb26cb148237dd0b4abc43afdc6a7bf34cba6f7f0ae58545ae7e200f6', 'txlist_hash': '336896ddb26cb148237dd0b4abc43afdc6a7bf34cba6f7f0ae58545ae7e200f6'},
    810000: {'ledger_hash': '9d4cdced353649d75d933791e70ce344bb2b397545b18cffe66c109a39ea1356', 'txlist_hash': '9d4cdced353649d75d933791e70ce344bb2b397545b18cffe66c109a39ea1356'},
    815000: {'ledger_hash': 'e6891326abcc4e9ee27401f6c29cded4c57d123c942b408b91fcae1e0d952db2', 'txlist_hash': 'e6891326abcc4e9ee27401f6c29cded4c57d123c942b408b91fcae1e0d952db2'},
    820000: {'ledger_hash': '9b24657edda4da25ba1ab1f03890238591f5219a0b5da1945a231872fbbb903f', 'txlist_hash': '9b24657edda4da25ba1ab1f03890238591f5219a0b5da1945a231872fbbb903f'}
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
    # NOTE: do not enforce this for messages_hashes, those are more informational (for now at least)
    cursor.execute('''SELECT * FROM blocks WHERE block_index = %s''', (block_index,))
    results = cursor.fetchall()
    if results:
        found_hash = results[0][field]
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
    logger.warning("Checking for CP version")
    cp_version = get_cp_version()
    logger.warning('Running counterparty-lib version {}'.format(cp_version))
    # FIXME: Finish version checking validation.
    return
