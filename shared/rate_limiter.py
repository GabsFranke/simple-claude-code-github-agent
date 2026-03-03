"""Rate limiting utilities for API calls."""

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(
        self,
        max_requests: int,
        time_window: float,
        name: str = "rate_limiter",
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum number of requests allowed in time window
            time_window: Time window in seconds
            name: Name for logging purposes
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.name = name
        self.requests: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire permission to make a request.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)

        Returns:
            True if acquired, False if timeout

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        start_time = time.monotonic()

        async with self._lock:
            while True:
                now = time.monotonic()

                # Remove expired requests
                while self.requests and self.requests[0] <= now - self.time_window:
                    self.requests.popleft()

                # Check if we can proceed
                if len(self.requests) < self.max_requests:
                    self.requests.append(now)
                    logger.debug(
                        f"{self.name}: Request acquired "
                        f"({len(self.requests)}/{self.max_requests})"
                    )
                    return True

                # Check timeout
                if timeout is not None:
                    elapsed = now - start_time
                    if elapsed >= timeout:
                        logger.warning(f"{self.name}: Rate limit timeout exceeded")
                        raise TimeoutError(f"Rate limit timeout after {timeout}s")

                # Calculate wait time
                oldest_request = self.requests[0]
                wait_time = (oldest_request + self.time_window) - now

                logger.debug(
                    f"{self.name}: Rate limit reached, waiting {wait_time:.2f}s"
                )

                # Release lock while waiting
                self._lock.release()
                try:
                    await asyncio.sleep(wait_time)
                finally:
                    await self._lock.acquire()


class MultiRateLimiter:
    """Manages multiple rate limiters for different services."""

    def __init__(self):
        self._limiters: dict[str, RateLimiter] = {}

    def add_limiter(
        self,
        name: str,
        max_requests: int,
        time_window: float,
    ) -> RateLimiter:
        """Add a rate limiter for a service."""
        limiter = RateLimiter(max_requests, time_window, name)
        self._limiters[name] = limiter
        logger.info(
            f"Added rate limiter '{name}': {max_requests} requests per {time_window}s"
        )
        return limiter

    def get_limiter(self, name: str) -> RateLimiter | None:
        """Get a rate limiter by name."""
        return self._limiters.get(name)

    async def acquire(self, name: str, timeout: float | None = None) -> bool:
        """Acquire permission from a named rate limiter."""
        limiter = self.get_limiter(name)
        if limiter is None:
            logger.warning(f"Rate limiter '{name}' not found, allowing request")
            return True
        return await limiter.acquire(timeout)
