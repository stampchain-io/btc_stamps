from typing import Generator
from unittest.mock import Mock, patch

import pytest

from src.index_core.fallback_state import clear_fallback_state, load_failed_blocks, save_failed_blocks
from src.index_core.reprocessing_queue import ReprocessingQueue


@pytest.fixture
def mock_queue() -> Generator[Mock, None, None]:
    mock_instance = Mock()
    mock_instance.save_fallback_state = Mock()
    mock_instance.load_fallback_state = Mock(return_value={123: True, 456: False})
    mock_instance.clear_fallback_state = Mock()
    mock_instance.get_oldest_failed_block = Mock(return_value=123)
    with patch.object(ReprocessingQueue, "get_instance", return_value=mock_instance):
        yield mock_instance


def test_save_load_clear(mock_queue: Mock) -> None:
    test_data = {789: True}
    with patch("src.index_core.util.CURRENT_BLOCK_INDEX", 789):
        save_failed_blocks(test_data)
        # Expect string keys since save_failed_blocks converts int keys to strings for JSON
        mock_queue.save_fallback_state.assert_called_with(789, {"789": True})
        loaded = load_failed_blocks()
        assert loaded == {123: True, 456: False}
        mock_queue.load_fallback_state.assert_called_with(789)
        clear_fallback_state(789)
        mock_queue.clear_fallback_state.assert_called_with(789)


def test_recovery_flow(mock_queue: Mock) -> None:
    # Test loading fallback state
    with patch("src.index_core.util.CURRENT_BLOCK_INDEX", 789):
        loaded = load_failed_blocks()
        mock_queue.load_fallback_state.assert_called_with(789)
        assert loaded == {123: True, 456: False}  # Non-empty as mocked

    # Test clearing fallback state
    clear_fallback_state(123)
    mock_queue.clear_fallback_state.assert_called_with(123)

    # Test empty after clear
    mock_queue.load_fallback_state.return_value = {}
    with patch("src.index_core.util.CURRENT_BLOCK_INDEX", 789):
        assert not load_failed_blocks()


def test_save_error_handling(mock_queue: Mock) -> None:
    """Test that save_failed_blocks re-raises exceptions."""
    mock_queue.save_fallback_state.side_effect = Exception("Database error")

    with patch("src.index_core.util.CURRENT_BLOCK_INDEX", 789):
        with pytest.raises(Exception) as exc_info:
            save_failed_blocks({789: True})
        assert "Database error" in str(exc_info.value)
        # Expect string keys since save_failed_blocks converts int keys to strings for JSON
        mock_queue.save_fallback_state.assert_called_with(789, {"789": True})


def test_load_returns_empty_dict_when_none(mock_queue: Mock) -> None:
    """Test that load_failed_blocks returns empty dict when queue returns None."""
    mock_queue.load_fallback_state.return_value = None

    with patch("src.index_core.util.CURRENT_BLOCK_INDEX", 789):
        result = load_failed_blocks()
        assert result == {}
        mock_queue.load_fallback_state.assert_called_with(789)
