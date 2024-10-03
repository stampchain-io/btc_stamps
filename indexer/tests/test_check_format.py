import unittest
from decimal import Decimal as D

from index_core.src20 import check_format


class TestCheckFormat(unittest.TestCase):
    def test_bytes_input(self):
        input_bytes = b'{"p": "src-20", "op": "TRANSFER", "tick": "BTC", "amt": "10"}'
        result = check_format(input_bytes, "dummy_tx_hash", 0)
        self.assertIsNotNone(result)
        self.assertEqual(result["p"], "src-20")

    def test_string_input(self):
        input_str = '{"p": "src-20", "op": "TRANSFER", "tick": "BTC", "amt": "10"}'
        result = check_format(input_str, "dummy_tx_hash", 0)
        self.assertIsNotNone(result)
        self.assertEqual(result["p"], "src-20")

    def test_dict_input(self):
        input_dict = {"p": "src-20", "op": "TRANSFER", "tick": "BTC", "amt": D("10")}
        result = check_format(input_dict, "dummy_tx_hash", 0)
        self.assertIsNotNone(result)
        self.assertEqual(result["p"], "src-20")

    def test_invalid_json(self):
        input_str = "invalid json"
        result = check_format(input_str, "dummy_tx_hash", 0)
        self.assertIsNone(result)

    def test_invalid_protocol(self):
        input_str = '{"p": "unknown", "op": "TRANSFER", "tick": "BTC", "amt": "10"}'
        result = check_format(input_str, "dummy_tx_hash", 0)
        self.assertIsNone(result)

    def test_invalid_type(self):
        input_int = 12345
        result = check_format(input_int, "dummy_tx_hash", 0)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
