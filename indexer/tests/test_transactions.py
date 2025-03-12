import json
import os
import sys
import tempfile
import unittest

# Add the parent directory to sys.path to allow relative imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.mock_transaction import process_transactions

# Import the test helpers and mock module
from tests.test_helpers import create_mock_tx_lookup, mock_backend, setup_test_environment

# Sample transaction data
SAMPLE_TX_DATA = {
    "2c90a9ec6ec51c9c8644e932c72332cd1843b78b312f76bdebdcb17cb96f0c24": "0100000001b9c606a36b5ec4899cba9eb51fce97fbf23a1f83eabe5c0f3a628614033b7bc0010000006a4730440220398125f458a85ee8eb3afffe259ab2c423852c649a3b67186b62230493c881b4022024494de0a2dfc547d03efa2bc0e3c58cc19e483c0e4f2e5c14678dd20c6742a6012102a8cbc88f03b11c5044173ee42ec694c6c0e49906cc5a36b11d988f417248ac1dffffffff027b000000000000001976a91485a30f5244e0b8c313e92516f23a4f9dd90305bb88ac61350000000000001976a914cb4c57f8e8dbed8a0c860adcc000f2c9e3f2bdc688ac00000000",
    "a0eb969a3c89cc8616f7683ffa95fe5bf3d3d9f5b6c4b767e45cd9aa0b30b1df": "0100000001a69cbed0eec39f291d7f4ad595b100fcc79dc6aa8b37a468aabfdd850fbac03c010000006a47304402204e350a5a18a8e1975c8a4b399c66631f451e0dcf39f655f38ec6edb066c31a7c022064e050e5c7449a5c3f49a2f5cc3a293e8eed9cfe5fcc187b03347ac98f7a9db6012102a8cbc88f03b11c5044173ee42ec694c6c0e49906cc5a36b11d988f417248ac1dffffffff027b000000000000001976a91485a30f5244e0b8c313e92516f23a4f9dd90305bb88ace5a30000000000001976a914cb4c57f8e8dbed8a0c860adcc000f2c9e3f2bdc688ac00000000",
}


class TestTransactions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Set up the test environment
        setup_test_environment()

    def test_process_transactions(self):
        # Create a temporary file to store the results
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            output_file = temp_file.name

        try:
            # Create a list of transaction hashes to process
            tx_hashes = list(SAMPLE_TX_DATA.keys())

            # Use the mock_backend context manager to patch the Backend.getrawtransaction method
            with mock_backend() as mock_getrawtx:
                # Set up the mock to use our create_mock_tx_lookup function
                mock_getrawtx.side_effect = create_mock_tx_lookup(SAMPLE_TX_DATA)

                # Call the function under test
                result = process_transactions(tx_hashes, output_file=output_file)

                # Verify the results
                self.assertEqual(len(result), len(tx_hashes))

                # Verify output file was written correctly
                with open(output_file, "r") as f:
                    saved_data = json.load(f)
                    self.assertEqual(len(saved_data), len(tx_hashes))

                # Make assertions about the mock calls
                self.assertEqual(mock_getrawtx.call_count, len(tx_hashes))

        finally:
            # Clean up the temporary file
            if os.path.exists(output_file):
                os.unlink(output_file)


if __name__ == "__main__":
    unittest.main()
