#!/usr/bin/env python
"""
Test the shutdown callback system.

This test verifies that the shutdown callback mechanism works correctly,
including proper notification of all registered components and handling
of late registrations.
"""

import logging
import signal
import sys
import time
import pytest

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("test_shutdown")

# Add src directory to path if needed
sys.path.append("indexer/src")

# Import our modules
from index_core.node_health import (
    register_shutdown_callback, 
    unregister_shutdown_callback, 
    set_shutdown_flag,
    clear_shutdown_flag,
    is_shutdown_requested
)


class TestShutdownCallbacks:
    """Test suite for shutdown callback mechanism."""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup before each test and cleanup after."""
        # Make sure we start with a clean state
        clear_shutdown_flag()
        yield
        # Clean up after test
        clear_shutdown_flag()
    
    def test_basic_callbacks(self):
        """Test that registered callbacks are properly notified."""
        # Track which components received the shutdown signal
        component_status = {
            "component1": False,
            "component2": False,
            "component3": False,
        }
        
        # Define component callbacks
        def component1_shutdown():
            logger.info("Component 1 received shutdown signal")
            component_status["component1"] = True
            
        def component2_shutdown():
            logger.info("Component 2 received shutdown signal")
            component_status["component2"] = True
            
        def component3_shutdown():
            logger.info("Component 3 received shutdown signal")
            component_status["component3"] = True
        
        # Register callbacks
        register_shutdown_callback(component1_shutdown)
        register_shutdown_callback(component2_shutdown)
        register_shutdown_callback(component3_shutdown)
        
        # Trigger shutdown
        set_shutdown_flag()
        
        # Verify all components were notified
        assert component_status["component1"] is True
        assert component_status["component2"] is True
        assert component_status["component3"] is True
    
    def test_late_registration(self):
        """Test that late registrations still receive callbacks if shutdown is already in progress."""
        # Set up test
        late_component_called = False
        
        def late_component_shutdown():
            nonlocal late_component_called
            logger.info("Late component received shutdown signal")
            late_component_called = True
        
        # Trigger shutdown first
        set_shutdown_flag()
        
        # Then register a component after shutdown is already in progress
        register_shutdown_callback(late_component_shutdown)
        
        # The callback should be executed immediately during registration
        assert late_component_called is True
    
    def test_unregister_callback(self):
        """Test that unregistered callbacks don't receive notifications."""
        # Set up test
        component1_called = False
        component2_called = False
        
        def component1_shutdown():
            nonlocal component1_called
            component1_called = True
            
        def component2_shutdown():
            nonlocal component2_called
            component2_called = True
        
        # Register both callbacks
        register_shutdown_callback(component1_shutdown)
        register_shutdown_callback(component2_shutdown)
        
        # Then unregister one of them
        unregister_shutdown_callback(component2_shutdown)
        
        # Trigger shutdown
        set_shutdown_flag()
        
        # Check that only the registered callback was called
        assert component1_called is True
        assert component2_called is False


if __name__ == "__main__":
    # This allows running the test directly, not just with pytest
    pytest.main(["-xvs", __file__]) 