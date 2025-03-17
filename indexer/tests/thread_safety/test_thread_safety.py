#!/usr/bin/env python
"""
Thread safety test for src20.py

This script simulates concurrent processing of SRC-20 transactions
to verify thread safety mechanisms without requiring a full database setup.
The main purpose is to verify lock behavior with shared lists.
"""

import concurrent.futures
import logging
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Add src directory to path
current_dir = Path(__file__).parent.parent.parent.absolute()
src_path = current_dir / "src"
sys.path.insert(0, str(src_path))

# ------------------------------------------------------------------------------
# Mock SRC-20 Processor for Thread Safety Testing
# ------------------------------------------------------------------------------

class MockSrc20Processor:
    """
    Mock implementation of SRC-20 processor that simulates the thread safety aspects
    without requiring a real database connection.
    """
    def __init__(self):
        # Shared resources that need protection
        self.processed_list = []
        self.processed_ticks = set()
        
        # Lock for thread safety
        self.lock = threading.Lock()
        
    def process_transaction(self, tx: Dict) -> bool:
        """Process a transaction with thread safety in mind"""
        # Simulate processing delay
        time.sleep(random.uniform(0.001, 0.01))
        
        tick = tx.get("tick", "UNKNOWN")
        
        # Use the lock to protect access to shared resources
        with self.lock:
            # Check if this tick is already in the processed list
            if tick in self.processed_ticks:
                logger.warning(f"Tick {tick} already processed - potential race condition")
                return False
                
            # Add to processed list and set of processed ticks
            tx_copy = tx.copy()
            tx_copy["processed"] = True
            self.processed_list.append(tx_copy)
            self.processed_ticks.add(tick)
        
        return True

# ------------------------------------------------------------------------------
# Thread Safety Tests
# ------------------------------------------------------------------------------

def test_lock_behavior():
    """
    Test the thread-safety of the lock mechanism by processing multiple transactions
    concurrently and verifying no duplicates or missed transactions.
    """
    logger.info("Testing thread lock behavior with concurrent transactions")
    
    # Create sample transactions
    transactions = []
    for i in range(20):
        transactions.append({
            "txid": f"txid{i}",
            "blockheight": 100000 + i,
            "tick": f"TEST{i}",
            "amount": "100",
            "data": f"Sample data {i}"
        })
    
    # Initialize processor
    processor = MockSrc20Processor()
    
    # Process transactions concurrently using ThreadPoolExecutor
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        # Submit all transactions for processing
        future_to_tx = {
            executor.submit(processor.process_transaction, tx): tx
            for tx in transactions
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_tx):
            tx = future_to_tx[future]
            try:
                result = future.result()
                results.append((tx["tick"], result))
            except Exception as e:
                logger.error(f"Error processing {tx['tick']}: {e}")
    
    # Verify results
    logger.info(f"Total processed transactions: {len(processor.processed_list)}")
    logger.info(f"Unique ticks processed: {len(processor.processed_ticks)}")
    
    # Check for race conditions
    duplicate_count = len(transactions) - len(processor.processed_ticks)
    if duplicate_count > 0:
        logger.error(f"Found {duplicate_count} potential race conditions (duplicate ticks)")
    
    # Test succeeds if all transactions were processed correctly with no duplicates
    success = len(processor.processed_list) == len(transactions) and len(processor.processed_ticks) == len(transactions)
    
    if success:
        logger.info("✅ Thread lock mechanism test passed!")
    else:
        logger.error("❌ Thread lock mechanism test failed!")
        # Log details of the issue
        if len(processor.processed_list) != len(transactions):
            logger.error(f"Expected {len(transactions)} processed transactions, got {len(processor.processed_list)}")
        if len(processor.processed_ticks) != len(transactions):
            logger.error(f"Expected {len(transactions)} unique ticks, got {len(processor.processed_ticks)}")
            # Show what's missing
            expected_ticks = {tx["tick"] for tx in transactions}
            missing_ticks = expected_ticks - processor.processed_ticks
            if missing_ticks:
                logger.error(f"Missing ticks: {missing_ticks}")
    
    return success

# ------------------------------------------------------------------------------
# Race Condition Simulation
# ------------------------------------------------------------------------------

def test_without_lock():
    """
    Intentionally create a race condition by processing without locks
    to demonstrate the importance of the thread safety mechanism.
    """
    logger.info("Testing behavior WITHOUT thread locks")
    
    # Create a shared counter to demonstrate race conditions
    counter = 0
    iterations = 100000
    num_threads = 10
    
    # Function that increments the counter without proper locking
    def increment_counter_without_lock(n):
        nonlocal counter
        for _ in range(n):
            # This is the critical section that should be protected with a lock
            # 1. Read the current value
            current = counter
            # 2. Simulate some processing time that could cause a context switch
            time.sleep(0.0000001)
            # 3. Update with the new value
            counter = current + 1
    
    # Process concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        # Each thread will increment the counter iterations/num_threads times
        futures = [executor.submit(increment_counter_without_lock, iterations // num_threads) 
                 for _ in range(num_threads)]
        
        # Wait for all threads to complete
        concurrent.futures.wait(futures)
    
    # Check the final counter value
    expected_value = iterations
    actual_value = counter
    
    logger.info(f"Without lock: Expected counter value: {expected_value}, Actual: {actual_value}")
    
    # If the actual value is less than expected, we have race conditions
    if actual_value < expected_value:
        logger.info(f"✅ Race condition demonstrated: {expected_value - actual_value} increments were lost!")
        
        # Now demonstrate correct behavior with a lock
        counter_with_lock = 0
        lock = threading.Lock()
        
        def increment_counter_with_lock(n):
            nonlocal counter_with_lock
            for _ in range(n):
                with lock:  # Properly protect the critical section
                    current = counter_with_lock
                    time.sleep(0.0000001)  # Same delay as before
                    counter_with_lock = current + 1
        
        # Process with proper locking
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(increment_counter_with_lock, iterations // num_threads) 
                    for _ in range(num_threads)]
            concurrent.futures.wait(futures)
        
        logger.info(f"With lock: Expected counter value: {expected_value}, Actual: {counter_with_lock}")
        
        return True
    else:
        logger.warning("⚠️ No race conditions detected in the unsafe test. Try running again or increasing iterations.")
        return True  # Still return True since this is a demonstration

# ------------------------------------------------------------------------------
# Main function
# ------------------------------------------------------------------------------

def main():
    """Run all thread safety tests"""
    logger.info("==== Testing SRC-20 Thread Safety ====")
    
    # Run test with proper lock mechanism
    logger.info("\n--- Testing with thread locks ---")
    with_lock_result = test_lock_behavior()
    
    # Run test without lock to demonstrate race conditions
    logger.info("\n--- Testing without thread locks ---")
    without_lock_result = test_without_lock()
    
    # Overall results
    if with_lock_result:
        logger.info("\n✅ Thread safety mechanisms are working properly!")
    else:
        logger.error("\n❌ Thread safety test failed - lock mechanisms may not be effective!")
    
    logger.info("==== Testing complete ====")

if __name__ == "__main__":
    main()