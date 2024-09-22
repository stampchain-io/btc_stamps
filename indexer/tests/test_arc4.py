import hashlib
import unittest

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4
from cryptography.hazmat.primitives.ciphers import Cipher

from src.index_core.arc4 import arc4_decrypt_chunk, get_arc4_path, init_arc4


class TestARC4(unittest.TestCase):
    def test_imports(self):
        """Test that all necessary modules can be imported."""
        try:
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.decrepit.ciphers.algorithms import ARC4
            from cryptography.hazmat.primitives.ciphers import Cipher

            self.assertTrue(True, "All modules imported successfully")
        except ImportError as e:
            self.fail(f"Import error: {e}")

    def test_arc4_with_tx_hash(self):
        # Simulate a transaction hash (32 bytes)
        tx_hash = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")

        plaintext = b"Hello, Bitcoin!"

        # Initialize ARC4 cipher with reversed tx_hash (as done in blocks.py)
        cipher = init_arc4(tx_hash[::-1])

        # Encrypt
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(plaintext) + encryptor.finalize()

        # Decrypt
        decrypted = arc4_decrypt_chunk(encrypted_data, init_arc4(tx_hash[::-1]))

        self.assertEqual(plaintext, decrypted)

    def test_arc4_with_pubkey(self):
        # Use a test Bitcoin public key (33 bytes for compressed key)
        test_pubkey = bytes.fromhex("0279BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798")

        plaintext = b"Hello, World!"

        # Hash the pubkey to get a valid key size for ARC4
        hashed_pubkey = hashlib.sha256(test_pubkey).digest()

        # Initialize ARC4 cipher with hashed pubkey
        cipher = Cipher(ARC4(hashed_pubkey), mode=None, backend=default_backend())

        # Encrypt
        encryptor = cipher.encryptor()
        encrypted_data = encryptor.update(plaintext) + encryptor.finalize()

        # Decrypt using our arc4_decrypt_chunk function
        # We use the hashed_pubkey here to avoid the key size issue
        decrypted = arc4_decrypt_chunk(encrypted_data, init_arc4(hashed_pubkey))

        self.assertEqual(plaintext, decrypted)

    def test_arc4_import_path(self):
        self.assertEqual(get_arc4_path(), "cryptography.hazmat.decrepit.ciphers.algorithms")

    def test_arc4_functionality(self):
        # This test directly uses the ARC4 algorithm to ensure it's working as expected
        key = b"test_key"
        plaintext = b"Hello, ARC4!"

        # Use ARC4 directly
        cipher = Cipher(ARC4(key), mode=None, backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(plaintext) + encryptor.finalize()

        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted) + decryptor.finalize()

        self.assertEqual(plaintext, decrypted)
        self.assertNotEqual(plaintext, encrypted)


if __name__ == "__main__":
    unittest.main()
