import json
import os
import sys

import requests


def get_transaction_hex(txid):
    """Get transaction hex from a Bitcoin RPC node."""
    try:
        # Use a public Bitcoin RPC service
        url = "https://blockstream.info/api/tx/" + txid + "/hex"
        response = requests.get(url)
        if response.status_code == 200:
            return response.text.strip()
        else:
            print(f"Error fetching transaction: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None


def test_transaction(parser, txid):
    """Test a specific transaction with the Rust parser."""
    print(f"\nTesting with transaction: {txid}")

    tx_hex = get_transaction_hex(txid)
    if tx_hex:
        print(f"Transaction hex fetched successfully ({len(tx_hex)} bytes)")

        # Test batch_parse_transactions
        results = parser.batch_parse_transactions([tx_hex])
        print(f"batch_parse_transactions result: {len(results)} transactions returned")

        if results:
            tx_info = results[0]
            print(f"Transaction included: {tx_info.should_include}")
            print(f"Transaction details:")
            print(f"  - txid: {tx_info.txid}")
            print(f"  - has_valid_pattern: {tx_info.has_valid_pattern}")
            print(f"  - has_valid_data: {tx_info.has_valid_data}")
            print(f"  - keyburn: {tx_info.keyburn}")
            print(f"  - outputs: {len(tx_info.outputs)}")

            # Print output details
            print(f"  - Output details:")
            for i, output in enumerate(tx_info.outputs):
                script_bytes = bytes.fromhex(output.script_hex)
                is_p2wsh = len(script_bytes) == 34 and script_bytes[0] == 0x00 and len(script_bytes[1:]) == 32
                print(
                    f"    Output #{i}: value={output.value}, is_p2wsh={is_p2wsh}, has_op_checkmultisig={output.has_op_checkmultisig}, keyburn={output.keyburn}"
                )
        else:
            print("No results returned")
    else:
        print("Failed to fetch transaction hex")


try:
    from btc_stamps_parser import FastTransactionParser

    print("Rust parser module imported successfully")

    # Create an instance of the parser
    parser = FastTransactionParser()
    print("Rust parser instance created successfully")

    # Test if the parser can deserialize a transaction
    print("Testing parser methods:")
    print(f"  - deserialize_transaction: {hasattr(parser, 'deserialize_transaction')}")
    print(f"  - batch_parse_transactions: {hasattr(parser, 'batch_parse_transactions')}")
    print(f"  - parse_block: {hasattr(parser, 'parse_block')}")

    # Test with specific transactions
    test_transaction(parser, "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2")
    test_transaction(parser, "359aefd7bf0bbd8398ee5c8c0f206799b78b158578f0f98e1e06bf58e70008dc")

except ImportError as e:
    print(f"Import error: {e}")
    print("Rust parser not available. Make sure to build it with 'poetry run maturin develop'")
except Exception as e:
    print(f"Error: {e}")
