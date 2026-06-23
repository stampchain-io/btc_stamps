#!/usr/bin/env python3
"""Clear persistent fallback state from the reprocess queue (issue #784).

Default invocation lists current state without modifying anything. Pass
``--clear`` to drop all fallback sessions, or ``--clear-block N`` to drop a
specific session. Destructive actions require interactive confirmation unless
``--yes`` is given.

The script uses the same ``ReprocessingQueue`` singleton the indexer uses, so
it resolves the SQLite DB path identically (typically
``~/.local/share/btc_stamps/reprocess_queue.db``).

Typical operator flow after the indexer logs a startup fallback warning:

    poetry run python indexer/tools/clear_fallback_state.py            # inspect
    poetry run python indexer/tools/clear_fallback_state.py --clear    # confirm + clear
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running directly from a checkout without installing the package.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from index_core.reprocessing_queue import ReprocessingQueue  # noqa: E402


def _list_sessions(queue: ReprocessingQueue) -> list[tuple[int, int]]:
    """Return [(start_block_index, failed_block_count), ...] for every session."""
    with queue.lock:
        cur = queue.conn.cursor()
        cur.execute("""
            SELECT s.start_block_index, COUNT(f.block_index)
            FROM fallback_sessions s
            LEFT JOIN failed_blocks f ON f.session_id = s.id
            GROUP BY s.start_block_index
            ORDER BY s.start_block_index
            """)
        return cur.fetchall()


def _confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        print("Refusing to act non-interactively without --yes", file=sys.stderr)
        return False
    return input(prompt).strip().lower() in ("yes", "y")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clear", action="store_true", help="Drop ALL fallback sessions")
    parser.add_argument("--clear-block", type=int, metavar="N", help="Drop only the session starting at block N")
    parser.add_argument("--yes", action="store_true", help="Skip the interactive confirmation prompt")
    args = parser.parse_args()

    if args.clear and args.clear_block is not None:
        parser.error("--clear and --clear-block are mutually exclusive")

    queue = ReprocessingQueue.get_instance()
    print(f"Fallback DB: {queue.db_path}")

    sessions = _list_sessions(queue)
    if not sessions:
        print("No fallback sessions recorded — nothing to clear.")
        return 0

    print(f"Found {len(sessions)} fallback session(s):")
    for start_block, failed_count in sessions:
        print(f"  start_block={start_block}  failed_blocks={failed_count}")

    if not (args.clear or args.clear_block is not None):
        print("\n(read-only) Re-run with --clear or --clear-block N to modify.")
        return 0

    if args.clear_block is not None:
        target_blocks = [args.clear_block]
        if args.clear_block not in {row[0] for row in sessions}:
            print(f"\nNo session at start_block={args.clear_block}; nothing to do.")
            return 0
        action_desc = f"clear session starting at block {args.clear_block}"
    else:
        target_blocks = [row[0] for row in sessions]
        action_desc = f"clear ALL {len(target_blocks)} session(s)"

    if not args.yes and not _confirm(f"\nProceed to {action_desc}? Type 'yes': "):
        print("Aborted.")
        return 1

    for start_block in target_blocks:
        queue.clear_fallback_state(start_block)
        print(f"  cleared start_block={start_block}")

    print(f"\nDone. {len(target_blocks)} session(s) cleared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
