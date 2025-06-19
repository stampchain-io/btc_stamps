"""
Test the fix for the "'list' object has no attribute 'add'" error in fallback state management.

This test verifies that:
1. When failed_cp_blocks is loaded as a list from JSON, it gets converted to a set
2. The add_failed_block method works correctly even when the state contains a list
3. All fallback state methods handle list-to-set conversion properly
"""

import json
import os
import tempfile
import unittest

from index_core.fallback_state import FallbackStateManager


class TestListToSetFix(unittest.TestCase):
    """Test the fix for list/set conversion issues in fallback state."""

    def setUp(self):
        """Set up test environment with a temporary state file."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "test_fallback_state.json")

    def tearDown(self):
        """Clean up test files."""
        if os.path.exists(self.state_file):
            os.remove(self.state_file)
        os.rmdir(self.temp_dir)

    def test_list_to_set_conversion_on_load(self):
        """Test that a list in the JSON state gets converted to a set on load."""
        # Create a state file with failed_cp_blocks as a list (simulating old format)
        state_data = {
            "fallback_active": True,
            "fallback_started_at": 900000,
            "failed_cp_blocks": [900001, 900002, 900003],  # This is a list!
            "last_updated": 1234567890,
            "version": "1.0",
        }

        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

        # Load the state manager
        manager = FallbackStateManager(self.state_file)

        # Verify that failed_cp_blocks was converted to a set internally
        self.assertIsInstance(manager.state["failed_cp_blocks"], set)
        self.assertEqual(manager.state["failed_cp_blocks"], {900001, 900002, 900003})

        # Verify that get_failed_blocks returns the correct set
        failed_blocks = manager.get_failed_blocks()
        self.assertIsInstance(failed_blocks, set)
        self.assertEqual(failed_blocks, {900001, 900002, 900003})

    def test_add_failed_block_with_list_state(self):
        """Test that add_failed_block works even when the state contains a list."""
        # Create a state file with failed_cp_blocks as a list
        state_data = {
            "fallback_active": True,
            "fallback_started_at": 900000,
            "failed_cp_blocks": [900001, 900002],  # This is a list!
            "last_updated": 1234567890,
            "version": "1.0",
        }

        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

        # Load the state manager but manually revert to list to simulate the bug
        manager = FallbackStateManager(self.state_file)
        manager.state["failed_cp_blocks"] = [900001, 900002]  # Force it back to a list

        # This should not raise "'list' object has no attribute 'add'" error
        try:
            manager.add_failed_block(900003)
        except AttributeError as e:
            if "'list' object has no attribute 'add'" in str(e):
                self.fail("add_failed_block failed with list conversion error")
            else:
                raise  # Re-raise if it's a different AttributeError

        # Verify the state was converted to a set and the block was added
        self.assertIsInstance(manager.state["failed_cp_blocks"], set)
        self.assertEqual(manager.state["failed_cp_blocks"], {900001, 900002, 900003})

    def test_start_fallback_mode_with_existing_list(self):
        """Test that start_fallback_mode handles existing list state properly."""
        # Create a state file with failed_cp_blocks as a list
        state_data = {
            "fallback_active": False,
            "fallback_started_at": None,
            "failed_cp_blocks": [900001, 900002],  # This is a list!
            "last_updated": 1234567890,
            "version": "1.0",
        }

        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

        # Load the state manager but manually revert to list
        manager = FallbackStateManager(self.state_file)
        manager.state["failed_cp_blocks"] = [900001, 900002]  # Force it back to a list

        # This should not raise an error and should convert the list to set
        manager.start_fallback_mode(900005)

        # Verify the state was converted to a set
        self.assertIsInstance(manager.state["failed_cp_blocks"], set)
        self.assertEqual(manager.state["failed_cp_blocks"], {900001, 900002})
        self.assertTrue(manager.state["fallback_active"])
        self.assertEqual(manager.state["fallback_started_at"], 900005)

    def test_get_failed_blocks_updates_state(self):
        """Test that get_failed_blocks permanently converts list to set in state."""
        # Create a state file with failed_cp_blocks as a list
        state_data = {
            "fallback_active": True,
            "fallback_started_at": 900000,
            "failed_cp_blocks": [900001, 900002, 900003],  # This is a list!
            "last_updated": 1234567890,
            "version": "1.0",
        }

        with open(self.state_file, "w") as f:
            json.dump(state_data, f)

        # Load the state manager but manually revert to list to test conversion
        manager = FallbackStateManager(self.state_file)
        manager.state["failed_cp_blocks"] = [900001, 900002, 900003]  # Force it back to a list

        # Verify it's currently a list
        self.assertIsInstance(manager.state["failed_cp_blocks"], list)

        # Call get_failed_blocks - this should convert the state to a set
        failed_blocks = manager.get_failed_blocks()

        # Verify the state was permanently updated to use a set
        self.assertIsInstance(manager.state["failed_cp_blocks"], set)
        self.assertEqual(manager.state["failed_cp_blocks"], {900001, 900002, 900003})
        self.assertEqual(failed_blocks, {900001, 900002, 900003})

        # Subsequent calls to add_failed_block should now work without issues
        manager.add_failed_block(900004)
        self.assertEqual(manager.state["failed_cp_blocks"], {900001, 900002, 900003, 900004})

    def test_roundtrip_save_load_preserves_functionality(self):
        """Test that saving and loading state preserves set functionality."""
        manager = FallbackStateManager(self.state_file)

        # Start fallback mode and add some blocks
        manager.start_fallback_mode(900000)
        manager.add_failed_block(900001)
        manager.add_failed_block(900002)

        # Verify state is correct
        self.assertEqual(manager.get_failed_blocks(), {900001, 900002})

        # Create a new manager instance (simulating restart)
        manager2 = FallbackStateManager(self.state_file)

        # Verify the loaded state is still functional
        self.assertEqual(manager2.get_failed_blocks(), {900001, 900002})

        # Add another block with the new manager
        manager2.add_failed_block(900003)
        self.assertEqual(manager2.get_failed_blocks(), {900001, 900002, 900003})

        # Verify the state is still a set internally
        self.assertIsInstance(manager2.state["failed_cp_blocks"], set)

    def test_empty_state_initialization(self):
        """Test that initializing with no existing state file works correctly."""
        manager = FallbackStateManager(self.state_file)

        # Verify initial state
        self.assertFalse(manager.is_fallback_active())
        self.assertEqual(manager.get_failed_blocks(), set())
        self.assertIsInstance(manager.state["failed_cp_blocks"], set)

        # Add blocks and verify functionality
        manager.start_fallback_mode(900000)
        manager.add_failed_block(900001)

        self.assertTrue(manager.is_fallback_active())
        self.assertEqual(manager.get_failed_blocks(), {900001})


if __name__ == "__main__":
    unittest.main()
