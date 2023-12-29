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
    780000: {'ledger_hash': '4fef3960cdd3b1909e6fecc3c82722ca9ba465d99182d2829f563f36d02191cc', 'txlist_hash': '175ccc866413d290ec0fe1b24c80226efb64522c94463c2d02e2b1d67982b009'},
    785000: {'ledger_hash': '153445deef0575b4acb51d34bd7d375234754eeda64888cdcb25ee26653b3a3d', 'txlist_hash': 'f3f070fc2860c1b50eba6a32e9bd7b3aeea618a4dc6f5baae6520a2572d89296'},
    790000: {'ledger_hash': '3896ff678bd8bc8fdc33d0223fc283b9259e8601240ef126f4fe46880e12b696', 'txlist_hash': '9ce603466a52c3bac450f6da28beb545411bf7ee89804c4077997b0c6c9fe9ca'},
    795000: {'ledger_hash': '10af6f6ddca0684fd2b1b6014ba576b6d1c7dc75864ed014f4373127193e4ab0', 'txlist_hash': '7da124c0b7529bef2890adffcada3149ac577bd0f21d19aaa41e861bfc86d239'},
    800000: {'ledger_hash': '794824a824de78069bc4479c6d26389ed5ae3ec237d52d6d79aa7cba9f615e9e', 'txlist_hash': '5f5eb91ace34334ec6ea70bda88b4c6d61f6be0694c9d625976e1fe2908972c6'},
    805000: {'ledger_hash': '31a12358cc5f65f186e44826a21bc8f7ea08e6c19318724fd14b5dec87405470', 'txlist_hash': '0c24970e3101f86f77ea4cbb1796cfddad6517b266be43dcd65b2de39342cee0'},
    810000: {'ledger_hash': '33b49e99bb4648deec1f737ff770ab60971b6fafecf9d4aaf2ae3df903918c35', 'txlist_hash': '422edb7f8145b605b74ed2e3ec466adce733bf45f0c30ca0f371c212bfdfc3e2'},
    815000: {'ledger_hash': '5b35773ba45425454e1eadd266f9d514f846b3d84e85fcdc49edae9e08befb2b', 'txlist_hash': 'fef34b155e6d1b87e87ad876f60a48161c31297bebb8a8b5a2f4e406d563953d'},
    820000: {'ledger_hash': '2eb433d136018498bfd535b6ac75b9b01fa7d373e3ab45f591a8038288e67c0c', 'txlist_hash': '57998f89eb5b3e494a083093541a2b43dab4e1ebc2158a26f02aada64fedc7a0'}
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
