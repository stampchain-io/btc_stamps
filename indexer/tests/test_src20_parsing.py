import json
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
os.environ["ENABLE_SENTRY"] = "0"
os.environ["ENABLE_MEMO"] = "1"
os.environ["IGNORE_DB_VERSION_CHECK"] = "1"

import colorlog
import pytest

logger = logging.getLogger(__name__)

# Import other modules
from index_core.async_upload import stop_upload_worker
from index_core.caching import cache_manager
from index_core.src20 import parse_src20
from index_core.stamp import parse_stamp

# Import test helpers first
from tests.db_simulator import DBSimulator
from tests.test_helpers import mock_database, setup_test_env


# Load test data from JSON file
def load_test_data():
    # Correctly resolve the path to the fixture file
    # The test is run from the `indexer` directory
    fixture_path = Path(__file__).parent / "fixtures" / "src20_variations_data.json"
    with open(fixture_path, "r") as f:
        return json.load(f)


src20_variations_data = load_test_data()


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


@pytest.mark.parametrize("variation", src20_variations_data, ids=lambda x: x["description"])
def test_src20_variations(variation, setup_environment):
    # This test is designed to run in the 'indexer' directory
    # Set the working directory to 'indexer' if it's not already
    if "indexer" not in os.getcwd():
        os.chdir("indexer")

    # Deconstruct variation data
    (
        description,
        src20_json_string,
        expected_outcome,
        source,
        destination,
        btc_amount,
        fee,
        decoded_tx,
        keyburn,
        tx_index,
        block_index,
        block_time,
        is_op_return,
        valid_stamps_in_block,
        processed_src20_in_block,
        p2wsh_data,
        tx_hash,
    ) = (
        variation["description"],
        variation["src20JsonString"],
        variation["expectedOutcome"],
        variation["source"],
        variation["destination"],
        variation["btc_amount"],
        variation["fee"],
        variation["decoded_tx"],
        variation["keyburn"],
        variation["tx_index"],
        variation["block_index"],
        variation["block_time"],
        variation["is_op_return"],
        variation["valid_stamps_in_block"],
        variation["processed_src20_in_block"],
        variation.get("p2wsh_data"),  # Use .get for optional fields
        variation["tx_hash"],
    )

    logging.info(f"Testing variation: {description}")
    logging.debug(f"Input JSON: {src20_json_string}")

    # Mock the database interaction
    mock_db = mock_database()

    # Prepare initial state if necessary
    if "initial_db_state" in variation:
        for state in variation["initial_db_state"]:
            if state["type"] == "balance":
                mock_db.add_balance(state["address"], state["tick"], state["balance"])
            elif state["type"] == "deployment":
                mock_db.add_deployment(
                    state["tick"],
                    state["max"],
                    state["lim"],
                    state["dec"],
                    state["deployer"],
                )

    # Use the DBSimulator from setup_environment
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

    # Create StampData instance
    from index_core.models import StampData

    stamp_data_instance = StampData(
        tx_hash=tx_hash,
        source=source,
        destination=destination,
        btc_amount=btc_amount,
        fee=fee,
        data=src20_json_string,
        decoded_tx=decoded_tx,
        keyburn=keyburn,
        tx_index=tx_index,
        block_index=block_index,
        block_time=block_time,
        is_op_return=is_op_return,
        p2wsh_data=p2wsh_data,
        prev_tx_hash=variation.get("prev_tx_hash", ""),
        destination_nvalue=variation.get("destination_nvalue", 0),
    )

    stamp_result, parsed_stamp, valid_stamp, prevalidated_src20 = parse_stamp(
        stamp_data=stamp_data_instance,
        db=db_simulator,
        valid_stamps_in_block=valid_stamps_in_block,
    )
    stamp_result = False if stamp_result is None else stamp_result

    if parsed_stamp:
        block_processor.parsed_stamps.append(parsed_stamp)
    if valid_stamp:
        block_processor.valid_stamps_in_block.append(valid_stamp)

    src20_result = False
    src20_dict = None
    if prevalidated_src20:
        src20_result, src20_dict = parse_src20(db_simulator, prevalidated_src20, block_processor.processed_src20_in_block)
        block_processor.processed_src20_in_block.append(src20_dict)

    stamp_valid = stamp_result
    src20_valid = src20_result
    result_message = expected_outcome.get("message", "Test completed")

    # Log results for easier debugging
    logging.info(f"Result message: {result_message}")
    logging.info(f"Stamp valid: {stamp_valid}, Expected: {expected_outcome['stamp_success']}")
    logging.info(f"SRC20 valid: {src20_valid}, Expected: {expected_outcome['src20_success']}")

    # Assertions
    assert stamp_valid == expected_outcome["stamp_success"]
    assert src20_valid == expected_outcome["src20_success"]

    # Optional: Check for specific database changes if defined in the test case
    # Note: This functionality would require full database state tracking which is not
    # implemented in the current DBSimulator. The main validation happens through
    # stamp_success and src20_success checks above.
