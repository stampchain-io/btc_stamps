import datetime
import logging
import os
import statistics
import sys
import time
from typing import Any, Dict, List, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("lru_cache_benchmark")

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

try:
    from btc_stamps_parser import FastTransactionParser

    logger.info("Successfully imported FastTransactionParser")
except ImportError as e:
    logger.error(f"Failed to import FastTransactionParser: {e}")
    sys.exit(1)

# A valid Bitcoin transaction hex
VALID_TX_HEX = "0100000001c997a5e56e104102fa209c6a852dd90660a20b2d9c352423edce25857fcd3704000000004847304402204e45e16932b8af514961a1d3a1a25fdf3f4f7732e9d624c6c61548ab5fb8cd410220181522ec8eca07de4860a4acdd12909d831cc56cbbac4622082221a8768d1d0901ffffffff0200ca9a3b00000000434104ae1a62fe09c5f51b13905f07f06b99a2f7159b2225f374cd378d71302fa28414e7aab37397f554a7df5f142c21c1b7303b8a0626f1baded5c72a704f7e6cd84cac00286bee0000000043410411db93e1dcdb8a016b49840f8c53bc1eb68a382e97b1482ecad7b148a6909a5cb2e0eaddfb84ccf9744464f82e160bfa9b8b64f9d4c03f999b8643f656b412a3ac00000000"


def generate_modified_tx_hex(base_tx_hex: str, modification_factor: float = 0.05) -> str:
    """Generate a slightly modified transaction hex based on the valid transaction."""
    chars = list(base_tx_hex)
    num_chars_to_modify = max(1, int(len(chars) * modification_factor))

    # Modify random characters while keeping it a valid hex string
    for _ in range(num_chars_to_modify):
        idx = int(time.time() * 1000000) % len(chars)
        chars[idx] = "0123456789abcdef"[int(time.time() * 10000000) % 16]

    return "".join(chars)


def benchmark_with_cache(num_transactions: int, num_repeats: int) -> Tuple[float, float, Dict[str, Any]]:
    """Benchmark transaction parsing with cache enabled."""
    parser = FastTransactionParser(use_cache=True)
    logger.info(f"Created FastTransactionParser with cache enabled")

    # Generate transaction hexes
    tx_hexes = [generate_modified_tx_hex(VALID_TX_HEX) for _ in range(num_transactions)]

    # First pass - populate cache
    start_time = time.time()
    for i, tx_hex in enumerate(tx_hexes):
        try:
            parser.parse_transaction(tx_hex)
        except Exception as e:
            logger.error(f"Error parsing transaction {i}: {e}")
    first_pass_time = time.time() - start_time

    # Repeat passes - should hit cache
    repeat_times = []
    for r in range(num_repeats):
        start_time = time.time()
        for i, tx_hex in enumerate(tx_hexes):
            try:
                parser.parse_transaction(tx_hex)
            except Exception as e:
                logger.error(f"Error parsing transaction {i} in repeat {r}: {e}")
        repeat_times.append(time.time() - start_time)

    avg_repeat_time = statistics.mean(repeat_times)
    cache_stats = parser.get_cache_stats()

    return first_pass_time, avg_repeat_time, cache_stats


def benchmark_without_cache(num_transactions: int, num_repeats: int) -> Tuple[float, float]:
    """Benchmark transaction parsing with cache disabled."""
    parser = FastTransactionParser(use_cache=False)
    logger.info(f"Created FastTransactionParser with cache disabled")

    # Generate transaction hexes
    tx_hexes = [generate_modified_tx_hex(VALID_TX_HEX) for _ in range(num_transactions)]

    # First pass
    start_time = time.time()
    for i, tx_hex in enumerate(tx_hexes):
        try:
            parser.parse_transaction(tx_hex)
        except Exception as e:
            logger.error(f"Error parsing transaction {i}: {e}")
    first_pass_time = time.time() - start_time

    # Repeat passes
    repeat_times = []
    for r in range(num_repeats):
        start_time = time.time()
        for i, tx_hex in enumerate(tx_hexes):
            try:
                parser.parse_transaction(tx_hex)
            except Exception as e:
                logger.error(f"Error parsing transaction {i} in repeat {r}: {e}")
        repeat_times.append(time.time() - start_time)

    avg_repeat_time = statistics.mean(repeat_times)

    return first_pass_time, avg_repeat_time


def run_benchmark():
    """Run the benchmark comparing performance with and without cache."""
    logger.info(f"Starting LRU cache benchmark at {datetime.datetime.now()}")

    # Configuration
    num_transactions = 1000
    num_repeats = 5

    # Benchmark with cache
    logger.info(f"Running benchmark with cache enabled ({num_transactions} transactions, {num_repeats} repeats)")
    with_cache_first_pass, with_cache_repeat, cache_stats = benchmark_with_cache(num_transactions, num_repeats)

    # Benchmark without cache
    logger.info(f"Running benchmark with cache disabled ({num_transactions} transactions, {num_repeats} repeats)")
    without_cache_first_pass, without_cache_repeat = benchmark_without_cache(num_transactions, num_repeats)

    # Calculate improvements
    first_pass_improvement = (without_cache_first_pass - with_cache_first_pass) / without_cache_first_pass * 100
    repeat_improvement = (without_cache_repeat - with_cache_repeat) / without_cache_repeat * 100

    # Report results
    logger.info("Benchmark Results:")
    logger.info(f"First pass (with cache): {with_cache_first_pass:.4f} seconds")
    logger.info(f"First pass (without cache): {without_cache_first_pass:.4f} seconds")
    logger.info(f"First pass improvement: {first_pass_improvement:.2f}%")
    logger.info(f"Repeat passes (with cache): {with_cache_repeat:.4f} seconds")
    logger.info(f"Repeat passes (without cache): {without_cache_repeat:.4f} seconds")
    logger.info(f"Repeat passes improvement: {repeat_improvement:.2f}%")
    logger.info(f"Final cache stats: {cache_stats}")

    # Summary
    logger.info("\nSummary:")
    if repeat_improvement > 50:
        logger.info("The LRU cache provides SIGNIFICANT performance improvement for repeated transactions!")
    elif repeat_improvement > 20:
        logger.info("The LRU cache provides GOOD performance improvement for repeated transactions.")
    elif repeat_improvement > 5:
        logger.info("The LRU cache provides MODEST performance improvement for repeated transactions.")
    else:
        logger.info("The LRU cache provides MINIMAL performance improvement for repeated transactions.")

    return {
        "with_cache_first_pass": with_cache_first_pass,
        "without_cache_first_pass": without_cache_first_pass,
        "with_cache_repeat": with_cache_repeat,
        "without_cache_repeat": without_cache_repeat,
        "first_pass_improvement": first_pass_improvement,
        "repeat_improvement": repeat_improvement,
        "cache_stats": cache_stats,
    }


if __name__ == "__main__":
    run_benchmark()
