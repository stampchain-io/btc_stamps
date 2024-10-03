import binascii

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4
from cryptography.hazmat.primitives.ciphers import Cipher


def init_arc4(seed):
    if isinstance(seed, str):
        seed = binascii.unhexlify(seed)
    backend = default_backend()
    cipher = Cipher(ARC4(seed), mode=None, backend=backend)  # nosec
    return cipher


def arc4_decrypt_chunk(cyphertext, key):
    """Un-obfuscate. initialize key once per attempt."""
    decryptor = key.decryptor()
    return decryptor.update(cyphertext) + decryptor.finalize()


def get_arc4_path():
    return ARC4.__module__
