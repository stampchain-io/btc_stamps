import bitcoin as bitcoinlib
import binascii

import config
import src.exceptions as exceptions


def get_asm(scriptpubkey):
    # TODO: When is an exception thrown here? Can this `try` block be tighter? Can it be replaced by a conditional?
    try:
        asm = []
        # TODO: This should be `for element in scriptpubkey`.
        for op in scriptpubkey:
            if type(op) == bitcoinlib.core.script.CScriptOp:
                # TODO: `op = element`
                asm.append(str(op))
            else:
                # TODO: `data = element` (?)
                asm.append(op)
    except bitcoinlib.core.script.CScriptTruncatedPushDataError:
        raise exceptions.PushDataDecodeError('invalid pushdata due to truncation')
    if not asm:
        raise exceptions.DecodeError('empty output')
    return asm


# Stamp Version
def get_checkmultisig(asm): #this is for any multisig in the correct format
    keyburn = None
    # convert asm[3] bytes to string for comparison against burnkeys
    asm3_str = binascii.hexlify(asm[3]).decode("utf-8")
    if len(asm) == 6 and asm[0] == 1 and asm[4] == 3 and asm[5] == 'OP_CHECKMULTISIG':
        pubkeys, signatures_required = asm[1:3], asm[0]
        # print("pubkeys from get_checkmultisig", pubkeys)
        if  asm3_str in config.BURNKEYS:
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
