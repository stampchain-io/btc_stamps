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
            to_include = whitelist.get('to_include', [])
            detected_now_was_not_prior_tbd = whitelist.get('detected_now_was_not_prior_tbd', [])
        return tx_hash in to_include or tx_hash in detected_now_was_not_prior_tbd
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
        invalid_src20_before_activation = whitelist.get('invalid_src20_before_activation', [])
        temporary_include  = whitelist.get('temporary_include', [])
        return tx_hash in invalid_src20_no_keyburn or tx_hash in reissue or tx_hash in invalid_src20_before_activation or tx_hash in temporary_include
    except FileNotFoundError:
        print(f"The file {whitelist_path} was not found.")
        return False
    except json.JSONDecodeError:
        print(f"The file {whitelist_path} is not a valid JSON file.")
        return False