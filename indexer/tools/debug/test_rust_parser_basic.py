#!/usr/bin/env python3
import logging
import os
import sys

from dotenv import load_dotenv

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import config

# Import after path setup
from index_core.backend import Backend

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger("test_rust_parser")

def main():
    # Set log level
    logger.setLevel(logging.DEBUG)
    logging.getLogger("index_core").setLevel(logging.DEBUG)
    
    # Load environment variables
    load_dotenv()
    
    # Initialize backend
    backend_instance = Backend()  # Use the singleton instance
    
    # Check if Rust parser is available
    if backend_instance._parser is None:
        logger.error("Rust parser is not available")
        return
    
    # Test transaction
    tx_id = "00d91249c4e66b49334388487c7dfc3c5403f837159badce7088cf6afe57d9cb"
    logger.info(f"Testing Rust parser with transaction {tx_id}")
    
    try:
        # Get transaction hex
        tx_hex = backend_instance.getrawtransaction(tx_id)
        logger.info(f"Transaction hex length: {len(tx_hex)}")
        
        # Parse with Rust parser directly
        logger.info("Parsing transaction with Rust parser directly")
        tx_info = backend_instance._parser.deserialize_transaction(tx_hex)
        
        # Log basic transaction info
        logger.info(f"Transaction parsed successfully: {tx_id}")
        logger.info(f"Transaction type: {type(tx_info)}")
        
        # Test batch processing
        logger.info("Testing batch processing with the same transaction")
        results = backend_instance._parser.batch_parse_transactions([tx_hex])
        
        if results:
            logger.info(f"Batch processing returned {len(results)} results")
            for i, result in enumerate(results):
                logger.info(f"Result {i} type: {type(result)}")
                # Check if the transaction should be included
                if hasattr(result, 'should_include'):
                    logger.info(f"Result {i}: should_include={result.should_include}")
                else:
                    logger.info(f"Result {i}: No 'should_include' attribute")
                
                # Check if the transaction has valid data
                if hasattr(result, 'has_valid_data'):
                    logger.info(f"Result {i}: has_valid_data={result.has_valid_data}")
                else:
                    logger.info(f"Result {i}: No 'has_valid_data' attribute")
                
                # Check if the transaction has valid pattern
                if hasattr(result, 'has_valid_pattern'):
                    logger.info(f"Result {i}: has_valid_pattern={result.has_valid_pattern}")
                else:
                    logger.info(f"Result {i}: No 'has_valid_pattern' attribute")
                
                # Check if the transaction has keyburn
                if hasattr(result, 'keyburn'):
                    logger.info(f"Result {i}: keyburn={result.keyburn}")
                else:
                    logger.info(f"Result {i}: No 'keyburn' attribute")
        else:
            logger.info("Batch processing returned no results")
            
    except Exception as e:
        logger.error(f"Error testing Rust parser: {e}", exc_info=True)

if __name__ == "__main__":
    main() 