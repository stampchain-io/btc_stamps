#!/usr/bin/env python
"""
Debug script to diagnose why transactions in block 865003 aren't appearing in the database.
This script specifically focuses on the src20.py processing pipeline.
"""

import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Add src to path
sys.path.insert(0, ".")

# Load environment variables from .env if exists
env_path = Path(".") / ".env"
if env_path.exists():
    logger.info(f"Loading environment variables from {env_path}")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key] = value

from btc_stamps_parser import FastTransactionParser

from src.index_core import arc4, blocks, script
from src.index_core.backend import Backend
from src.index_core.src20 import Src20Processor, Src20Validator, check_format, parse_src20

# Transactions from block 865003 as reported in the MySQL query
EXPECTED_TX_HASHES = [
    "c8c3831f6354831f1f14ee8f979c2b114d883c85653aae1c2d286ad351dfc30c",
    "8a68d7a9cf316014bc9f9a61583eced0dbf90db08e542639921ce235cd55f82e",
    "943200a9525381c5f128f1b889d0dd0c6a648f131b104b5db095fa82b5dd3304",
    "711ef8be4c0076b267e96afffd71907fd9388ea08e6d93564008e91a040e8d0c",
    "5e7d66b0b1d3bc28d8ed9211262592d44b601f148686a93cc372fc7e5a3bab71",
    "71aa8481fd179b56cbc125a95dad1c24e3146895f3d2dbe60875f549c1359fe7",
    "e70cfa82f5979405e715420af5533bfb8f8a99ec66177b4d6fc1ea790875c99c",
    "1e20a653c0824c10ed9401953927bef16cfaf43411f7d45165b88e252d8a9f48",
    "b7fc8ca93c23d2b0ef4c210147ec56df426139f85c6496db575ffe3c41beedea",
    "0fea78019487990814cfaba4c9b3fd861f70b3190886a659eaedc0bdc221d0ed",
    "3368bd06d79cc3a66a01d55cf81112e92affcb64022d7f1c78fafcad824ea426",
    "8730c7f8940706be7de6c28466b348703c8ddd48bf9a409a483265b7ded07d8e",
]


def extract_data_from_transaction(tx_hash, tx_hex, block_index):
    """Extract SRC-20 data from transaction."""
    logger.info(f"\n\n===== Analyzing transaction {tx_hash} =====")

    # Try to extract data using blocks module
    try:
        result = blocks.process_tx(None, tx_hash, block_index, None, {tx_hash: tx_hex})

        logger.info("Process_tx result:")
        if result:
            logger.info(f"TX Hash: {result.tx_hash}")
            logger.info(f"Source: {result.source}")
            logger.info(f"Destination: {result.destination}")
            logger.info(f"Keyburn: {result.keyburn}")
            logger.info(f"Is OP_RETURN: {result.is_op_return}")

            # Extract data content
            data_content = None
            if result.data:
                try:
                    if isinstance(result.data, bytes):
                        data_str = result.data.decode("utf-8")
                    else:
                        data_str = result.data

                    logger.info(f"Data string: {data_str}")

                    # This is where we'd pass to check_format in src20.py
                    return data_str, result.source, result.destination, result.keyburn
                except Exception as e:
                    logger.error(f"Error decoding data: {e}")
            else:
                logger.warning("No data found in transaction")
        else:
            logger.warning("Process_tx returned None")
    except Exception as e:
        logger.error(f"Error in process_tx: {e}")

    return None, None, None, None


def test_src20_format_check(data_str, tx_hash, block_index):
    """Test if the data passes src20.check_format."""
    logger.info("\n--- Testing src20.check_format ---")

    if not data_str:
        logger.warning("No data string to check")
        return None

    try:
        result = check_format(data_str, tx_hash, block_index)
        if result:
            logger.info("check_format PASSED ✅")
            logger.info(f"Result: {result}")
            return result
        else:
            logger.error("check_format FAILED ❌")

            # Try to determine why it failed
            try:
                json_data = json.loads(data_str)
                logger.info(f"JSON parse successful: {json_data}")

                # Check common reasons for rejection
                if "p" not in json_data:
                    logger.error("Missing 'p' field")
                elif json_data.get("p").lower() != "src-20":
                    logger.error(f"Invalid 'p' value: {json_data.get('p')}")

                if "tick" not in json_data:
                    logger.error("Missing 'tick' field")
                elif len(json_data.get("tick", "")) > 5:
                    logger.error(f"Tick too long: {json_data.get('tick')}")

                if "op" not in json_data:
                    logger.error("Missing 'op' field")

                # Check required fields based on operation
                op = json_data.get("op", "").upper()
                if op == "DEPLOY":
                    if "max" not in json_data:
                        logger.error("Missing 'max' field for DEPLOY")
                    if "lim" not in json_data:
                        logger.error("Missing 'lim' field for DEPLOY")
                elif op in ["MINT", "TRANSFER"]:
                    if "amt" not in json_data:
                        logger.error(f"Missing 'amt' field for {op}")
            except json.JSONDecodeError:
                logger.error(f"Data is not valid JSON: {data_str}")
            except Exception as e:
                logger.error(f"Error analyzing format failure: {e}")
    except Exception as e:
        logger.error(f"Error in check_format: {e}")

    return None


def test_src20_validator(src20_dict):
    """Test the Src20Validator logic."""
    logger.info("\n--- Testing Src20Validator ---")

    if not src20_dict:
        logger.warning("No src20_dict to validate")
        return None

    try:
        validator = Src20Validator(src20_dict)
        result = validator.process_values()

        logger.info(f"Validation errors: {validator.errors}")
        logger.info(f"Is valid: {validator.is_valid}")
        logger.info(f"Processed values: {result}")

        return result if validator.is_valid else None
    except Exception as e:
        logger.error(f"Error in Src20Validator: {e}")

    return None


def simulate_src20_processor(src20_dict):
    """Simulate the Src20Processor without database connections."""
    logger.info("\n--- Simulating Src20Processor ---")

    if not src20_dict:
        logger.warning("No src20_dict to process")
        return False

    # We'll just check the field correctness that would cause processing to fail
    try:
        # Check the basic operation requirements
        op = src20_dict.get("op", "").upper()
        logger.info(f"Operation: {op}")

        # For each operation type, check the required fields
        if op == "DEPLOY":
            if not src20_dict.get("lim") or not src20_dict.get("max"):
                logger.error("Missing required fields for DEPLOY operation")
                return False
        elif op in ["MINT", "TRANSFER"]:
            if not src20_dict.get("amt"):
                logger.error(f"Missing 'amt' field for {op} operation")
                return False
        else:
            logger.error(f"Unsupported operation: {op}")
            return False

        # If we've made it here, the processor would likely be valid
        logger.info("Src20Processor validation PASSED ✅")
        return True
    except Exception as e:
        logger.error(f"Error in Src20Processor: {e}")

    return False


def analyze_transaction(tx_hash, block_index):
    """Analyze a specific transaction, tracing it through the src20.py pipeline."""
    backend = Backend()
    tx_hex = backend.getrawtransaction(tx_hash)

    if not tx_hex:
        logger.error(f"Could not get transaction {tx_hash}")
        return

    # Extract SRC-20 data
    data_str, source, destination, keyburn = extract_data_from_transaction(tx_hash, tx_hex, block_index)

    # Check if it passes the SRC-20 format check
    src20_dict = test_src20_format_check(data_str, tx_hash, block_index)

    # If it passes format check, validate it
    if src20_dict:
        # Add required fields for processing
        src20_dict["tx_hash"] = tx_hash
        src20_dict["block_index"] = block_index
        src20_dict["creator"] = source
        src20_dict["destination"] = destination or source
        src20_dict["keyburn"] = keyburn

        # Validate
        validated_dict = test_src20_validator(src20_dict)

        # Simulate processor
        if validated_dict:
            is_valid = simulate_src20_processor(validated_dict)
            if is_valid:
                logger.info("Transaction would likely be processed successfully in src20.py ✅")
            else:
                logger.error("Transaction would fail in the processor stage ❌")
        else:
            logger.error("Transaction failed validation stage ❌")
    else:
        logger.error("Transaction failed format check stage ❌")


def main():
    """Main function to analyze transactions."""
    block_index = 865003
    logger.info(f"Analyzing transactions from block {block_index}")

    for tx_hash in EXPECTED_TX_HASHES:
        analyze_transaction(tx_hash, block_index)


if __name__ == "__main__":
    main()
