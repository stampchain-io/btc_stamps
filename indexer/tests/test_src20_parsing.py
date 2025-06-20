import logging
import os
import sys
import threading
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

# Set test environment variables BEFORE importing any indexer modules
os.environ["USE_TEST_TX_HEX"] = "1"
os.environ["TESTING"] = "1"
os.environ["USE_TEST_DB"] = "1"
os.environ["MOCK_DB"] = "1"
os.environ["CI_FIXTURE_MODE"] = "true"
os.environ["DISABLE_RUST_PARSER"] = "1"  # Disable Rust parser to avoid initialization issues

import colorlog
import pytest

logger = logging.getLogger(__name__)

# Import other modules
from index_core.async_upload import stop_upload_worker
from index_core.caching import cache_manager
from index_core.models import StampData
from index_core.src20 import parse_src20
from index_core.stamp import parse_stamp

# Import test helpers first
from tests.db_simulator import DBSimulator
from tests.fixtures.src20_variations_data import src20_variations_data
from tests.test_helpers import mock_database, setup_test_env


# Create a test-specific BlockProcessor that doesn't depend on backend_instance
class TestBlockProcessor:
    """Test version of BlockProcessor that doesn't require backend_instance."""

    def __init__(self, db):
        self.db = db
        self.valid_stamps_in_block: List = []
        self.parsed_stamps: List = []
        self.processed_src20_in_block: List = []
        self.processed_src101_in_block: List = []
        self.collection_operations = []
        self._lock = threading.Lock()


@pytest.fixture(scope="function")
def setup_environment():
    # Configure logging to show all test case details
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(log_color)s%(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        )
    )
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)  # Set to INFO to show test case details

    setup_test_env()
    db_patcher = mock_database()
    db_mock = db_patcher.start()

    # Set up cursor mock
    cursor_mock = MagicMock()
    db_mock.cursor.return_value.__enter__.return_value = cursor_mock

    # Set up default behavior for get_src20_deploy_in_db
    cursor_mock.fetchone.return_value = None  # Default to no deployment

    # Add the project root directory to the sys.path for module importing
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))

    # Initialize DB Simulator with the path to dbSimulation.json
    db_simulation_path = Path(__file__).resolve().parent / "dbSimulation.json"
    db_simulator = DBSimulator(db_simulation_path)

    # Print total number of test cases only once
    if not hasattr(setup_environment, "_printed"):
        print(f"\nTotal number of test cases: {len(src20_variations_data)}\n")
        setup_environment._printed = True

    yield db_simulator

    # Teardown starts here
    try:
        db_patcher.stop()
        # Clear cache at the end of all tests
        cache_manager.clear_all()
        # Stop the upload worker explicitly
        stop_upload_worker()
    except Exception:
        # Ignore cleanup errors to prevent logging issues
        pass


@pytest.fixture(autouse=True)
def setup_test():
    # Create a mock database connection and cursor
    db_mock = MagicMock()
    cursor_mock = MagicMock()
    db_mock.cursor.return_value.__enter__.return_value = cursor_mock

    # Set up default cursor behavior for stamp number queries
    cursor_mock.fetchone.return_value = (0,)

    # Create a mock for get_srcbackground_data
    with patch("index_core.src20.get_srcbackground_data") as mock_get_srcbackground:
        mock_get_srcbackground.return_value = ("background", 12, "#000000")
        yield

    # Clear any existing cache
    cache_manager.clear_all()


@pytest.mark.parametrize("test_case", src20_variations_data, ids=lambda x: x["description"])
def test_src20_variations(test_case, setup_environment):
    db_simulator = setup_environment
    if db_simulator is None:
        pytest.fail("db_simulator is None - setup_environment fixture failed")

    # Use TestBlockProcessor instead of the real one to avoid backend dependencies
    block_processor = TestBlockProcessor(db_simulator)

    # Clear cache before each test case to prevent state leakage
    cache_manager.clear_all()
    # Reset the block processor's state for each test case
    block_processor.parsed_stamps = []
    block_processor.valid_stamps_in_block = []
    block_processor.processed_src20_in_block = []

    logger.info(f"\nTest Case: {test_case['description']}")
    logger.info(f"Input: {test_case['src20JsonString']}")

    stamp_data_instance = StampData(
        tx_hash=test_case["tx_hash"],
        source=test_case["source"],
        destination=test_case["destination"],
        btc_amount=test_case["btc_amount"],
        fee=test_case["fee"],
        data=test_case["src20JsonString"],
        decoded_tx=test_case["decoded_tx"],
        keyburn=test_case["keyburn"],
        tx_index=test_case["tx_index"],
        block_index=test_case["block_index"],
        block_time=test_case["block_time"],
        is_op_return=test_case["is_op_return"],
        p2wsh_data=test_case["p2wsh_data"],
        prev_tx_hash=test_case.get("prev_tx_hash", ""),
        destination_nvalue=test_case.get("destination_nvalue", 0),
    )

    stamp_result, parsed_stamp, valid_stamp, prevalidated_src20 = parse_stamp(
        stamp_data=stamp_data_instance,
        db=db_simulator,
        valid_stamps_in_block=test_case["valid_stamps_in_block"],
    )
    stamp_result = False if stamp_result is None else stamp_result

    logger.info(f"Stamp Result: {'✓' if stamp_result == test_case['expectedOutcome']['stamp_success'] else '✗'}")
    logger.info(f"Expected: {test_case['expectedOutcome']['stamp_success']}, Got: {stamp_result}")

    if parsed_stamp:
        block_processor.parsed_stamps.append(parsed_stamp)
    if valid_stamp:
        block_processor.valid_stamps_in_block.append(valid_stamp)

    src20_result = False
    src20_dict = None
    if prevalidated_src20:
        src20_result, src20_dict = parse_src20(db_simulator, prevalidated_src20, block_processor.processed_src20_in_block)
        block_processor.processed_src20_in_block.append(src20_dict)

    logger.info(f"SRC20 Result: {'✓' if src20_result == test_case['expectedOutcome']['src20_success'] else '✗'}")
    logger.info(f"Expected: {test_case['expectedOutcome']['src20_success']}, Got: {src20_result}")
    logger.info(f"Message: {test_case['expectedOutcome']['message']}")
    logger.info("-" * 80)

    # Assert stamp result
    assert (
        stamp_result == test_case["expectedOutcome"]["stamp_success"]
    ), f"Failure in stamp_result test: {test_case['expectedOutcome']['message']} - Expected: {test_case['expectedOutcome']['stamp_success']}, Got: {stamp_result}"

    # Assert src20 result
    assert (
        src20_result == test_case["expectedOutcome"]["src20_success"]
    ), f"Failure in src20_result test: {test_case['expectedOutcome']['message']} - Expected: {test_case['expectedOutcome']['src20_success']}, Got: {src20_result}"

    # Assert max_val if specified
    if test_case["expectedOutcome"].get("max_val") is not None:
        assert (
            src20_dict.get("max") == test_case["expectedOutcome"]["max_val"]
        ), f"max_val mismatch - Expected: {test_case['expectedOutcome']['max_val']}, Got: {src20_dict.get('max')}"

    # Assert lim_val if specified
    if test_case["expectedOutcome"].get("lim_val") is not None:
        assert (
            src20_dict.get("lim") == test_case["expectedOutcome"]["lim_val"]
        ), f"lim_val mismatch - Expected: {test_case['expectedOutcome']['lim_val']}, Got: {src20_dict.get('lim')}"
