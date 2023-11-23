"""
None of the functions/objects in this module need be passed `db`.

Naming convention: a `pub` is either a pubkey or a pubkeyhash
"""

import hashlib
import bitcoin as bitcoinlib
import binascii

from bitcoin.core.key import CPubKey
from bitcoin.bech32 import CBech32Data


import src.util as util
import config
import src.exceptions as exceptions

b58_digits = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

class InputError (Exception):
    pass
class AddressError(Exception):
    pass
class MultiSigAddressError(AddressError):
    pass
class VersionByteError (AddressError):
    pass
class Base58Error (AddressError):
    pass
class Base58ChecksumError (Base58Error):
    pass


def validate(address, allow_p2sh=True):
    """Make sure the address is valid.

    May throw `AddressError`.
    """
    # Get array of pubkeyhashes to check.
    if is_multisig(address):
        pubkeyhashes = pubkeyhash_array(address)
    else:
        pubkeyhashes = [address]

    # Check validity by attempting to decode.
    for pubkeyhash in pubkeyhashes:
        try:
            if util.enabled('segwit_support'):
                if not is_bech32(pubkeyhash):
                    base58_check_decode(pubkeyhash, config.ADDRESSVERSION)
            else:
                base58_check_decode(pubkeyhash, config.ADDRESSVERSION)
        except VersionByteError as e:
            if not allow_p2sh:
                raise e
            base58_check_decode(pubkeyhash, config.P2SH_ADDRESSVERSION)
        except Base58Error as e:
            if not util.enabled('segwit_support') or not is_bech32(pubkeyhash):
                raise e



def base58_encode(binary):
    """Encode the address in base58."""
    # Convert big‐endian bytes to integer
    n = int('0x0' + util.hexlify(binary), 16)

    # Divide that integer into base58
    res = []
    while n > 0:
        n, r = divmod(n, 58)
        res.append(b58_digits[r])
    res = ''.join(res[::-1])

    return res


def base58_check_encode(original, version):
    """Check if base58 encoding is valid."""
    b = binascii.unhexlify(bytes(original, 'utf-8'))
    d = version + b

    binary = d + util.dhash(d)[:4]
    res = base58_encode(binary)

    # Encode leading zeros as base58 zeros
    czero = 0
    pad = 0
    for c in d:
        if c == czero:
            pad += 1
        else:
            break

    address = b58_digits[0] * pad + res

    if original != util.hexlify(base58_check_decode(address, version)):
        raise AddressError('encoded address does not decode properly')

    return address


def base58_decode(s):
    # Convert the string to an integer
    n = 0
    for c in s:
        n *= 58
        if c not in b58_digits:
            raise Base58Error('Not a valid Base58 character: ‘{}’'.format(c))
        digit = b58_digits.index(c)
        n += digit

    # Convert the integer to bytes
    h = '%x' % n
    if len(h) % 2:
        h = '0' + h
    res = binascii.unhexlify(h.encode('utf8'))

    # Add padding back.
    pad = 0
    for c in s[:-1]:
        if c == b58_digits[0]:
            pad += 1
        else:
            break
    k = b'\x00' * pad + res

    return k


def base58_check_decode_parts(s):
    """Decode from base58 and return parts."""

    k = base58_decode(s)

    addrbyte, data, chk0 = k[0:1], k[1:-4], k[-4:]

    return addrbyte, data, chk0


def base58_check_decode(s, version):
    """Decode from base58 and return data part."""

    addrbyte, data, chk0 = base58_check_decode_parts(s)

    if addrbyte != version:
        raise VersionByteError('incorrect version byte')

    chk1 = util.dhash(addrbyte + data)[:4]
    if chk0 != chk1:
        raise Base58ChecksumError('Checksum mismatch: 0x{} ≠ 0x{}'.format(util.hexlify(chk0), util.hexlify(chk1)))

    return data


def is_multisig(address):
    """Check if the address is multi‐signature."""
    array = address.split('_')
    return len(array) > 1

def is_p2sh(address):
    if is_multisig(address):
        return False

    try:
        base58_check_decode(address, config.P2SH_ADDRESSVERSION)
        return True
    except (VersionByteError, Base58Error):
        return False

def is_bech32(address):
    try:
        b32data = CBech32Data(address)
        return True
    except:
        return False

def is_fully_valid(pubkey_bin):
    """Check if the public key is valid."""
    cpubkey = CPubKey(pubkey_bin)
    return cpubkey.is_fullyvalid

def make_canonical(address):
    """Return canonical version of the address."""
    if is_multisig(address):
        signatures_required, pubkeyhashes, signatures_possible = extract_array(address)
        try:
            [base58_check_decode(pubkeyhash, config.ADDRESSVERSION) for pubkeyhash in pubkeyhashes]
        except Base58Error:
            raise MultiSigAddressError('Multi‐signature address must use PubKeyHashes, not public keys.')
        return construct_array(signatures_required, pubkeyhashes, signatures_possible)
    else:
        return address

def test_array(signatures_required, pubs, signatures_possible):
    """Check if multi‐signature data is valid."""
    try:
        signatures_required, signatures_possible = int(signatures_required), int(signatures_possible)
    except (ValueError, TypeError):
        raise MultiSigAddressError('Signature values not integers.')
    if signatures_required < 1 or signatures_required > 3:
        raise MultiSigAddressError('Invalid signatures_required.')
    if signatures_possible < 2 or signatures_possible > 3:
        raise MultiSigAddressError('Invalid signatures_possible.')
    for pubkey in pubs:
        if '_' in pubkey:
            raise MultiSigAddressError('Invalid characters in pubkeys/pubkeyhashes.')
    if signatures_possible != len(pubs):
        raise InputError('Incorrect number of pubkeys/pubkeyhashes in multi‐signature address.')

def construct_array(signatures_required, pubs, signatures_possible):
    """Create a multi‐signature address."""
    test_array(signatures_required, pubs, signatures_possible)
    address = '_'.join([str(signatures_required)] + sorted(pubs) + [str(signatures_possible)])
    return address

def extract_array(address):
    """Extract data from multi‐signature address."""
    assert is_multisig(address)
    array = address.split('_')
    signatures_required, pubs, signatures_possible = array[0], sorted(array[1:-1]), array[-1]
    test_array(signatures_required, pubs, signatures_possible)
    return int(signatures_required), pubs, int(signatures_possible)

def pubkeyhash_array(address):
    """Return PubKeyHashes from an address."""
    signatures_required, pubs, signatures_possible = extract_array(address)
    if not all([is_pubkeyhash(pub) for pub in pubs]):
        raise MultiSigAddressError('Invalid PubKeyHashes. Multi‐signature address must use PubKeyHashes, not public keys.')
    pubkeyhashes = pubs
    return pubkeyhashes

def hash160(x):
    x = hashlib.sha256(x).digest()
    m = hashlib.new('ripemd160')
    m.update(x)
    return m.digest()

def pubkey_to_pubkeyhash(pubkey):
    """Convert public key to PubKeyHash."""
    pubkeyhash = hash160(pubkey)
    pubkey = base58_check_encode(binascii.hexlify(pubkeyhash).decode('utf-8'), config.ADDRESSVERSION)
    return pubkey

def pubkey_to_p2whash(pubkey):
    """Convert public key to PayToWitness."""
    pubkeyhash = hash160(pubkey)
    pubkey = CBech32Data.from_bytes(0, pubkeyhash)
    return str(pubkey)

def bech32_to_scripthash(address):
    bech32 = CBech32Data(address)
    return bytes(bech32)

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

def get_checksig(asm):
    if len(asm) == 5 and asm[0] == 'OP_DUP' and asm[1] == 'OP_HASH160' and asm[3] == 'OP_EQUALVERIFY' and asm[4] == 'OP_CHECKSIG':
        pubkeyhash = asm[2]
        if type(pubkeyhash) == bytes:
            return pubkeyhash
    raise exceptions.DecodeError('invalid OP_CHECKSIG')

# Stamp Version
def get_checkmultisig(asm): #this is for any multisig in the correct format
    keyburn = None
    # convert asm[3] bytes to string for comparison against burnkeys
    asm3_str = binascii.hexlify(asm[3]).decode("utf-8")
    if len(asm) == 6 and asm[0] == 1 and asm[4] == 3 and asm[5] == 'OP_CHECKMULTISIG':
        pubkeys, signatures_required = asm[1:3], asm[0]
        # print("pubkeys from get_checkmultisig", pubkeys)
        if  asm3_str in config.BURNKEYS:
            keyburn = True
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

def scriptpubkey_to_address(scriptpubkey):
    asm = get_asm(scriptpubkey)

    if asm[-1] == 'OP_CHECKSIG':
        try:
            checksig = get_checksig(asm)
        except exceptions.DecodeError:  # coinbase
            return None

        return base58_check_encode(binascii.hexlify(checksig).decode('utf-8'), config.ADDRESSVERSION)

    elif asm[-1] == 'OP_CHECKMULTISIG':
        pubkeys, signatures_required = get_checkmultisig(asm)
        pubkeyhashes = [pubkey_to_pubkeyhash(pubkey) for pubkey in pubkeys]
        return construct_array(signatures_required, pubkeyhashes, len(pubkeyhashes))

    elif len(asm) == 3 and asm[0] == 'OP_HASH160' and asm[2] == 'OP_EQUAL':
        return base58_check_encode(binascii.hexlify(asm[1]).decode('utf-8'), config.P2SH_ADDRESSVERSION)

    return None


def is_pubkeyhash(monosig_address):
    """Check if PubKeyHash is valid P2PKH address. """
    assert not is_multisig(monosig_address)
    try:
        base58_check_decode(monosig_address, config.ADDRESSVERSION)
        return True
    except (Base58Error, VersionByteError):
        return False

