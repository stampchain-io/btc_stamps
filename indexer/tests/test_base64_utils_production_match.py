import unittest

from src.index_core.base64_utils import parse_base64_from_description


class TestBase64UtilsProductionMatch(unittest.TestCase):
    """Test cases to ensure base64_utils matches production behavior exactly"""

    def test_empty_stamp_description(self):
        """Test that empty STAMP: descriptions return None (production behavior)"""
        result = parse_base64_from_description("STAMP:")
        self.assertEqual(result, (None, ""))

        result = parse_base64_from_description("STAMP: ")
        self.assertEqual(result, (None, ""))

    def test_file_stamp_pattern(self):
        """Test that FILE:stamp: patterns work correctly (production behavior)"""
        result = parse_base64_from_description("FILE:stamp:IS-OLGA.html")
        self.assertEqual(result, ("IS-OLGA.html", ""))

        # This was being excluded by stamp:721 check - now works like production
        result = parse_base64_from_description("FILE:stamp:721|c:A12345678901234567890")
        self.assertEqual(result, ("721|c:A12345678901234567890", ""))

    def test_stamp_721_patterns_processed_normally(self):
        """Test that stamp:721 patterns are processed normally (production behavior)"""
        # In production, these are processed normally, not excluded
        result = parse_base64_from_description("stamp:721")
        self.assertEqual(result, ("721", ""))  # "721" has 3 chars, passes length check

        result = parse_base64_from_description("stamp:721|c:A12345")
        self.assertEqual(result, ("721|c:A12345", ""))  # Processed normally

    def test_normal_stamp_data(self):
        """Test that normal stamp data still works"""
        result = parse_base64_from_description("STAMP:image/png;base64data")
        self.assertEqual(result, ("base64data", "image/png"))

        result = parse_base64_from_description("stamp:text/plain;hello world")
        self.assertEqual(result, ("hello world", "text/plain"))

    def test_stamp_with_single_character(self):
        """Test single character stamps are excluded (production behavior)"""
        result = parse_base64_from_description("STAMP:a")
        self.assertEqual(result, (None, ""))

    def test_case_insensitive_search(self):
        """Test case insensitive stamp finding"""
        result = parse_base64_from_description("This has a STAMP:data in it")
        self.assertEqual(result, ("data in it", ""))

        result = parse_base64_from_description("FILE:Stamp:mydata")
        self.assertEqual(result, ("mydata", ""))

    def test_missing_stamps_scenarios(self):
        """Test specific scenarios from the missing stamps"""
        # These are the patterns that were being excluded but exist in production

        # FILE:stamp:IS-OLGA.html
        result = parse_base64_from_description("FILE:stamp:IS-OLGA.html")
        self.assertEqual(result, ("IS-OLGA.html", ""))

        # FILE:stamp:721|c:CPID
        result = parse_base64_from_description("FILE:stamp:721|c:A12345678901234567890")
        self.assertEqual(result, ("721|c:A12345678901234567890", ""))

        # Empty STAMP: (these will still be excluded due to length check)
        result = parse_base64_from_description("STAMP:")
        self.assertEqual(result, (None, ""))


if __name__ == "__main__":
    unittest.main()
