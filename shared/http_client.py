"""Shared async HTTP client for making API calls."""

import logging

import httpx

logger = logging.getLogger(__name__)


class AsyncHTTPClient:
    """Async HTTP client with connection pooling and timeout management."""

    def __init__(
        self,
        timeout: float = 30.0,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
    ):
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def connect(self):
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                limits=httpx.Limits(
                    max_connections=self._max_connections,
                    max_keepalive_connections=self._max_keepalive_connections,
                ),
            )
            logger.info("HTTP client initialized")

    async def close(self):
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("HTTP client closed")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get the underlying HTTP client."""
        if self._client is None:
            raise RuntimeError("HTTP client not initialized. Call connect() first.")
        return self._client


# Global client instance (initialized in main)
_http_client: AsyncHTTPClient | None = None


def get_http_client() -> AsyncHTTPClient:
    """Get the global HTTP client instance."""
    global _http_client
    if _http_client is None:
        _http_client = AsyncHTTPClient()
    return _http_client


async def close_http_client():
    """Close the global HTTP client."""
    global _http_client
    if _http_client is not None:
        await _http_client.close()
        _http_client = None
