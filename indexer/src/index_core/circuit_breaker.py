"""
Circuit breaker pattern implementation for handling endpoint failures gracefully.
"""

import logging
import time
from enum import Enum
from typing import Dict

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures when endpoints are down.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests are rejected immediately
    - HALF_OPEN: Testing if the service has recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_requests: int = 3,
    ):
        """
        Initialize the circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            recovery_timeout: Seconds to wait before trying again (half-open state)
            half_open_requests: Number of requests to try in half-open state
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_count = 0
        self.consecutive_successes = 0

    def record_success(self):
        """Record a successful request."""
        if self.state == CircuitState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= self.half_open_requests:
                logger.info("Circuit breaker closing after successful recovery")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.consecutive_successes = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        """Record a failed request."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.consecutive_successes = 0

        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Circuit breaker opening after {self.failure_count} consecutive failures")
                self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker reopening after failure in half-open state")
            self.state = CircuitState.OPEN
            self.half_open_count = 0

    def can_proceed(self) -> bool:
        """Check if a request can proceed."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time and time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info("Circuit breaker entering half-open state for testing")
                self.state = CircuitState.HALF_OPEN
                self.half_open_count = 0
                self.consecutive_successes = 0
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_count < self.half_open_requests:
                self.half_open_count += 1
                return True
            return False

        return False

    def get_state(self) -> str:
        """Get current circuit state."""
        return self.state.value


class EndpointCircuitBreakers:
    """Manages circuit breakers for multiple endpoints."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

    def get_breaker(self, endpoint: str) -> CircuitBreaker:
        """Get or create a circuit breaker for an endpoint."""
        if endpoint not in self.breakers:
            self.breakers[endpoint] = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                recovery_timeout=self.recovery_timeout,
            )
        return self.breakers[endpoint]

    def can_proceed(self, endpoint: str) -> bool:
        """Check if requests to an endpoint can proceed."""
        breaker = self.get_breaker(endpoint)
        return breaker.can_proceed()

    def record_success(self, endpoint: str):
        """Record a successful request to an endpoint."""
        breaker = self.get_breaker(endpoint)
        breaker.record_success()

    def record_failure(self, endpoint: str):
        """Record a failed request to an endpoint."""
        breaker = self.get_breaker(endpoint)
        breaker.record_failure()

    def get_state(self, endpoint: str) -> str:
        """Get the state of a specific endpoint's circuit breaker."""
        breaker = self.get_breaker(endpoint)
        return breaker.get_state()

    def get_all_states(self) -> Dict[str, str]:
        """Get states of all circuit breakers."""
        return {endpoint: breaker.get_state() for endpoint, breaker in self.breakers.items()}


# Global instance for the application
endpoint_circuit_breakers = EndpointCircuitBreakers()
