"""
Signal handling utilities for graceful process shutdown.
"""

import logging
import os
import signal
import threading

import index_core.server as server
from index_core.node_health import register_shutdown_callback, set_shutdown_flag

logger = logging.getLogger(__name__)

# Global variables to be referenced by the signal handler
profiler = None
cp_pipeline_instance = None


def signal_handler(sig, frame):
    """
    Handle SIGINT (Ctrl+C) gracefully.
    This handler is designed to be thread-safe and idempotent.
    """
    global profiler
    global cp_pipeline_instance

    # Track how many times the handler has been called
    if not hasattr(signal_handler, "call_count"):
        signal_handler.call_count = 0
    signal_handler.call_count += 1

    # If this is the second or later call, force immediate exit
    if signal_handler.call_count >= 2:
        logger.warning("Received second interrupt, forcing immediate exit...")
        if "profiler" in globals() and profiler is not None:
            try:
                profiler.end_block_profiling()
            except Exception:
                pass
        os._exit(1)  # Use os._exit for immediate termination

    logger.info("Received interrupt signal, initiating graceful shutdown...")
    if "profiler" in globals() and profiler is not None:
        try:
            profiler.end_block_profiling()
        except Exception as e:
            logger.error(f"Error ending profiling: {e}")

    # Set both shutdown flags - this will trigger callbacks
    # in all registered components
    server.shutdown_flag.set()

    # Set node health shutdown flag - this will notify all registered callbacks
    set_shutdown_flag()

    # Create a timer that forces exit if shutdown takes too long
    def force_exit_after_timeout():
        logger.warning("Shutdown timeout reached (10 seconds), forcing exit...")
        os._exit(1)  # Use os._exit for a hard exit that bypasses Python's cleanup

    # Schedule forced exit after 10 seconds
    shutdown_timer = threading.Timer(10.0, force_exit_after_timeout)
    shutdown_timer.daemon = True  # Make timer daemon so it doesn't block process exit
    shutdown_timer.start()


def setup_signal_handler(profiler_instance=None, cp_pipeline=None):
    """
    Set up the signal handler with required resources.
    """
    global profiler, cp_pipeline_instance

    # Set global references that will be used by the handler
    profiler = profiler_instance
    cp_pipeline_instance = cp_pipeline

    # Register CP pipeline for shutdown notification via callback
    if cp_pipeline is not None:

        def cp_pipeline_shutdown():
            logger.info("CP Pipeline shutdown callback triggered")
            try:
                cp_pipeline.shutdown_flag.set()
            except Exception as e:
                logger.error(f"Error shutting down CP pipeline: {e}")

        register_shutdown_callback(cp_pipeline_shutdown)

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
