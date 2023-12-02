import binascii
from Crypto.Cipher import ARC4


def init_arc4(seed):
    if isinstance(seed, str):
        seed = binascii.unhexlify(seed)
    return ARC4.new(seed)


def arc4_decrypt_chunk(cyphertext, key):
    '''Un-obfuscate. initialize key once per attempt.'''
    # This  is modified  for stamps since in parse_stamp we were getting the key and then converting to a byte string in 2 steps. 
    return key.decrypt(cyphertext)
