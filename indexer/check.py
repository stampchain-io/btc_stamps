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
    786000: {'ledger_hash': '56214ef0ca65e2e41bfa777e32712f5f71b805c68a1f1530cf98904d5d082d49', 'txlist_hash': '372e55054e19f756c666a4f789730824a98aa0c541033500df8a40071ee88dfd'},
    788000: {'ledger_hash': '475614b46d70e638321f3478c2f0c3064d73504f8e4b5b5d86e4e0f74b6f8d17', 'txlist_hash': '91b0a81e17a75e75cecf87a5fd2157457438405beae58f72606ecf5f26ffb014'},
    790000: {'ledger_hash': '5b0d103fb66718ad278cfb36beff1a65f568b1cd97504e58c3b12064e66cbbcb', 'txlist_hash': '97dda38074aea86e6f67a80eb93fa219d57db8c92795ecc1f6eb11a049cef373'},
    792000: {'ledger_hash': 'd59e3a6e0505bfa91cf75569e3323a9e1ea2aa2d9df4731fcdb3bb87d160fc23', 'txlist_hash': 'a0c17c35a2b4bb3afa4b6f624b462fd5b269b5efb0a5e70810a8640637605669'},
    794000: {'ledger_hash': '76c45133568ec1f99f8cf415deb623c42cc60e93e92e565c190e9dc09f4f0748', 'txlist_hash': '9ba618290936f226d59cfb93a3928fbe6d75c5ac83356edb926ed78962795eb2'},
    796000: {'ledger_hash': '6e5d703b23a1346d2c1da1c9e307c87d9c54498bbe761b9e6e19f3f87edbf61a', 'txlist_hash': '364a08e77216a43336db90d85cba695cacc9e7a186405a677b1f27c60a3eb24b'},
    798000: {'ledger_hash': 'de5d02859deb99628f15ec5c106383cb05b2113abfe7ecbcd2737a1814fd991a', 'txlist_hash': '880ad0523bd57c9034a37f3cc9a0e91f89b9b968607796884532f1c5d681311c'},
    800000: {'ledger_hash': 'c974045e77a2c13cd4c68146c8144eba1faa4c4c1d138e0ab7e93851362d8ba7', 'txlist_hash': 'ca8877287938ba474c1fa0710e0a66479f29aee06679e29c15603b53315934f7'},
    802000: {'ledger_hash': '876b6642dfde0fd903cdb7309bb0b852cea0c767606b8c417deacc7babc31b37', 'txlist_hash': 'cf46a1d386c96d2630acbd0cf998436ad7cf361b58e496a6be3853ef88932040'},
    804000: {'ledger_hash': '7a0f6557d5e5ece15bf90b09f01efea2e5543117c4e38353866611fe3d02b6a1', 'txlist_hash': 'dd31883491aa694f4f811bf34fc5228d493e2a9505c898ba5cd959494198f080'}
    806000: {'ledger_hash': '5997662bc2944ae506b6a70d86dd7f536e0ec0eed2449e0633fbe130d9518dd4', 'txlist_hash': '6372600b6a00ad9afdfb75cc2e9c2617c026e53876397169a6a4c66c5dfe9742'},
    808000: {'ledger_hash': 'f98ae6fcaf60821b969017c9f145edf988a16880211047cc6eeb1f5c78407b52', 'txlist_hash': '10a05c8e792b814e398ae9046e6c17949d4094d878534140df049ae8af2d0c15'},
    810000: {'ledger_hash': '491b692f8ad9f5064a0acbb61bb98a7bcb5136bc1d4a83e52a4e372d6831499c', 'txlist_hash': '0bb8b120e892e4c945469b066c97e6feeee6b9ce85535a8a105b8e62a59e0de0'},
    812000: {'ledger_hash': 'df62c8cb997374436cbdec61e7766f3b03767fdb3e6408b39b81f8e51178ee1c', 'txlist_hash': 'dfaffa8c028d1a662b9624bb53a0acbf08b2a51cd2498f13da290be86d82791a'},
    814000: {'ledger_hash': 'f922f032b9e39cf84a1220c3de97e09d0327487a4f4a22e3d413c9b143e0a780', 'txlist_hash': '2f4ff386cb0a2ec2a84f90a6fdc24952175c09f5d32610d1968844ed5078f8e7'},
    816000: {'ledger_hash': '416b5611ea84203208242d4372a118c13a794f64e65d4610ffa7ce72d2d60598', 'txlist_hash': 'de732cf071912c51611d9d02e7ef9da2101edb5c9e15eef41fd5df31986544bd'},
    818000: {'ledger_hash': '31c937907b412a171a88466b1325bcf4623ac2ff48255c9063ae0414d84fe7ef', 'txlist_hash': '749b40753dd86991a1986fafaddfad4ad759829617084b16361cd34c03f2c904'},
    820000: {'ledger_hash': 'ab66361a0a246520cc61d040b7bb0b966aa64e48732a7fd1de743819be5d1e5a', 'txlist_hash': 'c01196b868bac4f4f1b4727daf18125fbfaa6421c6fbcb78396913d8ca80be31'},

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
