import unittest
from index_core.blocks import process_vout, get_tx_info, list_tx
import index_core.backend as backend
import index_core.util as util


class TestTransactionProcessing(unittest.TestCase):
    @classmethod
    def setUp(cls):
        cls.test_transactions = [
            {  # MSIG
                "tx_hash": "3e5960feb9bf662d922eb3f5d02577d8e741499b964a878ea0690430f596c7e3",
                "block_index": 856538,
                "expected_data": b'{"p":"src-20","op":"transfer","tick":"0","amt":0.000000000000000001}',
                "expected_destination": "bc1qw0tglrpjdnj7f2gtp39q8l0l6xxw8qpxkrqj8x",
                "expected_source": "bc1qgclh6c403746fe0q2rhje8jyptau5rgqn5am59",
            },
            {  # OLGA
                "tx_hash": "dd3147b67cfbb78250fe6108704e107feb38ff1397f57456db68b9a026879de2",
                "block_index": 865000,  # actual 862152 prior to activation
                "expected_data": b'{"p":"SRC-20","op":"DEPLOY","tick":"KOLGA","max":"69000","lim":"69","dec":"0"}',
                "expected_destination": "bc1qhhv6rmxvq5mj2fc3zne2gpjqduy45urapje64m",
                "expected_source": "bc1qhhv6rmxvq5mj2fc3zne2gpjqduy45urapje64m",
            },
        ]

    def test_process_transactions(self):
        for tx_info in self.test_transactions:
            tx_hash = tx_info["tx_hash"]
            block_index = tx_info["block_index"]
            expected_data = tx_info["expected_data"]
            expected_destination = tx_info["expected_destination"]
            expected_source = tx_info["expected_source"]

            with self.subTest(tx_hash=tx_hash):
                # Set the current block index
                util.CURRENT_BLOCK_INDEX = block_index

                # Fetch the raw transaction hex
                tx_hex = backend.getrawtransaction(tx_hash)

                # Deserialize the transaction
                ctx = backend.deserialize(tx_hex)

                # Call get_tx_info
                transaction_info = get_tx_info(tx_hex, block_index=block_index)

                # Validate data from get_tx_info
                self.assertEqual(transaction_info.data, expected_data)

                # Validate destinations
                self.assertEqual(transaction_info.destinations, expected_destination)

                # Validate source
                self.assertEqual(transaction_info.source, expected_source)


if __name__ == "__main__":
    unittest.main()
