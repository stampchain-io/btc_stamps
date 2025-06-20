import logging
import os
import sys
import threading
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch
import json

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
from index_core.cache_db import cache_manager
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


@pytest.mark.parametrize("variation", src20_variations_data)
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
                mock_db.add_balance(
                    state["address"], state["tick"], state["balance"]
                )
            elif state["type"] == "deployment":
                mock_db.add_deployment(
                    state["tick"],
                    state["max"],
                    state["lim"],
                    state["dec"],
                    state["deployer"],
                )

    # Use a patch to replace the original database with the mock
    with patch("index_core.database.Database", return_value=mock_db):
        # Create a StampData object
        stamp = parse_stamp(
            tx_hash,
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
            src20_json_string,
            valid_stamps_in_block,
            p2wsh_data=p2wsh_data,
        )

        # Process the stamp
        result_message, stamp_valid, src20_valid = parse_src20(
            stamp, processed_src20_in_block, db=mock_db
        )

        # Log results for easier debugging
        logging.info(f"Result message: {result_message}")
        logging.info(f"Stamp valid: {stamp_valid}, Expected: {expected_outcome['stamp_success']}")
        logging.info(f"SRC20 valid: {src20_valid}, Expected: {expected_outcome['src20_success']}")

        # Assertions
        assert stamp_valid == expected_outcome["stamp_success"]
        assert src20_valid == expected_outcome["src20_success"]

        # Optional: Check for specific database changes if defined in the test case
        if "dbChanges" in expected_outcome:
            changes = expected_outcome["dbChanges"]
            if "balances" in changes:
                for balance_change in changes["balances"]:
                    final_balance = mock_db.get_balance(
                        balance_change["address"], balance_change["tick"]
                    )
                    assert final_balance == balance_change["amt"]
            if "deployments" in changes:
                for deploy_change in changes["deployments"]:
                    deployment = mock_db.get_deployment(deploy_change["tick"])
                    assert deployment is not None
                    assert deployment["max"] == deploy_change["max"]
                    assert deployment["lim"] == deploy_change["lim"]
