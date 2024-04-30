import bitcoin as bitcoinlib
import binascii


import config
import src.exceptions as exceptions


def get_asm_optimized(scriptpubkey):
    try:
        asm = []
        for element in scriptpubkey:
            if isinstance(element, bitcoinlib.core.script.CScriptOp):
                asm.append(str(element))
            else:
                asm.append(element)
    except bitcoinlib.core.script.CScriptTruncatedPushDataError:
        raise exceptions.PushDataDecodeError('invalid pushdata due to truncation')
    if not asm:
        raise exceptions.DecodeError('empty output')
    return asm


def get_p2wsh(asm):
    if len(asm) == 2 and asm[0] == 0:
        return [bytes(asm[1])]
    raise exceptions.DecodeError('Invalid P2WSH')


# Stamp Version
def get_checkmultisig(asm):  # this is for any multisig in the correct format
    keyburn = None
    # convert asm[3] bytes to string for comparison against burnkeys
    asm3_str = binascii.hexlify(asm[3]).decode("utf-8")
    if len(asm) == 6 and asm[0] == 1 and asm[4] == 3 and asm[5] == 'OP_CHECKMULTISIG':
        pubkeys, signatures_required = asm[1:3], asm[0]
        # print("pubkeys from get_checkmultisig", pubkeys)
        if asm3_str in config.BURNKEYS:
            keyburn = 1
        return pubkeys, signatures_required, keyburn
    raise exceptions.DecodeError('invalid OP_CHECKMULTISIG')

# CP Version
# def get_checkmultisig(asm):
#     # N‐of‐2
#     if len(asm) == 5 and asm[3] == 2 and asm[4] == 'OP_CHECKMULTISIG':
#         pubkeys, signatures_required = asm[1:3], asm[0]
#         if all([type(pubkey) == bytes for pubkey in pubkeys]):
#             return pubkeys, signatures_required
#     # N‐of‐3
#     if len(asm) == 6 and asm[4] == 3 and asm[5] == 'OP_CHECKMULTISIG':
#         pubkeys, signatures_required = asm[1:4], asm[0]
#         if all([type(pubkey) == bytes for pubkey in pubkeys]):
#             return pubkeys, signatures_required
#     raise exceptions.DecodeError('invalid OP_CHECKMULTISIG')
