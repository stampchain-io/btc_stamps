import binascii
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.backends import default_backend


def init_arc4(seed):
    if isinstance(seed, str):
        seed = binascii.unhexlify(seed)
    backend = default_backend()
    cipher = Cipher(algorithms.ARC4(seed), mode=None, backend=backend)  # nosec
    return cipher


def arc4_decrypt_chunk(cyphertext, key):
    '''Un-obfuscate. initialize key once per attempt.'''
    decryptor = key.decryptor()
    return decryptor.update(cyphertext) + decryptor.finalize()
