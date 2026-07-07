#!/usr/bin/env python3
"""Reparse CLI for Bitcoin Stamps: snapshot creation and pure in-memory validation."""

import os
import sys

# Force in-memory reparse to use mock DB (in-memory, no real pool or connections)
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["TESTING"] = "1"
from typing import TYPE_CHECKING, Any, Dict, Iterator, Optional, Union
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from index_core.database_manager import DatabaseManager

import importlib.util
import json  # for debug dump of hash dicts
import logging
import time  # for measuring validation duration
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

import index_core.caching as reparse_caching
import index_core.util as util
from index_core.block_validation import (
    create_check_hashes,
    filter_block_transactions,
)
from index_core.blocks import (
    BlockProcessor,
    backend_instance,
)
from index_core.fetch_utils import fetch_xcp_blocks_concurrent
from index_core.transaction_utils import prefetch_source_prevouts, process_tx

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
        start = time.time()
        logger.block_status("Validating block %s...", blk)  # type: ignore[attr-defined]
        ok = validator.validate_block(blk)
        duration = time.time() - start
        if not ok:
            logger.block_status("Validation failed at block %s (took %ss)", blk, f"{duration:.2f}")  # type: ignore[attr-defined]
            sys.exit(1)
        logger.block_status("Block %s validated in %ss", blk, f"{duration:.2f}")  # type: ignore[attr-defined]
        reparse_caching.cache_manager.check_memory_pressure()
    logging.info("All blocks validated successfully")
    sys.exit(0)


@contextmanager
def _force_post_genesis_filter() -> Iterator[None]:
    """Force ``filter_block_transactions`` to take its post-genesis branch.

    ``block_validation.filter_block_transactions`` gates on
    ``block_index < config.BTC_SRC20_GENESIS_BLOCK``: pre-genesis it keeps only
    stamp-issuance txs, post-genesis it routes EVERY tx through the Rust parser.
    For deterministic in-memory reparse we want the post-genesis behaviour for
    every block (uniform parsing, no pre-genesis special-casing), so this
    temporarily lowers the threshold to ``CP_STAMP_GENESIS_BLOCK``.

    NOTE: this repurposes the ``BTC_SRC20_GENESIS_BLOCK`` config value as a
    filter-mode toggle — it does NOT relocate the actual SRC-20-on-Bitcoin
    genesis, which is unchanged for every other consumer. The value is restored
    in ``finally`` so a transient bitcoind / CP-core error can't leak the
    mutated threshold into later blocks for the process lifetime.

    The restore-on-exit/exception behaviour is pinned by
    ``test_force_post_genesis_filter``. The toggle is also correct today only
    because no non-issuance tx in the CP era (779,652–793,067) carries a payload
    the Rust parser classifies as protocol traffic; that empirical invariant is
    guarded at integration level by the Tier-3 reparse of the CP-era curated
    blocks — a leak would surface there as a consensus-hash mismatch. The toggle
    goes away entirely once the Rust parser does CP/stamp pre-detection and every
    block is decoded uniformly (#754). See #774.
    """
    import config as _cfg

    orig = _cfg.BTC_SRC20_GENESIS_BLOCK
    _cfg.BTC_SRC20_GENESIS_BLOCK = _cfg.CP_STAMP_GENESIS_BLOCK
    try:
        yield
    finally:
        _cfg.BTC_SRC20_GENESIS_BLOCK = orig


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
        # Optional cross-block reissue lookup, injected by ``ReparseValidator`` from
        # the authoritative dev DB (``cpid`` stamped in an EARLIER block -> reissue).
        # ``None`` for DB-less runs: in-block reissue detection via the cache still works.
        self._reissue_lookup: Optional[Any] = None

    def _next_positive_number(self) -> int:
        """Return the next POSITIVE stamp number, mirroring ``get_next_stamp_number('stamp')``.

        The "counter" cache holds the LAST-USED positive number (seeded per block
        from ``MAX(stamp)`` of earlier blocks by ``_seed_stamp_counter``); the next
        is last-used + 1, and an unseeded counter yields 0 (production's default).
        """
        prev = reparse_caching.cache_manager.get_cache_value("stamp", "counter")
        if prev is None:
            prev = -1
        new = prev + 1
        reparse_caching.cache_manager.set_cache_value("stamp", "counter", new)
        return new

    def _next_cursed_number(self) -> int:
        """Return the next CURSED (negative) number, mirroring ``get_next_stamp_number('cursed')``.

        Symmetric to the positive counter: the "cursed_counter" cache holds the
        LAST-USED cursed number (seeded from ``MIN(stamp)`` of earlier blocks by
        ``_seed_cursed_counter``); the next is last-used - 1. When unseeded (no
        prior stamps at all) the last-used defaults to 0 so the first cursed number
        is -1 — exactly production's ``get_next_stamp_number`` ``default_value``.
        EVERY cursed stamp consumes one of these, even the A-cpid ones production
        does not emit, so the emitted (non-A) cursed stamps get production's numbers.
        """
        prev = reparse_caching.cache_manager.get_cache_value("stamp", "cursed_counter")
        if prev is None:
            prev = 0
        new = prev - 1
        reparse_caching.cache_manager.set_cache_value("stamp", "cursed_counter", new)
        return new

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

    def _classify_stamp(self, result: Any, data: dict) -> Union[str, tuple, None]:
        """Classify a stamp tx exactly as production does, reusing ``StampData``.

        Returns one of:
          * ``(is_btc_stamp, src_data, cpid)`` — production's verdict for the tx.
            ``is_btc_stamp=True`` => a valid Bitcoin Stamp (positive number);
            ``False`` => CURSED (negative number; emitted as a ValidStamp only when
            ``cpid`` does not start with "A"). ``cpid`` is production's FINAL cpid
            (``process_stamps_with_asset_longname`` rewrites POSH cpids to the
            asset_longname) so the caller can apply ``stamp.py``'s create-valid gate.
          * ``"drop"`` — production DROPS the tx entirely (no stamp number, no
            ValidStamp): a SRC-20/SRC-101 whose pure-format pre-check fails
            (``check_format`` / ``check_src101_inputs`` return ``None`` ->
            ``src20/101_pre_validation`` raises -> ``process_stamp`` swallows it),
            e.g. the empty-``tick`` SRC-20 mints in block 792853.
          * ``None`` — classification could not be completed; caller applies its
            default (treat as a valid stamp) handling.

        Verdicts come straight from the production pipeline, so they cannot drift:
        we drive the SAME ``StampData`` methods ``blocks.py`` drives
        (``get_base_64_data_from_trx`` -> ``determine_stamp_data_type`` ->
        ``update_stamp_data_rows_from_cp_asset``) and then production's OWN dispatch
        functions (``valid_src20`` / ``valid_src721`` / ``valid_src101`` /
        ``process_src721`` / ``process_all_stamps`` / ``process_cursed_*``). The only
        adaptation is that the DB-only SRC-20/SRC-101 SVG build in
        ``src20/101_pre_validation`` is replaced by its pure-format gate
        (``check_format`` / ``check_src101_inputs``, both DB-free) plus the two
        consensus-relevant field writes it performs (``is_btc_stamp = True``,
        ``file_suffix = "svg"``) — so the whole classifier is DB-less/off-host safe
        and a ``MagicMock`` DB (only the discarded SRC-721 SVG render would touch it)
        suffices. Any unexpected failure degrades to ``None``.

        Cursing (``is_btc_stamp=False``) happens when ``process_all_stamps`` rejects a
        cpid stamp — most commonly an INVALID ``file_suffix``
        (``json``/``octet-stream``/``plain``/``js``/``css``/``x-empty``), an
        ``asset_longname``, or an OP_RETURN: SRC-721 mints failing ``valid_src721``
        keep ``"json"``; cursed images sniff to ``octet-stream``; POSH/named assets
        curse via ``asset_longname``.
        """
        import threading

        from index_core.models import StampData
        from index_core.stamp import decode_base64, get_src_or_img_from_data

        try:
            stamp_data = StampData(
                tx_hash=result.tx_hash,
                source=getattr(result, "source", None),
                prev_tx_hash=getattr(result, "prev_tx_hash", None),
                destination=getattr(result, "destination", None),
                destination_nvalue=getattr(result, "destination_nvalue", None),
                btc_amount=getattr(result, "btc_amount", None),
                fee=getattr(result, "fee", None),
                fee_rate_sat_vb=getattr(result, "fee_rate_sat_vb", None),
                data=result.data,
                decoded_tx=getattr(result, "decoded_tx", None),
                keyburn=getattr(result, "keyburn", None),
                tx_index=getattr(result, "tx_index", None),
                block_index=result.block_index,
                block_time=getattr(result, "block_time", None),
                is_op_return=getattr(result, "is_op_return", None),
                p2wsh_data=getattr(result, "p2wsh_data", None),
            )
            # process_src721 guards its collection work with ``with self._lock``.
            stamp_data._lock = threading.Lock()
            # Mirror production's ``process_and_store_stamp_data``: seed the base64
            # fields, run the real decode/ident dispatch, then the CP-issuance fields
            # (supply/cpid/asset_longname) the validity gates read.
            stamp_data.get_base_64_data_from_trx(get_src_or_img_from_data, data)
            stamp_data.determine_stamp_data_type(decode_base64)
            stamp_data.update_stamp_data_rows_from_cp_asset(data)

            ident_known = stamp_data.ident != "UNKNOWN"
            cpid_starts_with_A = bool(stamp_data.cpid and stamp_data.cpid.startswith("A"))
            # Reproduce ``validate_and_process_stamp_data``'s dispatch, swapping the
            # DB-only SRC-20/101 SVG build for the pure-format gate so we stay DB-free
            # AND can observe production's "invalid pre-check -> DROP" outcome (which
            # otherwise surfaces as a swallowed exception in ``process_stamp``).
            if stamp_data.valid_src20():
                from index_core.src20 import check_format

                if check_format(stamp_data.decoded_base64, stamp_data.tx_hash, stamp_data.block_index) is None:
                    return "drop"  # src20_pre_validation raises -> tx dropped
                stamp_data.is_btc_stamp = True
                stamp_data.file_suffix = "svg"
            elif stamp_data.valid_src721():
                stamp_data.process_src721(self.valid_stamps_in_block, MagicMock())
            elif stamp_data.valid_src101():
                from index_core.src101 import check_src101_inputs

                if check_src101_inputs(stamp_data.decoded_base64, stamp_data.tx_hash, stamp_data.block_index) is None:
                    return "drop"  # src101_pre_validation raises -> tx dropped
                stamp_data.is_btc_stamp = True
            # Shared post-classification tail (identical to production's).
            if stamp_data.cpid:
                stamp_data.process_all_stamps(ident_known, cpid_starts_with_A)
            else:
                stamp_data.process_cursed_with_other_conditions(cpid_starts_with_A, ident_known)

            src_data = stamp_data.src_data if stamp_data.src_data is not None else ""
            return (bool(stamp_data.is_btc_stamp), src_data, stamp_data.cpid)
        except Exception:
            logging.getLogger(__name__).debug(
                f"Could not classify stamp for tx {getattr(result, 'tx_hash', '?')}; using default handling"
            )
            return None

    def process_transaction_results(self, tx_results: list) -> None:
        """Process transaction results and update in-memory state."""
        # Reuse the SAME production helpers the real indexer uses so the
        # validator's ValidStamp dicts are byte-identical to production and the
        # two paths cannot drift. ``get_src_or_img_from_data`` performs the exact
        # base64 parse/decode ``StampData.get_base_64_data_from_trx`` runs, and
        # ``create_valid_stamp_dict`` builds the exact ValidStamp TypedDict that
        # feeds ``str(sorted_valid_stamps)`` in ``create_check_hashes``.
        import base64

        from config import CP_P2WSH_FEAT_BLOCK_START
        from index_core.stamp import create_valid_stamp_dict, decode_base64, get_src_or_img_from_data

        for result in tx_results:
            if not getattr(result, "data", None):
                continue
            data = result.data
            # Parse data string into dict if necessary. Use the SAME production
            # converter (``convert_to_dict_or_string``) the real indexer uses:
            # issuance ``data`` is a JSON string (``json.dumps(stamp_issuance)``
            # in ``list_tx``) containing JSON literals (``false``/``true``/
            # ``null``) that ``ast.literal_eval`` cannot parse — so the previous
            # code silently dropped EVERY stamp, emitting an empty valid-stamp
            # list whose txlist_hash only matched for stamp-free blocks.
            # NOTE: native SRC-20/721/101 (P2WSH witness, no CP issuance) arrive as
            # RAW BYTES from ``get_tx_info`` (``data = data_chunk_without_prefix``),
            # NOT a str — ``list_tx`` only json.dumps()es the data for CP issuances.
            # The previous ``isinstance(data, str)``-only guard let those bytes fall
            # straight through to ``if not isinstance(data, dict): continue`` and be
            # DROPPED, so every native SRC-20 stamp vanished from both
            # ``valid_stamps_in_block`` (breaking txlist_hash + mis-numbering any
            # image stamp sharing the block) and ``processed_src20_in_block``.
            # ``convert_to_dict_or_string`` already handles bytes exactly as
            # production's ``process_and_store_stamp_data`` does.
            if isinstance(data, (str, bytes)):
                try:
                    data = util.convert_to_dict_or_string(data, output_format="dict")
                except Exception:
                    logging.getLogger(__name__).debug(f"Could not parse transaction data: {data!r}")
                    continue
            if not isinstance(data, dict):
                continue
            # CPID reissuance exclusion. Production's ``check_reissue`` treats a cpid
            # as a reissue if it is already stamped: in the reissue cache, earlier in
            # THIS block's valid_stamps, or in the DB from an EARLIER block. The
            # in-memory cache covers the first two; ``_reissue_lookup`` (seeded by the
            # validator from the authoritative dev DB, ``cpid`` present at
            # ``block_index < N``) covers the cross-block DB case a single-block
            # reparse cannot otherwise see — e.g. block 792853, whose reissued cpids
            # were first stamped in earlier blocks. Best-effort: ``None`` off-host.
            cpid = data.get("cpid")
            if cpid and reparse_caching.cache_manager.get_cache_value("reissue", cpid):
                continue
            if cpid and self._reissue_lookup is not None and self._reissue_lookup(cpid, result.block_index):
                continue
            # Reuse production's cursed-vs-valid verdict BEFORE committing this tx to
            # a stamp number / the valid-stamp list. A tx production CURSES (an
            # INVALID file_suffix such as SRC-721's un-processed "json" or an image's
            # "octet-stream", an asset_longname, an OP_RETURN, ...) is given a NEGATIVE
            # number from a separate cursed counter; SRC-20/SRC-101 return ``None``
            # (DB-touching pre-validation) and fall through to the unchanged per-type
            # handling as a valid stamp.
            src_data_value = ""
            prod_cpid = None
            is_cursed_stamp = False
            classification = self._classify_stamp(result, data)
            if classification == "drop":
                # Production drops this tx entirely (invalid SRC-20/SRC-101 pre-check):
                # no stamp number of EITHER kind is consumed and no ValidStamp emitted.
                continue
            if isinstance(classification, tuple):
                is_btc_stamp_cls, src_data_value, prod_cpid = classification
                is_cursed_stamp = not is_btc_stamp_cls
            # Assign the stamp number from the matching monotonic counter, each
            # advancing in on-chain order exactly like production's
            # ``get_next_stamp_number``: VALID stamps take the positive counter
            # (last-used + 1, seeded from ``MAX(stamp)``); CURSED stamps take the
            # negative cursed counter (last-used - 1, seeded from ``MIN(stamp)``).
            if is_cursed_stamp:
                new_stamp_num = self._next_cursed_number()
                # Production emits a ValidStamp for a cursed stamp ONLY when its final
                # cpid is truthy and does NOT start with "A" (``stamp.py`` create-valid
                # gate: ``is_cursed and cpid and not cpid.startswith("A")``). Every
                # SRC-721 and every cursed image is A-cpid: it consumed a cursed
                # number above (so later emitted cursed stamps get the right numbers)
                # but produces NO ValidStamp and never advances the positive counter.
                # Cursed NON-A stamps (POSH/named assets, e.g. 784013 WARBONDS.ONE)
                # ARE emitted, with the negative number, below.
                if not prod_cpid or str(prod_cpid).startswith("A"):
                    continue
            else:
                new_stamp_num = self._next_positive_number()
            # In-block reissue tracking: mark the cpid as seen for stamps we actually
            # emit (production finds a same-block repeat via the reissue cache for
            # btc_stamps and via valid_stamps for cursed), so a later dup in the same
            # block is excluded. Skipped A-cpid cursed stamps intentionally do NOT
            # populate it (production emits nothing for them).
            if cpid:
                reparse_caching.cache_manager.set_cache_value("reissue", cpid, True)
            # Derive the real base64 fields exactly as production's
            # ``StampData.determine_stamp_data_type`` does, so the ValidStamp is
            # byte-identical. Two mutually-exclusive branches, keyed the same way
            # production keys them:
            #   * OLGA / P2WSH (p2wsh_data present and block >= P2WSH feature
            #     start): the image bytes live in the witness, NOT the CP
            #     description — ``stamp_base64`` is ``b64encode(p2wsh_data)`` and
            #     ``is_valid_base64`` comes from decoding that (mirrors
            #     ``process_p2wsh_data``).
            #   * MULTISIG / description: ``get_src_or_img_from_data`` parses the
            #     base64 out of the CP issuance description and decodes it
            #     (mirrors ``get_base_64_data_from_trx``). For SRC protocols it
            #     returns ``(stamp, None, None, 1)``.
            # create_valid_stamp_dict normalises None -> "" / False, matching
            # production's ValidStamp exactly.
            p2wsh_data = getattr(result, "p2wsh_data", None)
            try:
                if p2wsh_data is not None and result.block_index >= CP_P2WSH_FEAT_BLOCK_START:
                    stamp_base64 = base64.b64encode(p2wsh_data).decode()
                    _decoded_base64, is_valid_base64 = decode_base64(stamp_base64, result.block_index)
                else:
                    _decoded_base64, stamp_base64, _stamp_mimetype, is_valid_base64 = get_src_or_img_from_data(
                        data, result.block_index
                    )
            except Exception:
                # Mirror production: an invalid ``p`` (or other decode failure)
                # yields no usable base64; fall back to empty/false so the dict
                # is still well-formed.
                stamp_base64, is_valid_base64 = None, None
            # Native SRC-20/721/101 issuances carry no CP ``cpid``; production
            # backfills it with the stamp_hash in ``update_cpid_and_stamp_url``
            # (``self.cpid = self.cpid if self.cpid else self.stamp_hash``, where
            # ``stamp_hash = create_base62_hash(tx_hash, str(block_index), 20)``).
            # Reuse that exact production helper so the hashed ValidStamp ``cpid``
            # is byte-identical (e.g. block 800175 -> "Aq2PmdeKENTlmafYo9j7") instead
            # of the empty string the old code emitted.
            # The ValidStamp cpid: a CURSED stamp uses production's FINAL cpid — POSH
            # assets are rewritten to their asset_longname (e.g. "WARBONDS.ONE") by
            # ``process_stamps_with_asset_longname`` — while a VALID stamp uses the CP
            # cpid, backfilling native SRC issuances with the stamp_hash exactly as
            # production's ``update_cpid_and_stamp_url`` does (e.g. block 800175 ->
            # "Aq2PmdeKENTlmafYo9j7") instead of the empty string the old code emitted.
            if is_cursed_stamp:
                cpid_value = prod_cpid
            else:
                cpid_value = data.get("cpid") or util.create_base62_hash(result.tx_hash, str(result.block_index), 20)
            # ``src_data_value`` was already computed above by ``_classify_stamp``
            # (production's ``json.dumps`` of the symbol->tick-mutated deploy/mint JSON
            # for a valid JSON SRC-721; "" for every other stamp type). Feed it and the
            # cursed flags straight into the ValidStamp so txlist_hash matches
            # production byte-for-byte.
            valid_stamp = create_valid_stamp_dict(
                new_stamp_num,
                result.tx_hash,
                cpid_value,
                not is_cursed_stamp,  # is_btc_stamp: False for an emitted cursed stamp
                # Mirror production's ``bool(stamp_data.is_valid_base64)``: the SRC
                # branch of ``get_src_or_img_from_data`` returns the int ``1``, which
                # must render as ``True`` in the hashed ValidStamp, not ``1``.
                bool(is_valid_base64) if is_valid_base64 is not None else False,
                stamp_base64 if not isinstance(stamp_base64, dict) else None,
                is_cursed_stamp,  # is_cursed
                src_data_value,
            )
            self.valid_stamps_in_block.append(valid_stamp)
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
        # Lazily-opened read-only connection to the authoritative dev DB, used
        # only to prime the global stamp counter (see _seed_stamp_counter).
        self._ref_db_conn: Optional[Any] = None
        self._ref_db_unavailable = False

    def _ref_conn(self) -> Optional[Any]:
        """Return a cached read-only connection to the authoritative dev DB (or None).

        Shared by the two consensus-NEUTRAL, best-effort seeders that need the same
        dev DB the reference hashes were snapshotted from (``_seed_stamp_counter``
        for global stamp numbering, ``_reconstruct_valid_src20_str`` for the SRC-20
        balance ledger). On any connection failure it flips ``_ref_db_unavailable``
        so DB-less / off-host runs degrade gracefully instead of raising.
        """
        if self._ref_db_unavailable:
            return None
        conn = self._ref_db_conn
        if conn is not None and getattr(conn, "open", False):
            return conn
        try:
            import pymysql

            conn = pymysql.connect(
                host=os.environ.get("RDS_HOSTNAME", "localhost"),
                user=os.environ.get("RDS_USER") or os.environ.get("MYSQL_USER", "admin"),
                password=os.environ.get("RDS_PASSWORD") or os.environ.get("MYSQL_PASSWORD", "password"),
                database=os.environ.get("RDS_DATABASE", "btc_stamps"),
                port=int(os.environ.get("RDS_PORT", 3306)),
                charset="utf8mb4",
                connect_timeout=30,
            )
            self._ref_db_conn = conn
            return conn
        except Exception as e:
            self._ref_db_unavailable = True
            logger.debug(f"Reference dev DB unavailable ({e}); DB-backed seeding disabled")
            return None

    def _last_nonempty_ledger_hash(self, block_index: int) -> str:
        """Return the most recent NON-empty ledger hash strictly before ``block_index``.

        The SRC-20 ledger hash chains only across blocks that carry SRC-20 activity;
        every other block stores an empty ledger hash. Production reproduces the
        chain via ``check.consensus_hash``'s DB walk-back; here we resolve it from
        the already-loaded snapshot so single-block validation feeds
        ``create_check_hashes`` a correct, truthy previous hash. Returns "" if none
        exists (pre-first-SRC-20 history).
        """
        hashes = self.snapshot_manager.load_snapshot().get("hashes", {})
        b = block_index - 1
        while b > 0:
            entry = hashes.get(str(b))
            if entry and entry.get("ledger_hash"):
                return entry["ledger_hash"]
            b -= 1
        return ""

    def _reconstruct_valid_src20_str(self, block_index: int) -> str:
        """Reconstruct production's ``valid_src20_str`` (the ledger_hash content).

        ``finalize_block`` builds this string from ``update_src20_balances`` ->
        ``process_balance_updates`` = for every (tick, address) touched by a valid
        MINT/TRANSFER in the block, the address's POST-BLOCK balance, formatted
        ``tick,address,amt`` and sorted/joined by ``process_balance_updates``.

        Reproducing that in-memory for a standalone block would require the SRC-20
        balance state as of ``block_index - 1`` (not stored anywhere queryable), so
        instead — mirroring ``_seed_stamp_counter``'s "read the authoritative answer
        from the dev DB" approach — we read the effective per-op amounts from the
        authoritative ``SRC20Valid`` table (which stores ONLY valid ops, with the
        post-ODL/OMA-reduction ``amt``) and compute each touched address's post-block
        balance as the cumulative signed sum of those amts (credit destination,
        debit TRANSFER creator) up to and including this block. The byte-exact
        formatting/sorting is delegated to the PRODUCTION ``process_balance_updates``
        helper so the output cannot drift.

        Consensus-NEUTRAL and best-effort: on any DB failure returns "" (the block's
        ledger check then degrades like a DB-less run) rather than raising.
        """
        conn = self._ref_conn()
        if conn is None:
            return ""
        try:
            from decimal import Decimal as D

            from config import CP_SRC20_GENESIS_BLOCK
            from index_core.src20 import process_balance_updates

            if block_index <= CP_SRC20_GENESIS_BLOCK:
                return ""
            with conn.cursor() as cursor:
                # Distinct (tick, tick_hash, address) pairs touched by a valid
                # MINT/TRANSFER in THIS block — exactly the balance_updates keys
                # production's update_src20_balances would build.
                cursor.execute(
                    """
                    SELECT DISTINCT tick, tick_hash, addr FROM (
                        SELECT tick, tick_hash, destination AS addr FROM SRC20Valid
                            WHERE block_index = %s AND op IN ('MINT', 'TRANSFER')
                        UNION
                        SELECT tick, tick_hash, creator AS addr FROM SRC20Valid
                            WHERE block_index = %s AND op = 'TRANSFER'
                    ) t
                    """,  # nosec B608
                    (block_index, block_index),
                )
                touched = cursor.fetchall()
                if not touched:
                    return ""
                balance_updates = []
                for tick, tick_hash, addr in touched:
                    # Post-block balance = cumulative signed amt across all valid ops
                    # up to and including this block: destinations credited, TRANSFER
                    # creators debited. (SRC20Valid's *_bal columns are written during
                    # threaded validation and are NOT a reliable sequential running
                    # balance, so they are intentionally not used here.)
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(delta), 0) FROM (
                            SELECT amt AS delta FROM SRC20Valid
                                WHERE block_index <= %s AND op IN ('MINT', 'TRANSFER')
                                  AND tick = %s AND tick_hash = %s AND destination = %s
                            UNION ALL
                            SELECT -amt AS delta FROM SRC20Valid
                                WHERE block_index <= %s AND op = 'TRANSFER'
                                  AND tick = %s AND tick_hash = %s AND creator = %s
                        ) x
                        """,  # nosec B608
                        (block_index, tick, tick_hash, addr, block_index, tick, tick_hash, addr),
                    )
                    bal = cursor.fetchone()[0]
                    balance_updates.append(
                        {"tick": tick, "tick_hash": tick_hash, "address": addr, "net_change": D(0), "original_amt": D(bal)}
                    )
            return process_balance_updates(balance_updates)
        except Exception as e:
            logger.debug(f"Could not reconstruct valid_src20_str for block {block_index} ({e}); skipping SRC-20 ledger")
            return ""

    def _seed_stamp_counter(self, block_index: int) -> None:
        """Prime the in-memory stamp counter from the authoritative dev DB.

        Global Bitcoin-Stamp numbers are monotonic across the entire chain, so a
        standalone (or resumed) single-block in-memory validation cannot know how
        many stamps precede ``block_index`` on its own. Production assigns numbers
        via ``get_next_stamp_number`` == ``MAX(stamp) + 1``; we reproduce that
        anchor by reading ``MAX(stamp)`` over all EARLIER blocks from the same dev
        DB the reference hashes were snapshotted from, and priming the "counter"
        cache (which holds the LAST-USED number) with it — so the next stamp is
        ``MAX + 1``. NULL (no prior stamps) leaves the cache unset so the first
        stamp becomes number 0, matching production's ``default_value``.

        Best-effort and consensus-NEUTRAL: this only fixes stamp NUMBERING, never
        the decoded stamp fields. On any DB failure the in-memory accumulation is
        left untouched so DB-less / off-host runs still work (correct for
        stamp-free blocks and full genesis->tip sequences).
        """
        conn = self._ref_conn()
        if conn is None:
            return
        from config import STAMP_TABLE

        try:
            with conn.cursor() as cursor:
                # Only non-cursed (>= 0) stamps: the CP-era validator numbers
                # positive btc_stamps; cursed (negative) numbering is out of scope.
                cursor.execute(
                    f"SELECT MAX(stamp) FROM {STAMP_TABLE} WHERE block_index < %s AND stamp >= 0",  # nosec
                    (block_index,),
                )
                row = cursor.fetchone()
            max_stamp = row[0] if row else None
            if max_stamp is not None:
                reparse_caching.cache_manager.set_cache_value("stamp", "counter", int(max_stamp))
            logger.debug(f"Seeded stamp counter for block {block_index}: last-used = {max_stamp}")
        except Exception as e:
            # Never let numbering-seed failure halt validation; fall back to the
            # in-memory counter (accurate for stamp-free blocks / full sequences).
            self._ref_db_unavailable = True
            logger.debug(f"Could not seed stamp counter from dev DB for block {block_index} ({e}); using in-memory counter")

    def _seed_cursed_counter(self, block_index: int) -> None:
        """Prime the in-memory CURSED counter from the authoritative dev DB.

        The mirror image of ``_seed_stamp_counter``: cursed (negative) Bitcoin-Stamp
        numbers are also monotonic across the chain, assigned by production's
        ``get_next_stamp_number('cursed')`` == ``MIN(stamp) - 1``. We prime the
        "cursed_counter" cache (LAST-USED cursed number) with ``MIN(stamp)`` over all
        EARLIER blocks so the next cursed stamp is ``MIN - 1`` (e.g. block 784013's
        WARBONDS.ONE gets ``-123`` from a prior ``MIN`` of ``-122``). ``MIN(stamp)``
        is taken over ALL stamps (cursed are negative, so it is the most-negative
        cursed number, or ``0`` when only positives precede — matching production's
        unfiltered ``SELECT MIN(stamp)``). NULL (empty history) leaves the cache
        unset so the first cursed number becomes ``-1`` (production's ``default_value``).

        Best-effort and consensus-NEUTRAL, exactly like ``_seed_stamp_counter``.
        """
        conn = self._ref_conn()
        if conn is None:
            return
        from config import STAMP_TABLE

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT MIN(stamp) FROM {STAMP_TABLE} WHERE block_index < %s",  # nosec
                    (block_index,),
                )
                row = cursor.fetchone()
            min_stamp = row[0] if row else None
            if min_stamp is not None:
                reparse_caching.cache_manager.set_cache_value("stamp", "cursed_counter", int(min_stamp))
            logger.debug(f"Seeded cursed counter for block {block_index}: last-used = {min_stamp}")
        except Exception as e:
            self._ref_db_unavailable = True
            logger.debug(f"Could not seed cursed counter from dev DB for block {block_index} ({e}); using in-memory counter")

    def _is_cross_block_reissue(self, cpid: str, block_index: int) -> bool:
        """Return True if ``cpid`` was already stamped in an EARLIER block (a reissue).

        Reproduces production's ``check_reissue`` -> ``check_reissue_in_db`` (``SELECT
        ... WHERE cpid = %s``) for the single-block case: production processes blocks
        sequentially so at block N its DB holds only blocks < N, but the authoritative
        dev DB holds the WHOLE chain, so we must scope the lookup to ``block_index < N``
        to mean "stamped before this block". The in-block/same-block repeats are
        already handled by the reissue cache; this only adds the cross-block case
        (e.g. block 792853, whose reissued cpids first appear in earlier blocks).

        Consensus-NEUTRAL and best-effort: returns False on no connection / any DB
        error so DB-less / off-host runs degrade to cache-only reissue detection.
        """
        conn = self._ref_conn()
        if conn is None:
            return False
        from config import STAMP_TABLE

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT 1 FROM {STAMP_TABLE} WHERE cpid = %s AND block_index < %s LIMIT 1",  # nosec
                    (cpid, block_index),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.debug(f"Cross-block reissue lookup failed for cpid {cpid} at block {block_index} ({e})")
            return False

    def compute_block_hashes(
        self,
        block_index: int,
        block_processor: Optional[Union[BlockProcessor, InMemoryBlockProcessor]] = None,
    ) -> Dict[str, str]:
        """Compute hashes for a block using the same logic as production."""
        try:
            # Sync util so that filtering treats our reparse genesis as post-genesis
            util.CURRENT_BLOCK_INDEX = block_index
            import config as _cfg

            # See _force_post_genesis_filter: force every tx through the Rust
            # parser (post-genesis filter branch) for uniform in-memory reparse.
            with _force_post_genesis_filter():
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

            # Process transactions using BlockProcessor if not provided
            # Initialize an in-memory processor if none provided
            if block_processor is None:
                # Prime BOTH global counters from the authoritative dev DB so
                # in-memory numbering matches production for standalone blocks: the
                # positive counter (valid stamps) and the cursed counter (negative
                # numbers for cursed non-"A"/POSH stamps that production emits).
                self._seed_stamp_counter(block_index)
                self._seed_cursed_counter(block_index)
                block_processor = InMemoryBlockProcessor()
                # Inject the cross-block reissue lookup so a cpid first stamped in an
                # earlier block is excluded (dev-DB backed; None-safe off-host).
                block_processor._reissue_lookup = self._is_cross_block_reissue
                tx_results = []
                # Pre-warm the raw-transaction cache so each candidate's vin[0]
                # source lookup in get_tx_info is a cache hit (one batched RPC per
                # block instead of N serial round-trips). Output-neutral.
                prefetch_source_prevouts(raw_transactions)
                for tx_hash in raw_transactions.keys():
                    result = process_tx(None, tx_hash, block_index, stamp_issuances, raw_transactions)
                    if getattr(result, "data", None) is not None:
                        result = result._replace(block_index=block_index, block_hash=block_hash, block_time=block_data["time"])
                        tx_results.append(result)
                # Number stamps in on-chain (block) order, exactly as production does:
                # ``blocks.py`` sorts tx_results by ``txhash_list.index`` before
                # ``process_transaction_results`` (global stamp numbers are assigned in
                # that order). ``filter_block_transactions`` returns raw_transactions
                # with ALL CP issuances first and native SRC-20 after, so for a mixed
                # SRC-20 + image block the unsorted order would mis-number every stamp.
                tx_results = sorted(tx_results, key=lambda r: txhash_list.index(r.tx_hash))
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
            # Consensus rule (#775): at SRC-20 genesis+1, check.consensus_hash
            # requires the *previous* ledger hash to be unset and seeds it to
            # shash_string("") itself; a truthy previous_consensus_hash raises a
            # ConsensusError. Production passes a falsy previous_ledger_hash here,
            # but the validator otherwise feeds the prior block's snapshot hash
            # (or the zero-hash default), which is truthy — so it must mirror
            # production and pass "" for the ledger previous at this one block.
            # Only the ledger previous is special-cased; txlist/messages still
            # chain normally.
            prev_ledger_hash = prev_hashes["ledger_hash"]
            if block_index == _cfg.CP_SRC20_GENESIS_BLOCK + 1:
                prev_ledger_hash = ""
            elif not prev_ledger_hash:
                # The SRC-20 ledger hash only chains across blocks that carry SRC-20
                # activity; ``check.consensus_hash`` walks the DB back to the most
                # recent NON-empty ledger hash when the immediate predecessor's is
                # empty. Standalone / resumed single-block validation feeds a mock DB
                # that cannot answer that walk-back, so resolve it from the snapshot
                # and pass a truthy previous hash (consensus_hash then skips its own
                # DB lookup). Blocks with empty ledger content are unaffected.
                prev_ledger_hash = self._last_nonempty_ledger_hash(block_index)
            # Production's ``finalize_block`` feeds ``create_check_hashes`` the
            # ``valid_src20_str`` (post-block SRC-20 balances) as the ledger content,
            # NOT the raw ``processed_src20_in_block`` list. Reconstruct that string
            # so ledger_hash matches for native SRC-20 blocks; see
            # ``_reconstruct_valid_src20_str``.
            src20_ledger_content: Any = block_processor.processed_src20_in_block
            if isinstance(block_processor, InMemoryBlockProcessor):
                src20_ledger_content = self._reconstruct_valid_src20_str(block_index)
            try:
                new_ledger_hash, new_txlist_hash, new_messages_hash = create_check_hashes(
                    mock_db,
                    block_index,
                    block_processor.valid_stamps_in_block,
                    src20_ledger_content,
                    txhash_list,
                    prev_ledger_hash,
                    prev_hashes["txlist_hash"],
                    prev_hashes["messages_hash"],
                )
            finally:
                # Restore checkpoint entry if it was removed
                if orig_checkpoint is not None:
                    check_mod.CHECKPOINTS_MAINNET[block_index] = orig_checkpoint

            # Debug: log detailed state for this block
            logger.debug(f"Block {block_index} debug state:")
            logger.debug(f"  txhash_list (len {len(txhash_list)}): {txhash_list}")
            logger.debug(f"  valid_stamps_in_block: {block_processor.valid_stamps_in_block}")
            logger.debug(f"  processed_src20_in_block: {block_processor.processed_src20_in_block}")
            # Only InMemoryBlockProcessor has these attributes
            if isinstance(block_processor, InMemoryBlockProcessor):  # type: ignore[name-defined]
                logger.debug(f"  processed_src721_in_block: {block_processor.processed_src721_in_block}")  # type: ignore[union-attr]
                logger.debug(f"  processed_src101_in_block: {block_processor.processed_src101_in_block}")  # type: ignore[union-attr]
                logger.debug(f"  ledger_updates: {block_processor.ledger_updates}")  # type: ignore[union-attr]
            else:
                logger.debug("  processed_src721_in_block: []")
                logger.debug("  processed_src101_in_block: []")
                logger.debug("  ledger_updates: {}")
            logger.debug(f"  collection_operations: {block_processor.collection_operations}")

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
                    # Dump full computed vs expected for debugging
                    logger.debug(f"Full computed hashes: {json.dumps(computed_hashes, indent=2)}")
                    logger.debug(f"Full expected hashes: {json.dumps(expected_hashes, indent=2)}")
                    return False

            # Only compare ledger_hash if it's not empty in the snapshot
            if expected_hashes["ledger_hash"]:
                if computed_hashes["ledger_hash"] != expected_hashes["ledger_hash"]:
                    logger.error(
                        f"Hash mismatch for block {block_index} (ledger_hash):\n"
                        f"  Computed: {computed_hashes['ledger_hash']}\n"
                        f"  Expected: {expected_hashes['ledger_hash']}"
                    )
                    # Dump full computed vs expected for debugging
                    logger.debug(f"Full computed hashes: {json.dumps(computed_hashes, indent=2)}")
                    logger.debug(f"Full expected hashes: {json.dumps(expected_hashes, indent=2)}")
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
