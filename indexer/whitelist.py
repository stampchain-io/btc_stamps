import json


def is_tx_in_whitelist(tx_hash):
    whitelist_path = 'indexer/whitelist.json'
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
