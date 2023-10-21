from binascii import Error as DecodeError
import json
import logging
import binascii
# import the function arc4_decrypt from the file arc4.py
import arc4
import sys
import io
from config import RPC_URL
from config import decimal_default
# assert 'RPC_URL' in globals(), "RPC_URL is not defined"
from arc4 import arc4_decrypt
from config import getrawtransaction
# from config import getrawtransaction, getblockcount


from config import BURNKEYS, BYTE_LENGTH_PREFIX_SIZE, STAMP_PREFIX_HEX
from src20 import check_format

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

byte_length_prefix_size = BYTE_LENGTH_PREFIX_SIZE

block_height = 793847 # 793068 # first test trx in 793069 with only 1 byte for byte length
# prior to block 793846 we used a single byte for the byte length prefix

# tx = "6005ee8cc02e528e20c8e5ff71191723b0260391020862a03587a985f813dabe" # 793069
# tx = "1db33fe19983d26d9e228169a9092f26eca52d62ae656e3b7a51adf9b339a4d3" # 793069
# tx = "50aeb77245a9483a5b077e4e7506c331dc2f628c22046e7d2b4c6ad6c6236ae1" # two byte length prefix # 793487
tx = "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc"


def get_checkmultisig(asm):
    asm = asm.split(' ')  
    # print each component of the split asm 
    # for i in range(len(asm)):
    #     print(i, asm[i])

    if len(asm) == 6 and asm[0] == '1' and asm[4] == '3' and asm[5] == 'OP_CHECKMULTISIG' and asm[3] in BURNKEYS:
        pubkeys = asm[1:3]
        return pubkeys
    raise DecodeError('invalid OP_CHECKMULTISIG')


def stamp_tx_parse(tx, block_height):

    tx_dict = getrawtransaction(tx, verbose=True)

    print("block_height", block_height)

    pubkeys_hex = []
    print(json.dumps(tx_dict, indent=4, default=decimal_default))
    try:
        logger.debug("tx_dict: {}".format(tx_dict))
        rc4_key = tx_dict['vin'][0]['txid']
        rc4_key_bytes = binascii.unhexlify(rc4_key)

        for utxo in tx_dict['vout']:
            # print("utxo", utxo, "\n \n")
            if utxo['scriptPubKey'].get('type') == 'multisig':
                pk = get_checkmultisig(utxo['scriptPubKey']['asm'])
                pubkeys_hex.append(pk)
                # print("pubkeys", pubkeys)
        # print(" final pubkeys", pubkeys_hex)
        stripped_pubkeys_hex = [pubkey[2:-2] for sublist in pubkeys_hex for pubkey in sublist] # remove first/last byte, flatten the list
        joined_stripped_pubkeys_hex = ''.join(stripped_pubkeys_hex) # concatenate the pubkeys
        bytestring = bytes.fromhex(joined_stripped_pubkeys_hex) # convert the hex string to a bytestring - required for arc4_decrypt
        arc4_decrypted_byte_script = arc4_decrypt(rc4_key_bytes, bytestring) # decrypt the bytestring 
        hex_decrypted_script = arc4_decrypted_byte_script.hex() # convert the bytestring to hex - includes byte length prefix

        print("hex_decrypted_script", hex_decrypted_script)
        
        stripped_hex = hex_decrypted_script.rstrip('0') # strip trailing zeros
        print("stripped_hex", stripped_hex)

        # remove the first byte from stripped_hex
        stripped_hex = stripped_hex[byte_length_prefix_size*2:] # remove the first byte
        print("stripped_hex with byte(s) removed", stripped_hex)
        # byte_length = len(bytes.fromhex(stripped_hex)) # with padding removed
        # print("Byte length of hex string -- this is good as integer without the first byte removed.:", byte_length)

        expected_byte_length = arc4_decrypted_byte_script[:byte_length_prefix_size].hex() # get the byte length prefix firs two bytes
        print("hex_decrypted_script: {} byte_length_prefix_length {} expected_byte_len in hex {}".format(hex_decrypted_script, byte_length_prefix_size, expected_byte_length))
        
        arc4_decrypted_byte_script = arc4_decrypted_byte_script[byte_length_prefix_size:] # strip the byte length prefix (1 or 2 bytes)
        # Remove any trailing null bytes from the byte string
        arc4_decrypted_byte_script = arc4_decrypted_byte_script.rstrip(b'\x00')
        
        # Determine the length of the byte string without padding
        byte_script_length = len(arc4_decrypted_byte_script) # with padding removed
        # print("arc4_decrypted_byte_script", arc4_decrypted_byte_script)
        # print("length of string computed from byte_script in hex", hex(byte_script_length)) # ---- this is good 

        hex_decrypted_script_no_byte_length_prefix = arc4_decrypted_byte_script.hex()
        # print("hex_decrypted {}".format(hex_decrypted_script_no_byte_length_prefix))

        byte_script_length = len(arc4_decrypted_byte_script)
        # print("byte_script_length in hex", hex(byte_script_length))

        # check if byte_script_length = expected_byte_length
        if byte_script_length != int(expected_byte_length, 16):
            print("byte_script_length int ", byte_script_length, "expected_byte_length", expected_byte_length)
            logger.warning('invalid byte length prefix')
            return None
 
        # print("arc4_decrypted_byte_script", arc4_decrypted_byte_script)
        # if STAMP_PREFIX_HEX in hex_decrypted_script:
        if hex_decrypted_script_no_byte_length_prefix.startswith(STAMP_PREFIX_HEX):
            # strip the STAMP_PREFIX_HEX from the decrypted script
            hex_decrypted_script = hex_decrypted_script[hex_decrypted_script.index(STAMP_PREFIX_HEX) + len(STAMP_PREFIX_HEX):]
            print("hex_decrypted_script without stamp prefix {}".format(hex_decrypted_script))
            # utf-8 decode the hex_decrypted_script
            
            try:
                utf8_decrypted_script = bytes.fromhex(hex_decrypted_script).decode('utf-8')
                print(utf8_decrypted_script)
                src_dict = check_format(utf8_decrypted_script)
                if src_dict:
                    # print("src_dict", src_dict)
                    tx_dict['src_dict'] = src_dict
                    # print("tx_dict", tx_dict)
                    print("returning to import to db")
                    return tx_dict
                else:
                    return None
                # save to srcx table since we have a valid src transaction
            
            except UnicodeDecodeError:
                # Assume that the byte string is not valid UTF-8 and try to determine if it is binary data
                try:
                    # Attempt to open the byte string as an image (this is not ok for svg)
                    with Image.open(io.BytesIO(arc4_decrypted_byte_script)) as img:
                        # The byte string is an image
                        logger.debug("image format")
                        return tx_dict
                except:
                    # The byte string is not an image and should stay as a byte string
                    pass
                # Handle the UnicodeDecodeError exception here
                logger.error("Error: UnicodeDecodeError - invalid UTF-8 byte string")
                return None

            except ValueError:
                # Handle the ValueError exception here
                logger.error(f"Error: Invalid JSON string")
                return None

            except:
                # Handle any other exceptions here
                pass

            return tx_dict # do we want to save to the db here if the stamp json does not parse properly? 

        else:
            return None
    except:
        return None

print(RPC_URL)
# test = getblockcount() 
# print(test)
stamp_tx_parse(tx, 795419) #793487) # "793068") # "793487")



# tx_info = None
# if tx_info is None:
#     # print(tx_info,"\n")
#     tx_info_node = get_transaction_info_from_node(tx)
#     print(tx_info_node,"\n")
#     tx_info = tx_info_node
    
# else:
#     print("Failed to retrieve transaction info")

# messages = process_tx(tx_info)
# print(json.dumps(messages))

# stpes to decode:
# 1. do a rc4 decrypt. 
# 2. take the first 2 pubkeySripts
# 3. parse each one of them:
#     (1)ditch the first byte and last byte. that would give you 33 - 2 = 31 bytes. 
# 4. combine them
# 5. after that you get a hex string. the first byte of the hex is "byte count of the message". 
# 6. do a hex to utf-8 decode.