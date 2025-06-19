import unittest

from index_core.base64_utils import parse_base64_from_description


class TestBase64Utils(unittest.TestCase):
    """Test base64 utility functions."""

    def test_parse_base64_from_description_with_mimetype(self):
        """Test parsing base64 with mimetype from description."""
        description = "Some text before stamp:image/png;iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "image/png")
        self.assertEqual(
            base64_string, "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        )

    def test_parse_base64_from_description_without_mimetype(self):
        """Test parsing base64 without mimetype from description."""
        description = "Some text before stamp:iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "")
        self.assertEqual(
            base64_string, "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        )

    def test_parse_base64_from_description_case_insensitive(self):
        """Test that 'stamp:' detection is case insensitive."""
        description = "Text STAMP:image/png;base64data"
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "image/png")
        self.assertEqual(base64_string, "base64data")

    def test_parse_base64_from_description_no_stamp(self):
        """Test description without 'stamp:' returns None."""
        description = "This is just a regular description"
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertIsNone(base64_string)
        self.assertIsNone(mimetype)

    def test_parse_base64_from_description_none_input(self):
        """Test None input returns None."""
        base64_string, mimetype = parse_base64_from_description(None)

        self.assertIsNone(base64_string)
        self.assertIsNone(mimetype)

    def test_parse_base64_from_description_empty_base64(self):
        """Test empty base64 data returns None."""
        description = "stamp:image/png;"
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "image/png")
        self.assertIsNone(base64_string)

    def test_parse_base64_from_description_short_base64(self):
        """Test single character base64 returns None."""
        description = "stamp:image/png;a"
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "image/png")
        self.assertIsNone(base64_string)

    def test_parse_base64_from_description_whitespace_handling(self):
        """Test whitespace is properly stripped."""
        description = "stamp:  image/png  ;  base64data  "
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "image/png")
        self.assertEqual(base64_string, "base64data")

    def test_parse_base64_from_description_long_mimetype(self):
        """Test mimetype longer than 255 chars is truncated."""
        long_mimetype = "a" * 300
        description = f"stamp:{long_mimetype};base64data"
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "")  # Should be empty when > 255 chars
        self.assertEqual(base64_string, "base64data")

    def test_parse_base64_from_description_multiple_semicolons(self):
        """Test only first semicolon is used as separator."""
        description = "stamp:image/png;base64;data;here"
        base64_string, mimetype = parse_base64_from_description(description)

        self.assertEqual(mimetype, "image/png")
        self.assertEqual(base64_string, "base64;data;here")


if __name__ == "__main__":
    unittest.main()
