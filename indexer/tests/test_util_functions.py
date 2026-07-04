import unittest
from decimal import Decimal

from index_core.util import (
    b2h,
    base62_encode,
    calculate_file_size,
    check_contains_special,
    check_valid_base64_string,
    check_valid_bitcoin_address,
    check_valid_eth_address,
    check_valid_tx_hash,
    chunkify,
    clean_json_string,
    clean_url_for_log,
    convert_decimal_to_string,
    create_base62_hash,
    decode_unicode_escapes,
    dhash,
    dhash_string,
    escape_non_ascii_characters,
    hex_decode,
    inverse_hash,
    shash_string,
)


class TestUtilFunctions(unittest.TestCase):

    def test_calculate_file_size(self):
        """Test calculate_file_size function with various inputs."""
        # Normal case
        self.assertEqual(calculate_file_size(b"hello"), 5)
        # Empty bytes
        self.assertEqual(calculate_file_size(b""), 0)
        # None input
        self.assertEqual(calculate_file_size(None), 0)
        # Larger data
        self.assertEqual(calculate_file_size(b"x" * 1000), 1000)

    def test_chunkify(self):
        """Test chunkify function for splitting lists."""
        # Normal case
        result = chunkify([1, 2, 3, 4, 5], 2)
        self.assertEqual(result, [[1, 2], [3, 4], [5]])

        # Edge cases
        self.assertEqual(chunkify([], 2), [])
        self.assertEqual(chunkify([1], 3), [[1]])
        self.assertEqual(chunkify([1, 2, 3], 0), [[1], [2], [3]])  # n=0 becomes n=1

        # Exact division
        self.assertEqual(chunkify([1, 2, 3, 4], 2), [[1, 2], [3, 4]])

    def test_dhash_and_dhash_string(self):
        """Test double hash functions."""
        test_data = "hello world"

        # Test dhash with string
        hash_bytes = dhash(test_data)
        self.assertIsInstance(hash_bytes, bytes)
        self.assertEqual(len(hash_bytes), 32)  # SHA256 is 32 bytes

        # Test dhash with bytes
        hash_bytes2 = dhash(test_data.encode("utf-8"))
        self.assertEqual(hash_bytes, hash_bytes2)

        # Test dhash_string
        hash_string = dhash_string(test_data)
        self.assertIsInstance(hash_string, str)
        self.assertEqual(len(hash_string), 64)  # 32 bytes = 64 hex chars

        # Consistency check
        self.assertEqual(hash_string, hash_bytes.hex())

    def test_shash_string(self):
        """Test single hash string function."""
        test_data = "test data"

        # Test with string
        hash_str = shash_string(test_data)
        self.assertIsInstance(hash_str, str)
        self.assertEqual(len(hash_str), 64)  # SHA256 hex string

        # Test with bytes
        hash_str2 = shash_string(test_data.encode("utf-8"))
        self.assertEqual(hash_str, hash_str2)

    def test_clean_url_for_log(self):
        """Test URL cleaning for logging purposes."""
        # URL with credentials
        url_with_creds = "https://user:pass@example.com/path"
        cleaned = clean_url_for_log(url_with_creds)
        self.assertEqual(cleaned, "https://XXXXXXXX@example.com/path")

        # URL without credentials
        normal_url = "https://example.com/path"
        self.assertEqual(clean_url_for_log(normal_url), normal_url)

        # Different protocol
        ftp_url = "ftp://user:secret@ftp.example.com"
        cleaned_ftp = clean_url_for_log(ftp_url)
        self.assertEqual(cleaned_ftp, "ftp://XXXXXXXX@ftp.example.com")

    def test_b2h_and_inverse_hash(self):
        """Test byte-to-hex and inverse hash functions."""
        test_bytes = b"\x01\x23\x45\x67"

        # Test b2h
        hex_str = b2h(test_bytes)
        self.assertEqual(hex_str, "01234567")

        # Test inverse_hash
        test_hash = "01234567"
        inverted = inverse_hash(test_hash)
        self.assertEqual(inverted, "67452301")

        # Test with even length hex string
        even_hash = "abcdef"
        inverted_even = inverse_hash(even_hash)
        self.assertEqual(inverted_even, "efcdab")

    def test_hex_decode(self):
        """Test hex string decoding."""
        # Valid hex
        result = hex_decode("48656c6c6f")  # "Hello" in hex
        self.assertEqual(result, "Hello")

        # Invalid hex
        result = hex_decode("invalid")
        self.assertIsNone(result)

        # Empty string
        result = hex_decode("")
        self.assertEqual(result, "")

    def test_check_valid_eth_address(self):
        """Test Ethereum address validation."""
        # Valid address
        valid_eth = "0x742d35Cc6635C0532925a3b8D6E4C46f64c4ceE2"
        self.assertTrue(check_valid_eth_address(valid_eth))

        # Invalid cases
        self.assertFalse(check_valid_eth_address("invalid"))
        self.assertFalse(check_valid_eth_address("742d35Cc6635C0532925a3b8D6E4C46f64c4ceE2"))  # No 0x
        self.assertFalse(check_valid_eth_address("0x742d35Cc6635C0532925a3b8D6E4C46f64c4ceE"))  # Too short
        self.assertFalse(check_valid_eth_address("0x742d35Cc6635C0532925a3b8D6E4C46f64c4ceE22"))  # Too long
        self.assertFalse(check_valid_eth_address("0xGGGd35Cc6635C0532925a3b8D6E4C46f64c4ceE2"))  # Invalid chars

    def test_check_valid_tx_hash(self):
        """Test transaction hash validation."""
        # Valid 64-character hex string
        valid_hash = "a" * 64
        self.assertTrue(check_valid_tx_hash(valid_hash))

        # Mixed case valid hash
        valid_mixed = "A1b2C3d4" * 8  # 64 chars
        self.assertTrue(check_valid_tx_hash(valid_mixed))

        # Invalid cases
        self.assertFalse(check_valid_tx_hash("a" * 63))  # Too short
        self.assertFalse(check_valid_tx_hash("a" * 65))  # Too long
        self.assertFalse(check_valid_tx_hash("g" * 64))  # Invalid hex chars
        self.assertFalse(check_valid_tx_hash(""))  # Empty

    def test_check_contains_special(self):
        """Test special character detection."""
        # Text with special characters
        self.assertTrue(check_contains_special("hello world"))  # space
        self.assertTrue(check_contains_special("hello@world"))  # @
        self.assertTrue(check_contains_special("hello#world"))  # #
        self.assertTrue(check_contains_special("hello.world"))  # .

        # Text without special characters
        self.assertFalse(check_contains_special("helloworld"))
        self.assertFalse(check_contains_special("ABC123"))

        # Edge cases
        self.assertFalse(check_contains_special(""))  # Empty string
        self.assertTrue(check_contains_special("   "))  # Only spaces

    def test_check_valid_base64_string(self):
        """Test base64 string validation."""
        # Valid base64 strings
        self.assertTrue(check_valid_base64_string("SGVsbG8="))  # "Hello"
        self.assertTrue(check_valid_base64_string("SGVsbG8gV29ybGQ="))  # "Hello World"
        self.assertTrue(check_valid_base64_string("YWJjZA=="))  # "abcd"

        # Invalid base64 strings
        self.assertFalse(check_valid_base64_string("SGVsbG8"))  # Wrong padding
        self.assertFalse(check_valid_base64_string("SGVsbG8==="))  # Too much padding
        self.assertFalse(check_valid_base64_string("SGVs@G8="))  # Invalid character
        self.assertFalse(check_valid_base64_string(None))  # None input
        self.assertFalse(check_valid_base64_string(""))  # Empty string

    def test_base62_encode(self):
        """Test base62 encoding."""
        # Test various numbers
        self.assertEqual(base62_encode(0), "0")
        self.assertEqual(base62_encode(1), "1")
        self.assertEqual(base62_encode(61), "Z")
        self.assertEqual(base62_encode(62), "10")

        # Test larger number
        result = base62_encode(123456)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_create_base62_hash(self):
        """Test base62 hash creation."""
        # Normal case
        hash1 = create_base62_hash("test1", "test2", 15)
        self.assertEqual(len(hash1), 15)

        # Different inputs should produce different hashes
        hash2 = create_base62_hash("test1", "test3", 15)
        self.assertNotEqual(hash1, hash2)

        # Test length validation
        with self.assertRaises(ValueError):
            create_base62_hash("test1", "test2", 11)  # Too short

        with self.assertRaises(ValueError):
            create_base62_hash("test1", "test2", 21)  # Too long

        # Test default length
        hash_default = create_base62_hash("test1", "test2")
        self.assertEqual(len(hash_default), 20)

    def test_escape_and_decode_unicode(self):
        """Test unicode escaping and decoding."""
        # Test with unicode characters
        test_text = "Hello 世界"

        # Escape unicode
        escaped = escape_non_ascii_characters(test_text)
        self.assertIn("\\u", escaped)

        # Decode back
        decoded = decode_unicode_escapes(escaped)
        self.assertEqual(decoded, test_text)

        # Test with ASCII only
        ascii_text = "Hello World"
        escaped_ascii = escape_non_ascii_characters(ascii_text)
        self.assertEqual(escaped_ascii, ascii_text)

    def test_clean_json_string(self):
        """Test JSON string cleaning."""
        # Test with single quotes
        dirty_json = "{'key': 'value'}"
        cleaned = clean_json_string(dirty_json)
        self.assertEqual(cleaned, "{ key :  value }")

        # Test with null bytes (function looks for literal "\x00", not actual null bytes)
        with_nulls = "test\\x00string"
        cleaned_nulls = clean_json_string(with_nulls)
        self.assertEqual(cleaned_nulls, "teststring")

        # Test with both
        complex_dirty = "{'test': 'value\\x00here'}"
        cleaned_complex = clean_json_string(complex_dirty)
        self.assertEqual(cleaned_complex, "{ test :  valuehere }")

    def test_convert_decimal_to_string(self):
        """Test decimal to string conversion."""
        # Test with Decimal
        decimal_val = Decimal("123.456")
        result = convert_decimal_to_string(decimal_val)
        self.assertEqual(result, "123.456")

        # Test with non-Decimal should raise TypeError
        with self.assertRaises(TypeError):
            convert_decimal_to_string("not a decimal")

        with self.assertRaises(TypeError):
            convert_decimal_to_string(123.456)


if __name__ == "__main__":
    unittest.main()
