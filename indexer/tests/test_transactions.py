import os
import unittest

import index_core.backend as backend
import index_core.util as util
from index_core.blocks import get_tx_info

# from unittest.mock import patch


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
                "prev_tx_hex": "020000000001019233ed9fb1494a68d0c7778ffa2cdda08aa6e55213cf27c41284665408767a820000000000fdffffff057924000000000000160014463f7d62af8faba4e5e050ef2c9e440afbca0d001c0300000000000069512102fba6e99b686b93622a047cae3cb48bb55e77444ba05d7430b9fc11ff848e8a4021028985b58c6d811b94593bdb32ee1c7a5d732b375940b69ce5c8df28ec1f3cb5922102222222222222222222222222222222222222222222222222222222222222222253ae1c0300000000000069512102285016cd3020b3ce66133b844f89f1938fd643cbcf8ea6e4698009b004a2b901210295634d926d49f3a7b16dd11f04c83c5fcb92d789116373902f21d96fcfffda402102020202020202020202020202020202020202020202020202020202020202020253ae17d81b00000000001600142e0bc1b58910cc023459db137ae9c984fd14fe7953ff00000000000016001460f60d7b5674c52907ab7abe32b18dccf9f9a7c302483045022100b78e8daf9745830fed1d8c1fed4c0abd3b5b639390875fd92bd0f4a1d2e751b802205936ffbd7343b506b0654ecdfdb8b24f1a85ebefba0732c336659dd1db5bb8fc812102791c2a09c2ab0bfd4b36990d80c02ac52fa286f722dbe835f5ceddd3b9c356f100000000",
            },
            {  # OLGA
                "tx_hash": "dd3147b67cfbb78250fe6108704e107feb38ff1397f57456db68b9a026879de2",
                "block_index": 865000,  # actual 862152 prior to activation
                "expected_data": b'{"p":"SRC-20","op":"DEPLOY","tick":"KOLGA","max":"69000","lim":"69","dec":"0"}',
                "expected_destination": "bc1qhhv6rmxvq5mj2fc3zne2gpjqduy45urapje64m",
                "expected_source": "bc1qhhv6rmxvq5mj2fc3zne2gpjqduy45urapje64m",
                "tx_hex": "020000000001011feea2ff200345ff4d4d07fc29344334d04db796916208b4dd5e8625f65508df0300000000fdffffff052202000000000000160014bdd9a1eccc053725271114f2a406406f095a707d220200000000000022002000547374616d703a7b2270223a225352432d3230222c226f70223a224445504c23020000000000002200204f59222c227469636b223a224b4f4c4741222c226d6178223a2236393030302224020000000000002200202c226c696d223a223639222c22646563223a2230227d00000000000000000000b38c000000000000160014bdd9a1eccc053725271114f2a406406f095a707d02483045022100868f5d9673a9a101c15774729e9e7efd6f93490aecff101fd05f2f0f35756b6f0220636560965d48e53146f3be0c9be737d12aaf66726f2975bfaa138ebac350800b0121026e1d52e7b014f119b64be0d928a8bb80d81f52ac2ba56f47a034ec1041d058da00000000",
                "prev_tx_hex": "02000000000101b9d5e314bee233e334110b7ad4b96efd5a216fed9d2ddcfb5a665e5daf02bc400200000000fdffffff041503000000000000160014bdd9a1eccc053725271114f2a406406f095a707d290300000000000069512102b09e3f3f79a4c5ae89b084915e020eeed6d632b0af458e40c3a033b4273d1d452102407e8e821c1876e7999f2637394a9c7382d6403ba041585da04efce95d1563f22102020202020202020202020202020202020202020202020202020202020202020253ae290300000000000069512102f5d8b34fe068f378714da43be0e70e7d5aefa9643b1b1830f2f254a4670aabc4210302043fe99c209e5f070563261759e96c7148891c1189403fd5102d5ad512f5e82102020202020202020202020202020202020202020202020202020202020202020253ae83b7000000000000160014bdd9a1eccc053725271114f2a406406f095a707d02483045022100a41b7bb28e00cc87215c449d8f3073baf9db4ddaf61031b332429021827c180e0220528ef71bc5ed636106c669c2b0e81c0712845a70471d10c3cca0ca3de8bcca6d0121026e1d52e7b014f119b64be0d928a8bb80d81f52ac2ba56f47a034ec1041d058da00000000",
            },
        ]

    # @patch("index_core.backend.getrawtransaction")
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
