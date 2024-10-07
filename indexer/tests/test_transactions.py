import os
import unittest

import index_core.backend as backend
import index_core.util as util
from index_core.blocks import get_tx_info


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
                "tx_hex": "020000000001012a9dea51a4f9a67fddb042aa39891a369d23684d8739f71d2c738280523fa6620000000000ffffffff03711200000000000016001473d68f8c326ce5e4a90b0c4a03fdffd18ce380261403000000000000695121029d42850b5c9e8c9cdb02bff2569f2653156de412344c97fb21b884732cf67fa321022d1cb9efb4bb592bd337319db73d07053c241d2861763718984fb84be47fc4902103333333333333333333333333333333333333333333333333333333333333333353ae1403000000000000695121022add53fad58aa8f4dbc6c4409deeb06204a40eb878f18ff3798d35ba7403f1102102f868ef2a23f22ae289b633e14458868b27ffc95bc990cf198258bc748b487c9d2103333333333333333333333333333333333333333333333333333333333333333353ae02483045022100ad5c7f1ecafb8e6482e5f85711631d215ad21a19370e4e5d2713d2140ba456d502206fa7138023291490fb33df514fc888c08e2b19a053b42750f29d69ceaa618af60121037a468410ad2831308cff6561f92bda494e6a5e264de308b1e853807f866e9bb300000000",
            },
            {  # OLGA
                "tx_hash": "dd3147b67cfbb78250fe6108704e107feb38ff1397f57456db68b9a026879de2",
                "block_index": 865000,  # actual 862152 prior to activation
                "expected_data": b'{"p":"SRC-20","op":"DEPLOY","tick":"KOLGA","max":"69000","lim":"69","dec":"0"}',
                "expected_destination": "bc1qhhv6rmxvq5mj2fc3zne2gpjqduy45urapje64m",
                "expected_source": "bc1qhhv6rmxvq5mj2fc3zne2gpjqduy45urapje64m",
                "tx_hex": "020000000001011feea2ff200345ff4d4d07fc29344334d04db796916208b4dd5e8625f65508df0300000000fdffffff052202000000000000160014bdd9a1eccc053725271114f2a406406f095a707d220200000000000022002000547374616d703a7b2270223a225352432d3230222c226f70223a224445504c23020000000000002200204f59222c227469636b223a224b4f4c4741222c226d6178223a2236393030302224020000000000002200202c226c696d223a223639222c22646563223a2230227d00000000000000000000b38c000000000000160014bdd9a1eccc053725271114f2a406406f095a707d02483045022100868f5d9673a9a101c15774729e9e7efd6f93490aecff101fd05f2f0f35756b6f0220636560965d48e53146f3be0c9be737d12aaf66726f2975bfaa138ebac350800b0121026e1d52e7b014f119b64be0d928a8bb80d81f52ac2ba56f47a034ec1041d058da00000000",
            },
        ]

    def test_process_transactions(self):
        use_test_tx_hex = os.environ.get("USE_TEST_TX_HEX", "0") == "1"

        for tx_info in self.test_transactions:
            tx_hash = tx_info["tx_hash"]
            block_index = tx_info["block_index"]
            expected_data = tx_info["expected_data"]
            expected_destination = tx_info["expected_destination"]
            expected_source = tx_info["expected_source"]
            stored_tx_hex = tx_info["tx_hex"]

            with self.subTest(tx_hash=tx_hash):
                # Set the current block index
                util.CURRENT_BLOCK_INDEX = block_index

                if use_test_tx_hex:
                    tx_hex = stored_tx_hex
                else:
                    try:
                        fetched_tx_hex = backend.getrawtransaction(tx_hash)
                        tx_hex = fetched_tx_hex
                        self.assertEqual(
                            fetched_tx_hex,
                            stored_tx_hex,
                            msg=f"Fetched tx_hex does not match stored tx_hex for tx {tx_hash}",
                        )
                    except Exception as e:
                        # Backend.getrawtransaction failed, use stored tx_hex
                        print(f"Failed to fetch tx_hex for tx {tx_hash} via backend.getrawtransaction: {e}")
                        tx_hex = stored_tx_hex

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
