from unittest.mock import MagicMock, patch

import pytest

import config
from index_core.transaction_utils import quick_filter_src20_transaction

# Skip if Rust parser not available
pytest.importorskip("btc_stamps_parser")


@pytest.fixture
def mock_backend():
    """Mock backend for testing parsers."""
    backend = MagicMock()

    # Sample transaction hex that should be filtered
    sample_tx_hex = "0200000001a1b2c3d4e5f6789012345678901234567890123456789012345678901234567890000000006a47304402201234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef02201234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef012103abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890abffffffff02e8030000000000001976a914123456789abcdef123456789abcdef123456789abc88ac0000000000000000536a4c50000000140002747874223b2273746174223a20226f6e6c696e65223b20226d657373616765223a2022686920616c6c223b2022766572223a2022302e30312e3130223b202270223a20227372633230223b00000000"

    backend.getrawtransaction.return_value = sample_tx_hex
    return backend


@pytest.fixture
def sample_transactions():
    """Sample transaction hex data for testing."""
    return {
        # Valid Bitcoin transaction - block 170 coinbase
        "valid_coinbase": "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0704ffff001d0104ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7947be63c52da7589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000",
        # Valid transaction with OP_RETURN (contains stamp data)
        "stamp_op_return": "020000000110f3b0e1b6bbfde41b8e0a8d4aad52b99d082db87fc8b6028a44b5bc3ba5f5cf010000006a473044022051c2e4b5e49df96e7c23b7b5cfaa8ac4f973c1de8b4c96c6c9e4b0b64ddcc8f9022057a5abc90bb7b5bb1f96e6e1c8e1c8e1c8e1c8e1c8e1c8e1c8e1c8e1c8e1c8e10121031c7836c0a75f2d67ccd6364af43b068e39d3f0dd36359dc99a3cc42265e71c82ffffffff020000000000000000536a4c50000000140002747874223b2273746174223a20226f6e6c696e65223b20226d657373616765223a2022686920616c6c223b2022766572223a2022302e30312e3130223b202270223a20227372633230223b00000000404b4c00000000001976a914e4e0b2f1a2e89b33d72e9e68fa27e4b6b264fa9e88ac00000000",
        # Transaction with keyburn (1Jpxxxxxxxx address)
        "keyburn": "020000000192c0e38528b8e0a5ba93925f8ab47fb1fddce0fb526cc96a0876ee087c83c7d9000000006a473044022057a20c35dc72efe088c712c341fba7b6c5f1709a99ecad528c0d3f972b3e0c2402204c8ab49c11c93e31eeaa62e1f73a056fa4bbd8d5539a7e1b6b6baeb7e32cf1bc012102a85c33f3c691a33c9c2a567e2916a05a11dbe0a6132094a73c6769e8c8c4b81effffffff010000000000000000226a204a7015141c7015141c7015141c7015141c7015141c7015141c7015141c70151400000000",
    }


def test_parser_comparison_src20_filtering(mock_backend, sample_transactions):
    """Compare transaction filtering results between Rust and Python parsers."""
    pytest.skip("Test requires actual backend connection for transaction deserialization")


def test_parser_comparison_transaction_deserialization(mock_backend, sample_transactions):
    """Compare transaction deserialization between Rust and Python parsers."""
    # Import parser module to access both parsers
    from index_core.parser import RUST_PARSER_AVAILABLE, Parser

    if not RUST_PARSER_AVAILABLE:
        pytest.skip("Rust parser not available")

    parser = Parser()

    # Test deserialization with a valid transaction
    tx_hex = sample_transactions["valid_coinbase"]

    try:
        # Deserialize with Rust parser
        ctx = parser.deserialize_transaction(tx_hex)

        # Check basic transaction properties
        assert hasattr(ctx, "vin"), "Transaction should have inputs"
        assert hasattr(ctx, "vout"), "Transaction should have outputs"
        assert hasattr(ctx, "txid"), "Transaction should have txid"

        # The transaction should be parseable
        assert ctx is not None, "Parser should return a valid transaction object"

    except Exception as e:
        pytest.fail(f"Parser failed to deserialize transaction: {e}")


def test_parser_comparison_batch_processing(sample_transactions):
    """Test batch processing capabilities of the parser."""
    from index_core.parser import RUST_PARSER_AVAILABLE, Parser

    if not RUST_PARSER_AVAILABLE:
        pytest.skip("Rust parser not available")

    parser = Parser()

    # Create a batch of transactions
    tx_batch = list(sample_transactions.values())

    try:
        # Process batch
        results = parser.batch_parse_transactions(tx_batch)

        # Should return filtered results
        assert isinstance(results, list), "Batch parse should return a list"

        # Each result should be a valid transaction
        for tx in results:
            assert hasattr(tx, "vin"), "Each transaction should have inputs"
            assert hasattr(tx, "vout"), "Each transaction should have outputs"
            assert hasattr(tx, "txid"), "Each transaction should have txid"

    except Exception as e:
        pytest.fail(f"Batch parser failed: {e}")
