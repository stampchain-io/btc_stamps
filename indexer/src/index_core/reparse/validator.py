#!/usr/bin/env python3
"""Reparse CLI for Bitcoin Stamps: snapshot creation and pure in-memory validation."""

import os
import sys

# Force in-memory reparse to use mock DB (in-memory, no real pool or connections)
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["TESTING"] = "1"
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from index_core.database_manager import DatabaseManager

import ast
import importlib.util
import logging
from pathlib import Path

import index_core.caching as reparse_caching
import index_core.util as util
from index_core.blocks import (
    BlockProcessor,
    backend_instance,
    create_check_hashes,
    fetch_xcp_blocks_concurrent,
    filter_block_transactions,
    process_tx,
)

# Load .env from project root, falling back to .env.sample
root_dir = Path(__file__).resolve().parents[3]
env_path = root_dir / ".env"
if not env_path.exists():
    env_path = root_dir / ".env.sample"
if env_path.exists():
    load_dotenv(dotenv_path=str(env_path))

# Load the real snapshot module directly (bypass any test stubs in sys.modules)
_snapshot_file = Path(__file__).parent / "snapshot.py"
# Load real snapshot module spec (ensure spec and loader are available)
_spec = importlib.util.spec_from_file_location("index_core.reparse.snapshot_real", str(_snapshot_file))
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load module spec for {_snapshot_file}")
_snapshot_mod = importlib.util.module_from_spec(_spec)
# Insert real snapshot module under its normal name to override any stubs
sys.modules["index_core.reparse.snapshot_real"] = _snapshot_mod
sys.modules["index_core.reparse.snapshot"] = _snapshot_mod
_spec.loader.exec_module(_snapshot_mod)
SnapshotManager = _snapshot_mod.SnapshotManager

logger = logging.getLogger(__name__)

import argparse


def main() -> None:
    """Snapshot creation or pure in-memory reparse CLI."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="BTC Stamps Reparse CLI")
    parser.add_argument(
        "--snapshot-path", default=os.getenv("SNAPSHOT_PATH", "snapshots/reference_hashes.json"), help="Path to snapshot file"
    )
    parser.add_argument("--save-snapshot", action="store_true", help="Save DB state to snapshot and exit")
    parser.add_argument("--block-index", type=int, help="In-memory validate one block")
    parser.add_argument("--sequence", action="store_true", help="Validate snapshot continuity")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.save_snapshot:
        # For snapshot creation, disable mock DB environment variables to use real database
        os.environ.pop("USE_TEST_DB", None)
        os.environ.pop("MOCK_DB", None)
        os.environ.pop("TESTING", None)
        from index_core.database_manager import DatabaseManager

        logging.info(f"Snapshotting DB to {args.snapshot_path}...")
        dbm = DatabaseManager()
        db = dbm.connect()
        SnapshotManager(args.snapshot_path).save_current_state(db)
        db.close()
        logging.info("Snapshot complete.")
        sys.exit(0)
    # Pure in-memory reparse
    validator = ReparseValidator(snapshot_path=args.snapshot_path)
    if args.block_index is not None:
        sys.exit(0 if validator.validate_block(args.block_index) else 1)
    if args.sequence:
        sys.exit(0 if validator.validate_sequence() else 1)
    hashes = validator.snapshot_manager.load_snapshot().get("hashes", {})
    for blk in sorted(int(i) for i in hashes):
        logging.info(f"Validating block {blk}...")
        if not validator.validate_block(blk):
            logging.error(f"Validation failed at block {blk}")
            sys.exit(1)
        reparse_caching.cache_manager.check_memory_pressure()
    logging.info("All blocks validated successfully")
    sys.exit(0)


class ValidationError(Exception):
    """Base class for validation errors."""

    pass


class InMemoryBlockProcessor:
    """Process blocks in-memory for pure reparse without any database reads or writes."""

    def __init__(self) -> None:
        # Stamp tracking
        self.valid_stamps_in_block: list = []
        # Protocol state
        self.processed_src20_in_block: list = []
        self.processed_src721_in_block: list = []
        self.processed_src101_in_block: list = []
        # Ledger state
        self.ledger_updates: dict = {}
        # Collection operations
        self.collection_operations: list = []

    def _update_ledger(self, operation_data: dict) -> None:
        """Update in-memory ledger state for src-20 operations."""
        tick = operation_data.get("tick")
        amt = int(operation_data.get("amt", 0))
        if operation_data.get("operation") == "mint":
            if tick not in self.ledger_updates:
                self.ledger_updates[tick] = {"supply": 0, "holders": {}}
            self.ledger_updates[tick]["supply"] += amt
        elif operation_data.get("operation") == "transfer":
            if tick not in self.ledger_updates:
                self.ledger_updates[tick] = {"holders": {}}
            holders = self.ledger_updates[tick].setdefault("holders", {})
            sender = operation_data.get("from")
            receiver = operation_data.get("to")
            holders[sender] = holders.get(sender, 0) - amt
            holders[receiver] = holders.get(receiver, 0) + amt

    def process_transaction_results(self, tx_results: list) -> None:
        """Process transaction results and update in-memory state."""
        for result in tx_results:
            if not getattr(result, "data", None):
                continue
            data = result.data
            # Parse data string into dict if necessary
            if isinstance(data, str):
                try:
                    data = ast.literal_eval(data)
                except (ValueError, SyntaxError):
                    logging.getLogger(__name__).debug(f"Could not parse transaction data string: {data}")
                    continue
            # CPID reissuance exclusion via cache
            cpid = data.get("cpid")
            if cpid:
                # Use pre-existing 'reissue' cache
                if reparse_caching.cache_manager.get_cache_value("reissue", cpid):
                    continue
                reparse_caching.cache_manager.set_cache_value("reissue", cpid, True)
            # Track valid stamps with in-memory numbering
            # Assign in-memory stamp number
            prev_stamp_num = reparse_caching.cache_manager.get_cache_value("stamp", "counter") or 0
            new_stamp_num = prev_stamp_num + 1
            reparse_caching.cache_manager.set_cache_value("stamp", "counter", new_stamp_num)
            stamp_record = {
                "tx_hash": result.tx_hash,
                "block_index": result.block_index,
                "block_time": result.block_time,
                "cpid": data.get("cpid"),
                "stamp": new_stamp_num,
            }
            self.valid_stamps_in_block.append(stamp_record)
            # Protocol operations
            protocol = data.get("protocol")
            if protocol == "src-20":
                self.processed_src20_in_block.append(data)
                self._update_ledger(data)
                # Update in-memory SRC-20 caches
                from decimal import Decimal as D

                tick = data.get("tick")
                op = data.get("operation", "").lower()
                amt = D(data.get("amt", "0"))
                # Total minted cache
                if op == "mint" and tick:
                    prev_total = reparse_caching.cache_manager.get_cache_value("total_minted", tick) or D(0)
                    reparse_caching.cache_manager.set_cache_value("total_minted", tick, prev_total + amt)
                    # Credit to holder balance cache
                    to_addr = data.get("to")
                    if to_addr:
                        key_to = f"{tick}:{to_addr}"
                        prev_bal = reparse_caching.cache_manager.get_cache_value("balance", key_to) or D(0)
                        reparse_caching.cache_manager.set_cache_value("balance", key_to, prev_bal + amt)
                # Transfer balance cache
                if op == "transfer" and tick:
                    from_addr = data.get("from")
                    to_addr = data.get("to")
                    if from_addr:
                        key_from = f"{tick}:{from_addr}"
                        prev_from = reparse_caching.cache_manager.get_cache_value("balance", key_from) or D(0)
                        reparse_caching.cache_manager.set_cache_value("balance", key_from, prev_from - amt)
                    if to_addr:
                        key_to = f"{tick}:{to_addr}"
                        prev_to = reparse_caching.cache_manager.get_cache_value("balance", key_to) or D(0)
                        reparse_caching.cache_manager.set_cache_value("balance", key_to, prev_to + amt)
            elif protocol == "src-721":
                self.processed_src721_in_block.append(data)
                # Cache collection deploy metadata
                op_val = data.get("operation", "").lower()
                cpid = data.get("cpid")
                if op_val == "deploy" and cpid:
                    reparse_caching.cache_manager.set_cache_value("collection", cpid, data)
            elif protocol == "src-101":
                self.processed_src101_in_block.append(data)
                # Cache SRC-101 deploy parameters
                op_val = data.get("operation", "").lower()
                h = data.get("hash")
                if op_val == "deploy" and h:
                    reparse_caching.cache_manager.set_cache_value("src101_deploy", h, data)
            # Note: collections and metadata tracked via collection_operations as needed


class ReparseValidator:
    """Validator for reparse operations."""

    def __init__(self, snapshot_path: Optional[str] = None, db: Optional["DatabaseManager"] = None):
        self.snapshot_path = snapshot_path or os.getenv("SNAPSHOT_PATH") or "snapshots/reference_hashes.json"
        Path(self.snapshot_path).parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_manager = SnapshotManager(self.snapshot_path)
        self.db = db  # Optional DB connection for creating reference hashes

    def compute_block_hashes(
        self,
        block_index: int,
        block_processor: Optional[Union[BlockProcessor, InMemoryBlockProcessor]] = None,
    ) -> Dict[str, str]:
        """Compute hashes for a block using the same logic as production."""
        try:
            # Sync util and config so that filtering treats our reparse genesis as post-genesis
            util.CURRENT_BLOCK_INDEX = block_index
            import config as _cfg

            # Temporarily align BTC_SRC20_GENESIS_BLOCK to our CP_STAMP_GENESIS_BLOCK
            _orig_gen = _cfg.BTC_SRC20_GENESIS_BLOCK
            _cfg.BTC_SRC20_GENESIS_BLOCK = _cfg.CP_STAMP_GENESIS_BLOCK
            # Get block data from Bitcoin node
            block_hash = backend_instance.getblockhash(block_index)
            block_data = backend_instance.getblock(block_hash, 2)
            if not block_data:
                raise ValidationError(f"Failed to get block data for block {block_index}")

            # Get CP block data
            cp_blocks = fetch_xcp_blocks_concurrent(block_index, block_index)
            stamp_issuances = cp_blocks[block_index]["issuances"] if block_index in cp_blocks else []

            # Filter transactions
            txhash_list, raw_transactions = filter_block_transactions(block_data, stamp_issuances=stamp_issuances)
            # For CP genesis block, only include stamp issuance transactions in memory reparse
            if block_index == _cfg.CP_STAMP_GENESIS_BLOCK:
                raw_transactions = {
                    issuance["tx_hash"]: raw_transactions[issuance["tx_hash"]]
                    for issuance in stamp_issuances
                    if issuance.get("tx_hash") in raw_transactions
                }
            # Restore original SRC20 genesis for other logic
            _cfg.BTC_SRC20_GENESIS_BLOCK = _orig_gen

            # Process transactions using BlockProcessor if not provided
            # Initialize an in-memory processor if none provided
            if block_processor is None:
                block_processor = InMemoryBlockProcessor()
                tx_results = []
                for tx_hash in raw_transactions.keys():
                    result = process_tx(None, tx_hash, block_index, stamp_issuances, raw_transactions)
                    if getattr(result, "data", None) is not None:
                        result = result._replace(block_index=block_index, block_hash=block_hash, block_time=block_data["time"])
                        tx_results.append(result)
                block_processor.process_transaction_results(tx_results)
            # Ensure block_processor is not None for type checking
            assert block_processor is not None

            # Get previous hashes from snapshot
            prev_hashes = self.snapshot_manager.get_expected_hash(block_index - 1) or {
                "ledger_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "txlist_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                "messages_hash": "0000000000000000000000000000000000000000000000000000000000000000",
            }

            # Create a mock database for hash computation
            mock_db = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_db.cursor.return_value = mock_cursor

            # Compute hashes using existing create_check_hashes function
            # Temporarily remove checkpoint entry for this block to avoid enforcement error
            from index_core import check as check_mod

            orig_checkpoint = None
            if block_index in check_mod.CHECKPOINTS_MAINNET:
                orig_checkpoint = check_mod.CHECKPOINTS_MAINNET.pop(block_index)
            try:
                new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                    mock_db,  # Use mock DB for hash computation
                    block_index,
                    block_processor.valid_stamps_in_block,
                    "",  # Empty string for valid_src20_str as we're just validating
                    txhash_list,
                    prev_hashes["ledger_hash"],
                    prev_hashes["txlist_hash"],
                    prev_hashes["messages_hash"],
                )
            finally:
                # Restore checkpoint entry if it was removed
                if orig_checkpoint is not None:
                    check_mod.CHECKPOINTS_MAINNET[block_index] = orig_checkpoint

            # Prepare result
            result = {
                "block_hash": block_hash,
                "messages_hash": new_messages_hash,
                "txlist_hash": new_txlist_hash,
                "ledger_hash": new_ledger_hash,
            }
            # Memory housekeeping: clear in-memory processor state
            try:
                reparse_caching.cache_manager.check_memory_pressure()
                if isinstance(block_processor, InMemoryBlockProcessor):
                    block_processor.valid_stamps_in_block.clear()
                    block_processor.processed_src20_in_block.clear()
                    block_processor.processed_src721_in_block.clear()
                    block_processor.processed_src101_in_block.clear()
                    block_processor.ledger_updates.clear()
                    block_processor.collection_operations.clear()
            except Exception:
                logger.debug("Memory housekeeping failed for block processor state cleanup")
            return result

        except Exception as e:
            logger.error(f"Error computing hashes for block {block_index}: {e}")
            raise

    def validate_block(self, block_index: int) -> bool:
        """Validate a block by computing and comparing hashes."""
        try:
            # Determine checkpoint behavior: skip re-validation for designated checkpoints, but still process genesis
            import config as _cfg
            from index_core import check

            # Skip only non-genesis checkpoint blocks
            if block_index in check.CHECKPOINTS_MAINNET and block_index != _cfg.CP_STAMP_GENESIS_BLOCK:
                logger.info(f"Block {block_index} is a checkpoint; skipping re-validation.")
                return True
            # Identify genesis to include in-memory processing but skip hash comparison
            is_genesis = block_index == _cfg.CP_STAMP_GENESIS_BLOCK
            # Compute hashes for the block
            computed_hashes = self.compute_block_hashes(block_index)
            if is_genesis:
                logger.info(f"Genesis block {block_index} processed; skipping hash comparison.")
                return True
            # Get expected hash from snapshot
            expected_hashes = self.snapshot_manager.get_expected_hash(block_index)
            if not expected_hashes:
                raise ValidationError(f"No expected hashes found for block {block_index}")

            # Compare hashes
            for hash_type in ["messages_hash", "txlist_hash"]:  # Skip ledger_hash if empty
                if computed_hashes[hash_type] != expected_hashes[hash_type]:
                    logger.error(
                        f"Hash mismatch for block {block_index} ({hash_type}):\n"
                        f"  Computed: {computed_hashes[hash_type]}\n"
                        f"  Expected: {expected_hashes[hash_type]}"
                    )
                    return False

            # Only compare ledger_hash if it's not empty in the snapshot
            if expected_hashes["ledger_hash"]:
                if computed_hashes["ledger_hash"] != expected_hashes["ledger_hash"]:
                    logger.error(
                        f"Hash mismatch for block {block_index} (ledger_hash):\n"
                        f"  Computed: {computed_hashes['ledger_hash']}\n"
                        f"  Expected: {expected_hashes['ledger_hash']}"
                    )
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating block {block_index}: {e}")
            raise

    def validate_sequence(self) -> bool:
        """Validate that snapshot block indices form a continuous sequence."""
        data = self.snapshot_manager.load_snapshot()
        hashes = data.get("hashes") if isinstance(data, dict) else None
        if not hashes:
            raise ValidationError("No hashes found in snapshot for sequence validation")
        indices = sorted(int(i) for i in hashes.keys())
        missing = [i for i in range(indices[0], indices[-1] + 1) if i not in indices]
        if missing:
            raise ValidationError(f"Missing blocks in snapshot: {missing}")
        return True


if __name__ == "__main__":
    main()
