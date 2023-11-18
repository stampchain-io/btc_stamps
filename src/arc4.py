import binascii
from Crypto.Cipher import ARC4

def init_arc4(seed):
    if isinstance(seed, str):
        seed = binascii.unhexlify(seed)
    return ARC4.new(seed)

def arc4_decrypt(cyphertext, ctx):
    '''Un‐obfuscate. initialize key once per attempt.'''
    key = arc4.init_arc4(ctx.vin[0].prevout.hash[::-1])
    return key.decrypt(cyphertext)


def arc4_decrypt(key, ciphertext): #input as a bytestring
    # Initialize the key schedule
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]

    # Decrypt the ciphertext
    plaintext = bytearray()
    i = j = 0
    for byte in ciphertext:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        k = S[(S[i] + S[j]) % 256]
        plaintext.append(byte ^ k)

    return plaintext
