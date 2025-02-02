import logging
import os
import sys
import time
import warnings
from pathlib import Path

import psutil

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Suppress insecure request warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

from index_core.backend import Backend
from index_core.blocks import filter_block_transactions
import config

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configure test settings
config.BACKEND_SSL_NO_VERIFY = True

# Set up QuickNode configuration
quicknode_url = os.getenv("QUICKNODE_URL", "").strip("'\"").rstrip("/")
quicknode_key = os.getenv("QUICKNODE_API_KEY", "").strip("'\"")

if quicknode_url and quicknode_key:
    config.QUICKNODE_ENDPOINT = quicknode_url
    config.QUICKNODE_API_KEY = quicknode_key
    logger.info(f"Using QuickNode endpoint: {quicknode_url}")
else:
    logger.warning("QuickNode credentials not found, some tests will be skipped")


def test_prefilter_performance():
    # Skip test if QuickNode credentials are not available
    if not quicknode_url or not quicknode_key:
        logger.warning("Skipping performance test - QuickNode credentials not available")
        return

    # Initialize backend and set required globals
    try:
        backend = Backend()
        import index_core.util as util
        util.CURRENT_BLOCK_INDEX = 0
    except Exception as e:
        if "database" in str(e).lower():
            logger.warning("Database connection failed, continuing without DB")
            backend = Backend()
            util.CURRENT_BLOCK_INDEX = 0
        else:
            logger.warning(f"Backend initialization failed: {e}")
            return

    # Test with 20 blocks
    start_time = time.time()
    total_filtered = 0
    total_txs = 0
    block_times = []
    memory_usage = []

    try:
        # Get 20 recent blocks
        current = backend.rpc("getblockcount", [])
        logger.info(f"Starting from block {current}")

        for i in range(20):
            block_start = time.time()
            try:
                try:
                    block_hash = backend.rpc("getblockhash", [current - i])
                    if not block_hash:
                        logger.error(f"Failed to get block hash for height {current - i}")
                        continue

                    logger.debug(f"Got block hash: {block_hash}")
                    block = backend.rpc("getblock", [block_hash, 2])
                    if not block or "tx" not in block:
                        logger.error(f"Invalid block data for hash {block_hash}")
                        continue

                    # Track memory before filtering
                    mem_before = psutil.Process().memory_percent()

                    # Filter transactions
                    _, filtered_txs = filter_block_transactions(block, block_hash)
                    if not filtered_txs:
                        filtered_txs = {}

                    # Calculate block metrics
                    block_time = time.time() - block_start
                    block_times.append(block_time)
                    total_filtered += len(filtered_txs)
                    total_txs += len(block["tx"])

                    # Track memory after filtering
                    mem_after = psutil.Process().memory_percent()
                    memory_usage.append(mem_after - mem_before)

                    # Log detailed progress
                    filter_rate = (
                        ((len(block["tx"]) - len(filtered_txs)) / len(block["tx"])) * 100 if len(block["tx"]) > 0 else 0
                    )
                    logger.info(
                        f"Block {current - i}: "
                        f"Time={block_time:.3f}s, "
                        f'Txs={len(filtered_txs)}/{len(block["tx"])}, '
                        f"Filter={filter_rate:.1f}%, "
                        f"Mem={mem_after:.1f}%"
                    )
                except Exception as e:
                    logger.error(f"Error processing block {current - i}: {str(e)}")
                    continue

            except Exception as e:
                logger.error(f"Error processing block {current - i}: {str(e)}")
                continue

        # Calculate final metrics
        total_time = time.time() - start_time
        avg_time = sum(block_times) / len(block_times)
        max_time = max(block_times)
        total_filter_rate = ((total_txs - total_filtered) / total_txs) * 100
        max_memory = max(memory_usage)

        print("\nPerformance Results:")
        print(f"Total time: {total_time:.2f}s")
        print(f"Average time per block: {avg_time:.3f}s")
        print(f"Max block time: {max_time:.3f}s")
        print(f"Filter rate: {total_filter_rate:.1f}%")
        print(f"Max memory increase: {max_memory:.1f}%")

    except Exception as e:
        logger.error(f"Error during performance test: {str(e)}")


if __name__ == "__main__":
    test_prefilter_performance()
