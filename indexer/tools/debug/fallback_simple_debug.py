import time
from unittest import mock

from index_core.pipeline_utils import CPBlocksPipeline

# Mock the dependencies
with mock.patch("index_core.pipeline_utils.Backend") as mock_backend:
    mock_backend_instance = mock.MagicMock()
    mock_backend_instance.getblockcount.return_value = 820100
    mock_backend.return_value = mock_backend_instance

    with mock.patch("index_core.pipeline_utils.backend_instance", mock_backend_instance):
        with mock.patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get:
            with mock.patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update:
                with mock.patch("index_core.pipeline_utils.is_shutdown_requested") as mock_shutdown:
                    with mock.patch("index_core.pipeline_utils.get_fallback_state_manager") as mock_fsm:
                        mock_shutdown.return_value = False
                        mock_get.return_value = []  # No healthy nodes

                        mock_mgr = mock.MagicMock()
                        mock_mgr.is_fallback_active.return_value = False
                        mock_mgr.get_failed_blocks.return_value = set()
                        mock_mgr.get_fallback_start_block.return_value = None
                        mock_fsm.return_value = mock_mgr

                        print("Creating pipeline...")
                        pipeline = CPBlocksPipeline()

                        print("Starting pipeline...")
                        try:
                            pipeline.start(820000)
                            print("Pipeline started successfully")

                            # Wait a bit
                            time.sleep(2)

                            print(f"Fallback started at: {pipeline.fallback_started_at}")

                            # Stop the pipeline
                            print("Stopping pipeline...")
                            pipeline.stop()
                            print("Pipeline stopped")

                        except Exception as e:
                            print(f"Error: {e}")
                            import traceback

                            traceback.print_exc()
