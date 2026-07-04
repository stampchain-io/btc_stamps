import asyncio
import os
import sys
import unittest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


class TestMajorDependencyUpdates(unittest.TestCase):
    """Test major dependency updates for compatibility."""

    def test_aiohttp_basic_functionality(self):
        """Test aiohttp basic functionality works with new version."""
        try:
            import aiohttp

            async def test_session():
                timeout = aiohttp.ClientTimeout(total=5, connect=2)
                connector = aiohttp.TCPConnector(
                    limit=10,
                    limit_per_host=5,
                    ttl_dns_cache=300,
                    use_dns_cache=True,
                    keepalive_timeout=30,
                    enable_cleanup_closed=True,
                )

                async with aiohttp.ClientSession(
                    timeout=timeout, connector=connector, headers={"Connection": "keep-alive"}
                ) as session:
                    # Test basic session creation and configuration
                    self.assertIsNotNone(session)
                    self.assertIsNotNone(session.timeout)
                    self.assertIsNotNone(session.connector)
                    return True

            # Run the async test
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(test_session())
                self.assertTrue(result)
            finally:
                loop.close()

        except ImportError:
            self.skipTest("aiohttp not available")

    def test_aiohttp_server_error_handling(self):
        """Test aiohttp server error handling (ServerDisconnectedError)."""
        try:
            import aiohttp

            # Test that the error class still exists and is importable
            self.assertTrue(hasattr(aiohttp, "ServerDisconnectedError"))
            self.assertTrue(issubclass(aiohttp.ServerDisconnectedError, Exception))

        except ImportError:
            self.skipTest("aiohttp not available")

    def test_pyzmq_basic_functionality(self):
        """Test pyzmq basic functionality works with new version."""
        try:
            import zmq

            # Test context creation
            context = zmq.Context()
            self.assertIsNotNone(context)

            # Test socket creation
            socket = context.socket(zmq.SUB)
            self.assertIsNotNone(socket)

            # Test socket options
            socket.setsockopt(zmq.RCVTIMEO, 5000)
            socket.setsockopt(zmq.LINGER, 0)
            socket.setsockopt(zmq.SUBSCRIBE, b"test")

            # Test poll functionality
            self.assertTrue(hasattr(socket, "poll"))

            # Test multipart receive (even if it times out)
            self.assertTrue(hasattr(socket, "recv_multipart"))

            # Cleanup
            socket.close()
            context.term()

        except ImportError:
            self.skipTest("zmq not available")

    def test_pyzmq_error_handling(self):
        """Test pyzmq error handling classes."""
        try:
            import zmq

            # Test that error classes still exist
            self.assertTrue(hasattr(zmq, "error"))
            self.assertTrue(hasattr(zmq.error, "ZMQError"))

            # Test specific error types used in our code
            self.assertTrue(hasattr(zmq.error, "ZMQError"))

        except ImportError:
            self.skipTest("zmq not available")

    def test_psutil_basic_functionality(self):
        """Test psutil basic functionality works with new version."""
        try:
            import psutil

            # Test Process creation (main usage in our code)
            process = psutil.Process(os.getpid())
            self.assertIsNotNone(process)

            # Test memory_percent method (used in memory_manager.py)
            memory_pct = process.memory_percent()
            self.assertIsInstance(memory_pct, float)
            self.assertGreaterEqual(memory_pct, 0.0)

            # Test that it returns reasonable values
            self.assertLess(memory_pct, 100.0)  # Should be less than 100%

        except ImportError:
            self.skipTest("psutil not available")

    def test_psutil_process_methods(self):
        """Test specific psutil Process methods used in our codebase."""
        try:
            import psutil

            process = psutil.Process(os.getpid())

            # Test methods used in memory_manager.py
            self.assertTrue(hasattr(process, "memory_percent"))

            # Test that memory_percent can be called without arguments
            memory_pct = process.memory_percent()
            self.assertIsInstance(memory_pct, (int, float))

        except ImportError:
            self.skipTest("psutil not available")

    def test_dependency_imports_in_our_modules(self):
        """Test that our modules can still import these dependencies."""
        test_cases = [
            ("index_core.fetch_utils", "aiohttp"),
            ("index_core.zmq_utils", "zmq"),
            ("index_core.memory_manager", "psutil"),
            ("index_core.parser", "psutil"),
            ("index_core.backend", "psutil"),
        ]

        for module_name, dependency in test_cases:
            with self.subTest(module=module_name, dependency=dependency):
                try:
                    # Import the module and check if dependency import works
                    __import__(module_name)
                    __import__(dependency)
                except ImportError as e:
                    self.fail(f"Failed to import {module_name} or {dependency}: {e}")

    def test_fetch_utils_aiohttp_integration(self):
        """Test that fetch_utils can work with updated aiohttp."""
        try:
            import aiohttp

            from index_core import fetch_utils

            # Test that the module imports successfully
            self.assertTrue(hasattr(fetch_utils, "fetch_xcp_async"))

            # Test that aiohttp classes used in fetch_utils are available
            self.assertTrue(hasattr(aiohttp, "ClientTimeout"))
            self.assertTrue(hasattr(aiohttp, "TCPConnector"))
            self.assertTrue(hasattr(aiohttp, "ClientSession"))

        except ImportError:
            self.skipTest("fetch_utils or aiohttp not available")

    def test_zmq_utils_pyzmq_integration(self):
        """Test that zmq_utils can work with updated pyzmq."""
        try:
            import zmq

            from index_core import zmq_utils

            # Test that the module imports successfully
            self.assertTrue(hasattr(zmq_utils, "ZMQNotifier"))

            # Test that zmq classes used in zmq_utils are available
            self.assertTrue(hasattr(zmq, "Context"))
            self.assertTrue(hasattr(zmq, "SUB"))
            self.assertTrue(hasattr(zmq, "SUBSCRIBE"))
            self.assertTrue(hasattr(zmq, "RCVTIMEO"))
            self.assertTrue(hasattr(zmq, "LINGER"))

        except ImportError:
            self.skipTest("zmq_utils or zmq not available")

    def test_memory_manager_psutil_integration(self):
        """Test that memory_manager can work with updated psutil."""
        try:
            import psutil

            from index_core import memory_manager

            # Test that the module imports successfully
            self.assertTrue(hasattr(memory_manager, "MemoryManager"))

            # Test basic MemoryManager functionality
            mm = memory_manager.MemoryManager()
            self.assertIsNotNone(mm)

            # Test memory usage method
            usage = mm.get_memory_usage()
            self.assertIsInstance(usage, float)
            self.assertGreaterEqual(usage, 0.0)
            self.assertLessEqual(usage, 1.0)

        except ImportError:
            self.skipTest("memory_manager or psutil not available")

    def test_version_compatibility(self):
        """Test that dependency versions are compatible."""
        dependencies = ["aiohttp", "zmq", "psutil"]

        for dep in dependencies:
            with self.subTest(dependency=dep):
                try:
                    module = __import__(dep)

                    # Check if version attribute exists
                    if hasattr(module, "__version__"):
                        version = module.__version__
                        self.assertIsInstance(version, str)
                        self.assertGreater(len(version), 0)
                        print(f"{dep} version: {version}")

                except ImportError:
                    self.skipTest(f"{dep} not available")


if __name__ == "__main__":
    unittest.main()
