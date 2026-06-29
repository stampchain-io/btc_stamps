"""
Block validation utilities extracted from blocks.py

This module contains functions for validating blocks and their transactions,
including consensus hash calculation and transaction filtering.

Functions:
    create_check_hashes(): Calculate and update consensus hashes for block data
    validate_block_against_production(): Validate block against production database
    filter_block_transactions(): Filter transactions based on genesis status and patterns
"""

import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

import config
import index_core.check as check
import index_core.util as util
from index_core.critical_failure_handler import handle_database_corruption_failure
from index_core.database import update_block_hashes
from index_core.exceptions import BlockUpdateError
from index_core.models import ValidStamp
from index_core.node_health import is_shutdown_requested
from index_core.transaction_utils import backend_instance, quick_filter_src20_transaction

# Module logger
logger = logging.getLogger(__name__)


def create_check_hashes(
    db,
    block_index,
    valid_stamps_in_block: List[ValidStamp],
    processed_src20_in_block,
    txhash_list,
    previous_ledger_hash=None,
    previous_txlist_hash=None,
    previous_messages_hash=None,
):
    """
    Calculate and update the hashes for the given block data. This needs to be modified for a reparse.

    Args:
        db (Database): The database object.
        block_index (int): The index of the block.
        valid_stamps_in_block (list): The list of processed transactions in the block.
        processed_src20_in_block (list): The list of valid SRC20 tokens in the block.
        txhash_list (list): The list of transaction hashes in the block.
        previous_ledger_hash (str, optional): The hash of the previous ledger. Defaults to None.
        previous_txlist_hash (str, optional): The hash of the previous transaction list. Defaults to None.
        previous_messages_hash (str, optional): The hash of the previous messages. Defaults to None.

    Returns:
        tuple: A tuple containing the new ledger hash, transaction list hash, and messages hash.
    """
    # Filter out None values before sorting
    filtered_stamps = [stamp for stamp in valid_stamps_in_block if stamp is not None]
    sorted_valid_stamps = sorted(filtered_stamps, key=lambda x: x.get("stamp_number", 0))
    txlist_content = str(sorted_valid_stamps)
    new_txlist_hash, found_txlist_hash = check.consensus_hash(
        db, block_index, "txlist_hash", previous_txlist_hash, txlist_content
    )

    ledger_content = str(processed_src20_in_block)
    new_ledger_hash, found_ledger_hash = check.consensus_hash(
        db, block_index, "ledger_hash", previous_ledger_hash, ledger_content
    )

    messages_content = str(txhash_list)
    new_messages_hash, found_messages_hash = check.consensus_hash(
        db, block_index, "messages_hash", previous_messages_hash, messages_content
    )

    try:
        update_block_hashes(db, block_index, new_txlist_hash, new_ledger_hash, new_messages_hash)
    except BlockUpdateError as e:
        # Critical database error - terminate with proper cleanup
        handle_database_corruption_failure(
            error_message=f"Failed to update block hashes for block {block_index}", exception=e, block_index=block_index
        )

    return new_ledger_hash, new_txlist_hash, new_messages_hash


def validate_block_against_production(block_index: int) -> bool:
    """Dispatch the every-1000-block inline consensus check per VALIDATION_MODE.

    Consensus-NEUTRAL: validation tooling only; does NOT change indexer
    output/decode/hashes. Kept under the original name so the blocks.py call
    site is unchanged. Halt-on-False semantics are preserved for every mode:
      * "db"        -> compare_tables dev-vs-prod DB diff (DEFAULT; unchanged)
      * "reference" -> lightweight file-based reference_hashes.json check
      * "both"      -> run both paths and require BOTH to pass (logical AND)
    Any unrecognized value falls back to the default "db" path.
    """
    if not config.DEBUG_VALIDATION:
        return True

    mode = getattr(config, "VALIDATION_MODE", "db")
    if mode == "reference":
        return validate_block_against_reference(block_index)
    if mode == "both":
        return _validate_block_against_production_db(block_index) and validate_block_against_reference(block_index)
    return _validate_block_against_production_db(block_index)


def _validate_block_against_production_db(block_index: int) -> bool:
    """Run the compare_tables script to validate against production."""
    block_logger = logging.getLogger("validate_block")
    block_logger.info(f"Validating block {block_index} against production database...")

    try:
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "tools", "compare_tables.py")

        # Check if script exists
        if not os.path.exists(script_path):
            block_logger.warning(f"Validation script not found: {script_path}")
            return True

        # Check shutdown flag before starting validation
        if is_shutdown_requested():
            block_logger.info("Skipping validation due to shutdown signal")
            return True

        process = subprocess.Popen([sys.executable, script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        while True:
            try:
                # Use communicate with timeout to allow for interrupt checking
                stdout, stderr = process.communicate(timeout=1)
                break
            except subprocess.TimeoutExpired:
                # Check shutdown flag periodically
                if is_shutdown_requested():
                    block_logger.info("Terminating validation due to shutdown signal")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return True
                continue

        if process.returncode != 0:
            block_logger.error(f"Validation failed at block {block_index}")
            block_logger.error(f"Comparison output:\n{stdout}\n{stderr}")
            return False

        block_logger.info(f"Block {block_index} validation successful")
        return True

    except Exception as e:
        block_logger.error(f"Error running validation: {str(e)}")
        return True


# ---------------------------------------------------------------------------
# Optional file-based inline validation (consensus-NEUTRAL — validation tooling
# only; does NOT change indexer output/decode/hashes).
#
# A lightweight alternative to the heavy dev-vs-prod compare_tables.py DB diff:
# the every-1000-block check can instead compare the indexer's stored block
# hashes against the ``snapshots/reference_hashes.json`` checkpoint file (the
# same source validate_hashes.py uses), removing the prod-DB dependency so
# validation can run off-host. Selected via ``config.VALIDATION_MODE``
# (default "db" preserves the prior compare_tables behavior).
# ---------------------------------------------------------------------------

# Module-level cache for the parsed reference_hashes.json so it is read at most
# once per process (mirrors the cheapness requirement of the 1000-block check).
_REFERENCE_HASHES_CACHE: Optional[Dict[str, Dict[str, str]]] = None


def _reference_hashes_path() -> str:
    """Resolve snapshots/reference_hashes.json relative to the indexer root.

    block_validation.py lives at ``indexer/src/index_core/`` so three dirname()
    hops reach the indexer root — the same hop count compare_tables resolution
    uses to find ``tools/``.
    """
    indexer_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(indexer_root, "snapshots", "reference_hashes.json")


def _load_reference_hashes() -> Dict[str, Dict[str, str]]:
    """Load and cache the ``hashes`` map from reference_hashes.json (once)."""
    global _REFERENCE_HASHES_CACHE
    if _REFERENCE_HASHES_CACHE is None:
        path = _reference_hashes_path()
        with open(path, "r") as f:
            data = json.load(f)
        _REFERENCE_HASHES_CACHE = data.get("hashes", {})
    return _REFERENCE_HASHES_CACHE


def _read_block_hashes(block_index: int) -> Optional[Dict[str, Optional[str]]]:
    """Read the stored consensus hashes for ``block_index`` from the dev DB.

    Reuses the indexer's configured connection pool (no extra credentials) and
    returns the same columns validate_hashes.py compares, or None if the block
    row is absent.
    """
    # Lazy import to avoid any import-time coupling to the database pool.
    from index_core.database import db_manager

    db = db_manager.connect()
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT block_hash, ledger_hash, txlist_hash, messages_hash FROM blocks WHERE block_index = %s",
            (block_index,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return {
        "block_hash": row[0],
        "ledger_hash": row[1],
        "txlist_hash": row[2],
        "messages_hash": row[3],
    }


def validate_block_against_reference(block_index: int) -> bool:
    """Validate a block's stored hashes against snapshots/reference_hashes.json.

    Mirrors validate_hashes.py field handling (ledger_hash may be ""). Returns:
      * True  on a full match,
      * True  (non-fatal) when the block is absent from the reference file
              (i.e. the tail beyond the snapshot) or absent from the dev DB,
              logging a warning so the tail never false-halts,
      * False on a real hash mismatch.
    """
    block_logger = logging.getLogger("validate_block")
    block_logger.info(f"Validating block {block_index} against reference_hashes.json...")

    try:
        ref_hashes = _load_reference_hashes()
    except Exception as e:
        # Tooling failure must never false-halt a consensus reindex.
        block_logger.warning(f"Could not load reference_hashes.json ({e}); skipping reference validation")
        return True

    expected = ref_hashes.get(str(block_index))
    if expected is None:
        block_logger.warning(
            f"Block {block_index} not present in reference_hashes.json "
            f"(beyond snapshot tail); skipping reference validation"
        )
        return True

    actual = _read_block_hashes(block_index)
    if actual is None:
        block_logger.warning(f"Block {block_index} not found in dev blocks table; skipping reference validation")
        return True

    mismatches: List[Tuple[str, Optional[str], Optional[str]]] = []
    # txlist_hash / messages_hash / block_hash are always present in the file;
    # ledger_hash may be "" (genesis-era blocks) — only compared when non-empty.
    for field in ("txlist_hash", "messages_hash", "block_hash"):
        exp = expected.get(field)
        if exp and exp != actual.get(field):
            mismatches.append((field, exp, actual.get(field)))

    exp_ledger = expected.get("ledger_hash")
    if exp_ledger and exp_ledger != (actual.get("ledger_hash") or ""):
        mismatches.append(("ledger_hash", exp_ledger, actual.get("ledger_hash")))

    if mismatches:
        block_logger.error(f"Reference validation failed at block {block_index}")
        for field, exp, act in mismatches:
            block_logger.error(f"  {field} mismatch: expected={exp} actual={act}")
        return False

    block_logger.info(f"Block {block_index} reference validation successful")
    return True


def filter_block_transactions(block_data, stamp_issuances=None):
    """
    Filter transactions from a block based on genesis status.
    IMPORTANT: Always maintains complete tx_hash_list for hash calculation.
    Uses Rust parser for efficient batch processing if available.
    """
    logger.debug(f"Starting filter_block_transactions with {len(block_data['tx'])} transactions")

    # Initialize raw_transactions for filtered transactions
    raw_transactions = {}

    # Get all transactions from block
    all_txs = block_data["tx"]
    # CRITICAL: Create tx_hash_list with ALL transactions in original order for hash calculation
    tx_hash_list = [tx["txid"] for tx in all_txs]
    logger.debug(f"Created tx_hash_list with {len(tx_hash_list)} transactions for hash calculation")

    # Get set of issuance transactions if any
    issuance_tx_hashes = {issuance["tx_hash"] for issuance in stamp_issuances} if stamp_issuances else set()
    if issuance_tx_hashes:
        logger.debug(f"Found {len(issuance_tx_hashes)} stamp issuance transactions")

    # Before SRC20 genesis, only get stamp issuance transactions
    # Handle the case where CURRENT_BLOCK_INDEX is None
    current_block_index = util.CURRENT_BLOCK_INDEX or 0
    if current_block_index < config.BTC_SRC20_GENESIS_BLOCK:
        logger.debug("Pre-genesis block: processing only stamp issuances")
        # Only process issuance transactions (in order)
        for tx in all_txs:
            if tx["txid"] in issuance_tx_hashes:
                raw_transactions[tx["txid"]] = tx["hex"]
        logger.debug(f"Processed {len(raw_transactions)} pre-genesis transactions")
        return tx_hash_list, raw_transactions

    logger.debug("Post-genesis block: processing all potential transactions")
    # After genesis block:
    # 1. First add all stamp issuance transactions (in order)
    for tx in all_txs:
        if tx["txid"] in issuance_tx_hashes:
            raw_transactions[tx["txid"]] = tx["hex"]
            logger.debug(f"Added issuance transaction: {tx['txid']}")

    # 2. Process remaining transactions
    non_issuance_txs = [tx for tx in all_txs if tx["txid"] not in issuance_tx_hashes]
    logger.debug(f"Found {len(non_issuance_txs)} non-issuance transactions to filter")

    if non_issuance_txs:
        # Create a mapping of transaction ID to transaction object for easy lookup
        tx_id_to_tx = {tx["txid"]: tx for tx in non_issuance_txs}

        # Check if Rust parser is available and properly initialized
        if backend_instance._parser is not None:
            logger.debug("Using Rust parser for batch processing")

            # Create a list of transaction hexes in the same order as non_issuance_txs
            tx_hexes = [tx["hex"] for tx in non_issuance_txs]

            try:
                # Process transactions with Rust parser
                # Note: The Rust parser now only returns transactions that should be included
                parsed_txs = backend_instance._parser.batch_parse_transactions(tx_hexes)
                logger.debug(f"Rust parser returned {len(parsed_txs)} filtered results from {len(tx_hexes)} inputs")

                # Process each parsed transaction (all of which should be included)
                for parsed_tx in parsed_txs:
                    if parsed_tx is not None:
                        try:
                            # Try to get the txid from the parsed_tx object
                            # This should work with our EnhancedCTransaction class
                            tx_id = parsed_tx.txid

                            if tx_id in tx_id_to_tx:
                                raw_transactions[tx_id] = tx_id_to_tx[tx_id]["hex"]
                                logger.debug(f"Rust parser included transaction {tx_id}")
                            else:
                                logger.warning(f"Transaction {tx_id} returned by Rust parser not found in tx_id_to_tx")
                        except AttributeError as e:
                            logger.error(f"Transaction missing txid attribute: {e}")
                            # Skip this transaction
                            continue

            except Exception as e:
                logger.critical(f"Error in batch_parse_transactions: {e}, falling back to Python implementation")
                logger.exception(e)  # Log the full exception with traceback

                # Only use Python fallback if Rust parser completely fails
                for tx in non_issuance_txs:
                    try:
                        ctx = backend_instance.deserialize(tx["hex"])
                        filter_result = quick_filter_src20_transaction(ctx)

                        if filter_result:
                            raw_transactions[tx["txid"]] = tx["hex"]
                            logger.debug(f"Python fallback included transaction {tx['txid']}")
                    except Exception as e:
                        logger.error(f"Error processing transaction {tx['txid']}: {e}")
        else:
            # Use Python implementation if Rust parser is not available
            logger.debug("Using Python implementation for filtering")

            for tx in non_issuance_txs:
                try:
                    ctx = backend_instance.deserialize(tx["hex"])
                    filter_result = quick_filter_src20_transaction(ctx)

                    if filter_result:
                        raw_transactions[tx["txid"]] = tx["hex"]
                except Exception as e:
                    logger.error(f"Error processing transaction {tx['txid']}: {e}")

    logger.debug(f"Final transaction count: {len(raw_transactions)} filtered, {len(tx_hash_list)} total for hash")
    return tx_hash_list, raw_transactions


# ---------------------------------------------------------------------------
# Issue #756 item 3 — skip the CP API fetch for blocks with no Counterparty data
# ---------------------------------------------------------------------------
#
# Consumes #754's over-approximating ``TransactionInfo.has_counterparty_data``.
# That signal is SOUND for skipping: it is a strict over-approximation that
# never yields a false negative, so a block it reports as CP-free genuinely
# carries no Counterparty data and the CP API call can be elided without ever
# dropping an issuance (which would corrupt MAX(stamp)+1 numbering).
#
# Gated by ``config.CP_SKIP_NO_COUNTERPARTY_BLOCKS`` (default False); when the
# flag is off everything below is a thin pass-through and behavior is byte-
# identical to a normal fetch.


def _empty_cp_block_data(block_index: int) -> Dict[str, Any]:
    """Return the exact ``block_data`` shape a real CP fetch yields for a block
    with zero Counterparty transactions.

    Verified against ``fetch_utils`` — a CP-free block flows through
    ``_fetch_block_transactions_verbose_safe_pagination`` with an empty
    ``all_transactions`` list, producing::

        {"block_index": n, "xcp_block_hash": None, "transactions": [], "issuances": []}

    (``xcp_block_hash`` is taken from ``all_transactions[0]`` which is absent, so
    it is ``None``.) Downstream consumers (blocks.py xcp_hash resolution,
    filter_block_transactions) read exactly these keys, so the substitute is
    behavior-identical to a real empty fetch.
    """
    return {"block_index": block_index, "xcp_block_hash": None, "transactions": [], "issuances": []}


def txs_have_counterparty_data(raw_parser: Any, tx_hexes: List[str]) -> bool:
    """Return True if ANY transaction hex carries Counterparty data.

    Pure helper over the raw Rust ``FastTransactionParser`` (the inner parser,
    NOT the ``Parser`` wrapper whose ``deserialize_transaction`` converts to a
    ``CTransaction`` and drops the ``has_counterparty_data`` field). Short-
    circuits on the first CP-bearing tx.

    Fail-safe: if the parser predates #754 and a parsed tx lacks the
    ``has_counterparty_data`` attribute, we cannot soundly skip, so we report
    True (treat the block as CP-bearing -> fetch as normal).
    """
    for tx_hex in tx_hexes:
        info = raw_parser.deserialize_transaction(tx_hex)
        if not hasattr(info, "has_counterparty_data"):
            return True
        if info.has_counterparty_data:
            return True
    return False


def block_has_counterparty_data(block_index: int) -> bool:
    """Over-approximating predicate: does Bitcoin block ``block_index`` contain
    any Counterparty transaction?

    Sound for the #756 skip (never a false negative). Parses every transaction
    in the block via the Rust parser's ``has_counterparty_data`` (issue #754).
    The raw block is fetched from bitcoind here; the same block is fetched again
    at processing time — an acceptable, cheap local RPC cost on this perf-gated
    path.

    Fail-safe: on ANY error or when the parser is unavailable, returns True so
    the caller fetches from the CP API as normal (never skips on uncertainty).
    """
    parser_wrapper = getattr(backend_instance, "_parser", None)
    raw_parser = getattr(parser_wrapper, "_parser", None)
    if raw_parser is None:
        return True
    try:
        block_hash = backend_instance.getblockhash(block_index)
        block_hex = backend_instance.rpc("getblock", [block_hash, 0])
        _tx_hash_list, raw_transactions, *_ = raw_parser.parse_block(block_hex)
        return txs_have_counterparty_data(raw_parser, list(raw_transactions.values()))
    except Exception as e:
        logger.warning(
            f"CP-skip predicate failed for block {block_index} ({e}); "
            f"treating as CP-bearing and fetching from CP API to stay safe"
        )
        return True


def _contiguous_runs(indices: List[int]) -> List[Tuple[int, int]]:
    """Group a list of block indices into contiguous (start, end) inclusive runs."""
    runs: List[List[int]] = []
    for idx in sorted(indices):
        if runs and idx == runs[-1][1] + 1:
            runs[-1][1] = idx
        else:
            runs.append([idx, idx])
    return [(a, b) for a, b in runs]


def fetch_cp_blocks_skipping_empty(
    start_block: int, end_block: int, progress_indicator: bool = False
) -> Dict[int, Dict[str, Any]]:
    """Fetch CP block data for ``[start_block, end_block]``, eliding the CP API
    call for blocks that carry no Counterparty data (issue #756 item 3).

    When ``config.CP_SKIP_NO_COUNTERPARTY_BLOCKS`` is False (default), this is a
    direct pass-through to ``fetch_xcp_blocks_concurrent`` — byte-identical to
    the prior behavior. When True, each block in the range is classified via
    ``block_has_counterparty_data`` (the sound #754 predicate); CP-free blocks
    get the exact empty-fetch shape substituted (no API call), and the CP-
    bearing blocks are fetched in contiguous runs to preserve the concurrent
    range-fetch contract and ordering.
    """
    # Lazy import to avoid a module-load import cycle (fetch_utils -> ... -> here).
    from index_core.fetch_utils import fetch_xcp_blocks_concurrent

    if not getattr(config, "CP_SKIP_NO_COUNTERPARTY_BLOCKS", False):
        return fetch_xcp_blocks_concurrent(start_block, end_block, progress_indicator=progress_indicator)

    cp_bearing: List[int] = []
    results: Dict[int, Dict[str, Any]] = {}
    for idx in range(start_block, end_block + 1):
        if block_has_counterparty_data(idx):
            cp_bearing.append(idx)
        else:
            logger.info(f"Block {idx}: no Counterparty data (issue #756) — skipping CP API fetch")
            results[idx] = _empty_cp_block_data(idx)

    for run_start, run_end in _contiguous_runs(cp_bearing):
        fetched = fetch_xcp_blocks_concurrent(run_start, run_end, progress_indicator=progress_indicator)
        if fetched:
            results.update(fetched)

    return results
