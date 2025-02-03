#!/usr/bin/env python3

import logging

from btc_stamps_parser import FastTransactionParser

from index_core.backend import Backend

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def analyze_transaction(txid):
    """Analyze a transaction in detail."""
    backend = Backend()
    parser = FastTransactionParser()

    # Get raw transaction
    tx_hex = backend.getrawtransaction(txid)

    # Parse with Rust parser
    tx_info = parser.deserialize_transaction(tx_hex)

    # Print transaction info
    logger.info(f"Transaction ID: {tx_info.txid}")
    logger.info(f"Should Include: {tx_info.should_include}")
    logger.info(f"Has Valid Pattern: {tx_info.has_valid_pattern}")
    logger.info(f"Has Valid Data: {tx_info.has_valid_data}")
    logger.info(f"Keyburn: {tx_info.keyburn}")
    logger.info(f"Number of inputs: {len(tx_info.inputs)}")
    logger.info(f"Number of outputs: {len(tx_info.outputs)}")

    # Analyze each output from Rust parser
    for i, output in enumerate(tx_info.outputs):
        logger.info(
            f"Output {i}: value={output.value}, script_hex={output.script_hex}, script_len={len(output.script_hex)//2}"
        )
        logger.info(f"  has_op_checkmultisig: {output.has_op_checkmultisig}, keyburn: {output.keyburn}")

    # Analyze with Python parser
    ctx = backend.deserialize(tx_hex)
    logger.info(f"Python parser - Number of outputs: {len(ctx.vout)}")

    # Analyze each output from Python parser
    for i, vout in enumerate(ctx.vout):
        script_bytes = bytes(vout.scriptPubKey)
        logger.info(
            f"Python Output {i}: value={vout.nValue}, script_hex={vout.scriptPubKey.hex()}, script_len={len(script_bytes)}"
        )

        # Check for P2WSH pattern
        if len(script_bytes) == 34 and script_bytes[0] == 0x00 and len(script_bytes[1:]) == 32:
            logger.info(f"  Output {i} has P2WSH pattern")

        # Check for multisig pattern
        if len(script_bytes) > 2 and script_bytes[-1] == 0xAE:
            logger.info(f"  Output {i} has potential multisig pattern")

            # Try to extract ASM
            try:
                from index_core.script import get_asm

                asm = get_asm(vout.scriptPubKey)
                logger.info(f"  ASM: {asm}")

                if asm[-1] == "OP_CHECKMULTISIG":
                    logger.info(f"  Output {i} has OP_CHECKMULTISIG")
            except Exception as e:
                logger.error(f"  Error getting ASM: {e}")


if __name__ == "__main__":
    # Test transaction from the test case
    txid = "e2aa459ebfe0ba3625c917143452678a3e80636489fe0ec8cc7e9651cfd4ddb2"
    analyze_transaction(txid)
