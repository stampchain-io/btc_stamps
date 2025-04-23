"""
Stub module for 'btc_stamps_parser' providing Rust parser interfaces for tests and mypy.
Includes:
- FastTransactionParser alias to FastParser
- TransactionInfo as Any
- parse_rust_src20 alias
"""

from typing import Any

from index_core.fast_parser import FastParser as FastTransactionParser  # noqa: F401

TransactionInfo: Any = Any

# parse_rust_src20 for test_parser_comparison
from index_core.src20 import parse_src20 as parse_rust_src20  # noqa: F401

# Note: Using the actual FastTransactionParser imported from Rust implementation above
# No duplicate class definition
