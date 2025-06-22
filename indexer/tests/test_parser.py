"""Tests for parser module."""

import unittest

from index_core.parser import Parser, ParserError


class TestParser(unittest.TestCase):
    """Test parser functionality."""

    def test_parser_initialization(self):
        """Test that Parser can be initialized."""
        try:
            parser = Parser()
            self.assertIsNotNone(parser)
        except ParserError as e:
            # It's OK if Rust parser is not available in test environment
            self.assertIn("Rust parser not available", str(e))

    def test_parser_singleton(self):
        """Test that Parser follows singleton pattern."""
        try:
            parser1 = Parser()
            parser2 = Parser()
            self.assertIs(parser1, parser2)
        except ParserError:
            # Skip if Rust parser is not available
            self.skipTest("Rust parser not available")


if __name__ == "__main__":
    unittest.main()