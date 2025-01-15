import logging
from typing import Optional, Tuple

import zmq

import config

logger = logging.getLogger(__name__)


class ZMQNotifier:
    def __init__(self):
        self.context: Optional[zmq.Context] = None
        self.socket: Optional[zmq.Socket] = None
        self._is_active = False

    def check_zmq_ports(self) -> bool:
        """Check if ZMQ block notifications are available"""
        if config.QUICKNODE_ENDPOINT:
            logger.info("ZMQ not available with Quicknode - using RPC polling only")
            return False

        try:
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.SUB)

            # Set socket options for better reliability
            self.socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second receive timeout
            self.socket.setsockopt(zmq.LINGER, 0)  # Don't wait on close

            try:
                host = config.ZMQ_HOST or config.BACKEND_CONNECT
                port = config.ZMQ_BLOCK_PORT

                zmq_url = f"tcp://{host}:{port}"
                logger.debug(f"Connecting to ZMQ block port {zmq_url}")
                self.socket.connect(zmq_url)

                # Only subscribe to rawblock as that's what the node publishes
                self.socket.setsockopt(zmq.SUBSCRIBE, b"rawblock")

                logger.info(f"Successfully connected to ZMQ notifications on {zmq_url}")
                logger.debug("Subscribed to topic: rawblock")
                self._is_active = True
                return True
            except zmq.error.ZMQError as e:
                logger.warning(f"Failed to connect to ZMQ block port {port}: {e}")
                self.cleanup()
                return False

        except Exception as e:
            logger.error(f"Error checking ZMQ ports: {e}")
            self.cleanup()
            return False

    def wait_for_notification(self, timeout: int = 1000) -> Optional[Tuple[bytes, bytes, bytes]]:
        """Wait for a block notification"""
        if not self._is_active or not self.socket:
            return None

        try:
            logger.debug(f"Polling ZMQ socket for new blocks with {timeout}ms timeout...")
            events = self.socket.poll(timeout)
            logger.debug(f"ZMQ poll returned {events} events")

            if events:
                topic, body, seq = self.socket.recv_multipart()
                topic_str = topic.decode("utf-8")
                logger.info(f"Received ZMQ notification - Topic: {topic_str}, Sequence: {seq}")
                return topic, body, seq
        except zmq.error.ZMQError as e:
            logger.error(f"Error receiving ZMQ notification: {e}")
            self.cleanup()

        return None

    def cleanup(self):
        """Clean up ZMQ resources"""
        if self.socket:
            self.socket.close()
            self.socket = None
        if self.context:
            self.context.term()
            self.context = None
        self._is_active = False
