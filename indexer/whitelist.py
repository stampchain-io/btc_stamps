import json

# DEBUG ONLY 

def is_tx_in_whitelist(tx_hash):
    whitelist_path = 'whitelist.json'
    try:
        with open(whitelist_path, 'r') as file:
            whitelist = json.load(file)
        return tx_hash in whitelist.get('op_return', [])
    except FileNotFoundError:
        print(f"The file {whitelist_path} was not found.")
        return False
    except json.JSONDecodeError:
        print(f"The file {whitelist_path} is not a valid JSON file.")
        return False

def is_to_include(tx_hash):
    whitelist_path = 'whitelist.json'
    try:
        with open(whitelist_path, 'r') as file:
            whitelist = json.load(file)
        return tx_hash in whitelist.get('to_include', [])
    except FileNotFoundError:
        print(f"The file {whitelist_path} was not found.")
        return False
    except json.JSONDecodeError:
        print(f"The file {whitelist_path} is not a valid JSON file.")
        return False

def is_to_exclude(tx_hash):
    whitelist_path = 'whitelist.json'
    try:
        with open(whitelist_path, 'r') as file:
            whitelist = json.load(file)
        invalid_src20_no_keyburn = whitelist.get('invalid_src20_no_keyburn', [])
        reissue = whitelist.get('reissue', [])
        invalid_src2_before_activation = whitelist.get('invalid_src2_before_activation', [])
        return tx_hash in invalid_src20_no_keyburn or tx_hash in reissue or tx_hash in invalid_src2_before_activation
    except FileNotFoundError:
        print(f"The file {whitelist_path} was not found.")
        return False
    except json.JSONDecodeError:
        print(f"The file {whitelist_path} is not a valid JSON file.")
        return False