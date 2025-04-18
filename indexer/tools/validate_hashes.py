#!/usr/bin/env python3

import json
import sys

from src.index_core.check import CHECKPOINTS_MAINNET


def validate_reference_hashes():
    try:
        with open("snapshots/reference_hashes.json", "r") as f:
            reference_data = json.load(f)

        ref_hashes = reference_data.get("hashes", {})

        print(f"Found {len(ref_hashes)} blocks in reference hashes")
        print(f"Found {len(CHECKPOINTS_MAINNET)} blocks in CHECKPOINTS_MAINNET")

        # Check each checkpoint block
        all_valid = True
        for block_index, expected in CHECKPOINTS_MAINNET.items():
            block_str = str(block_index)
            if block_str not in ref_hashes:
                print(f"Block {block_index} missing from reference_hashes.json")
                all_valid = False
                continue

            actual = ref_hashes[block_str]

            # Check txlist_hash
            if expected["txlist_hash"] != actual["txlist_hash"]:
                print(f"Block {block_index} txlist_hash mismatch!")
                print(f"   Expected: {expected['txlist_hash']}")
                print(f"   Actual:   {actual['txlist_hash']}")
                all_valid = False

            # Check ledger_hash if it exists in the checkpoint
            if expected.get("ledger_hash") and expected["ledger_hash"] != actual.get("ledger_hash", ""):
                print(f"Block {block_index} ledger_hash mismatch!")
                print(f"   Expected: {expected['ledger_hash']}")
                print(f"   Actual:   {actual.get('ledger_hash', '')}")
                all_valid = False

        if all_valid:
            print("All checkpoint hashes match reference_hashes.json")

        return all_valid

    except Exception as e:
        print(f"Error validating hashes: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    validate_reference_hashes()
