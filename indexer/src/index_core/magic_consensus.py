"""
Consensus-anchor assertion for libmagic.

The txlist_hash depends on libmagic's MIME classification of stamp bytes
(file_suffix → is_btc_stamp → ValidStamp dict → str(list) → sha256). The
CHECKPOINTS in check.py were generated against libmagic 5.41. Drift to a
newer libmagic silently flips is_btc_stamp on classification-borderline
stamps (e.g. the 2023-byte ZIP-header stamp 7d6a382d… in block 783727 that
5.41 calls application/zip and 5.46 calls application/octet-stream) and
diverges every subsequent block's txlist_hash.

This module verifies at startup that the loaded libmagic matches the
consensus anchor and fails loud otherwise. The Dockerfile vendors the 5.41
binaries from Ubuntu 22.04; on host (systemd) installs, operators must
`apt-mark hold libmagic1 libmagic-mgc` on Ubuntu 22.04.
"""

import ctypes
import ctypes.util
import hashlib
import logging
import os

import config

logger = logging.getLogger(__name__)

# libmagic.magic_version() returns the version as an integer: 5.41 → 541.
CONSENSUS_LIBMAGIC_VERSION = 541

# sha256 of the libmagic-mgc 1:5.41-3ubuntu0.1 magic database, as shipped by
# Ubuntu 22.04. Verified identical on the host's /usr/lib/file/magic.mgc and
# /usr/share/misc/magic.mgc (both are the same file from the same package),
# and identical to the file copied out of an `ubuntu:22.04` Docker image.
CONSENSUS_MAGIC_MGC_SHA256 = "5d82f8f7172ab254d0241a7a558fe3a7a9d88cbb4bc6c8828c6bd48fd80cd228"

# libmagic searches these paths in order. We check both because some libmagic
# builds default to /usr/share/misc and some to /usr/lib/file; if either one
# drifts the wrong build could load the wrong file.
_MGC_PATHS = ("/usr/lib/file/magic.mgc", "/usr/share/misc/magic.mgc")


def _read_libmagic_runtime_version() -> int:
    """Returns the integer version reported by the loaded libmagic.so (e.g. 541)."""
    libname = ctypes.util.find_library("magic") or "libmagic.so.1"
    lib = ctypes.CDLL(libname)
    lib.magic_version.restype = ctypes.c_int
    return int(lib.magic_version())


def _sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def assert_consensus_libmagic() -> None:
    """
    Verify the runtime libmagic matches the consensus anchor.

    Logs all observed values (loud audit trail) and raises ConsensusError if
    anything drifts. Honors config.FORCE: with FORCE=True the mismatch is
    downgraded to a WARNING for operators who knowingly want to run a
    non-canonical build (e.g. a reparse-and-recheckpoint workflow).
    """
    runtime_version = _read_libmagic_runtime_version()
    logger.info("libmagic runtime version: %d (consensus anchor: %d)",
                runtime_version, CONSENSUS_LIBMAGIC_VERSION)

    mgc_hashes = {}
    for path in _MGC_PATHS:
        if os.path.exists(path):
            mgc_hashes[path] = _sha256_file(path)
            logger.info("libmagic database sha256: %s = %s", path, mgc_hashes[path])
        else:
            logger.warning("libmagic database missing at expected path: %s", path)

    problems = []
    if runtime_version != CONSENSUS_LIBMAGIC_VERSION:
        problems.append(
            f"libmagic runtime version {runtime_version} != consensus anchor "
            f"{CONSENSUS_LIBMAGIC_VERSION}"
        )
    for path, observed in mgc_hashes.items():
        if observed != CONSENSUS_MAGIC_MGC_SHA256:
            problems.append(
                f"libmagic database sha256 mismatch at {path}: "
                f"observed {observed}, expected {CONSENSUS_MAGIC_MGC_SHA256}"
            )

    if not problems:
        return

    detail = (
        "libmagic consensus drift detected — txlist_hash will diverge from "
        "CHECKPOINTS_MAINNET. Fix:\n"
        "  Docker:  rebuild from the supplied Dockerfile (vendors libmagic "
        "5.41 from ubuntu:22.04)\n"
        "  Host:    `sudo apt install libmagic1=1:5.41-3ubuntu0.1 "
        "libmagic-mgc=1:5.41-3ubuntu0.1 && sudo apt-mark hold libmagic1 "
        "libmagic-mgc`  (Ubuntu 22.04 only)\n"
        "Details:\n  - " + "\n  - ".join(problems)
    )

    if getattr(config, "FORCE", False):
        logger.warning("FORCE mode: ignoring libmagic consensus drift. %s", detail)
        return

    raise RuntimeError(detail)
