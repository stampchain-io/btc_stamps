import time
from unittest import mock

from index_core.pipeline_utils import CPBlocksPipeline
from index_core.reprocessing_queue import ReprocessingQueue

# Mock the dependencies
with mock.patch("index_core.pipeline_utils.Backend") as mock_backend:
    mock_backend_instance = mock.MagicMock()
    mock_backend_instance.getblockcount.return_value = 820100
    mock_backend.return_value = mock_backend_instance

    with mock.patch("index_core.pipeline_utils.backend_instance", mock_backend_instance):
        with mock.patch("index_core.pipeline_utils.get_healthy_nodes") as mock_get:
            with mock.patch("index_core.pipeline_utils.update_healthy_nodes") as mock_update:
                with mock.patch("index_core.pipeline_utils.is_shutdown_requested") as mock_shutdown:
                    # Mock ReprocessingQueue for fallback state
                    with mock.patch.object(ReprocessingQueue, "get_instance") as mock_queue:
                        mock_shutdown.return_value = False
                        mock_get.return_value = []  # No healthy nodes

                        mock_queue_instance = mock.MagicMock()
                        mock_queue_instance.get_oldest_failed_block.return_value = None
                        mock_queue_instance.load_fallback_state.return_value = {}
                        mock_queue.return_value = mock_queue_instance

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
