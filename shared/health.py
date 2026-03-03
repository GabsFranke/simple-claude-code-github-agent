"""Health check utilities for monitoring service health."""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health status information."""

    healthy: bool
    last_activity: float
    uptime: float
    processed_count: int
    error_count: int
    message: str


class HealthChecker:
    """Health checker that tracks service health and writes to a file."""

    def __init__(
        self,
        health_file: str = "/tmp/worker_health",  # nosec B108
        update_interval: int = 30,
        max_idle_time: int = 300,
    ):
        """
        Initialize health checker.

        Args:
            health_file: Path to health check file
            update_interval: How often to update health file (seconds)
            max_idle_time: Maximum time without activity before unhealthy (seconds)
        """
        self.health_file = Path(health_file)
        self.update_interval = update_interval
        self.max_idle_time = max_idle_time

        self._start_time = time.time()
        self._last_activity = time.time()
        self._processed_count = 0
        self._error_count = 0
        self._running = False
        self._task: asyncio.Task | None = None

    def record_activity(self) -> None:
        """Record successful activity."""
        self._last_activity = time.time()
        self._processed_count += 1

    def record_error(self) -> None:
        """Record error."""
        self._error_count += 1

    def get_status(self) -> HealthStatus:
        """Get current health status."""
        now = time.time()
        idle_time = now - self._last_activity
        uptime = now - self._start_time

        healthy = idle_time < self.max_idle_time

        if not healthy:
            message = f"Unhealthy: No activity for {idle_time:.0f}s"
        else:
            message = f"Healthy: Last activity {idle_time:.0f}s ago"

        return HealthStatus(
            healthy=healthy,
            last_activity=self._last_activity,
            uptime=uptime,
            processed_count=self._processed_count,
            error_count=self._error_count,
            message=message,
        )

    async def _update_loop(self) -> None:
        """Background loop to update health file."""
        while self._running:
            try:
                status = self.get_status()
                self._write_health_file(status)
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                logger.info("Health checker update loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error updating health file: {e}", exc_info=True)
                await asyncio.sleep(self.update_interval)

    def _write_health_file(self, status: HealthStatus) -> None:
        """Write health status to file."""
        try:
            # Create parent directory if needed
            self.health_file.parent.mkdir(parents=True, exist_ok=True)

            # Write health info
            content = (
                f"healthy={int(status.healthy)}\n"
                f"last_activity={status.last_activity:.0f}\n"
                f"uptime={status.uptime:.0f}\n"
                f"processed={status.processed_count}\n"
                f"errors={status.error_count}\n"
                f"message={status.message}\n"
            )

            self.health_file.write_text(content, encoding="utf-8")
            logger.debug(f"Updated health file: {status.message}")

        except OSError as e:
            logger.warning(f"Failed to write health file: {e}")

    def start(self) -> None:
        """Start health checker background task."""
        if self._running:
            logger.warning("Health checker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._update_loop())
        logger.info(
            f"Health checker started (file: {self.health_file}, "
            f"interval: {self.update_interval}s)"
        )

    async def stop(self) -> None:
        """Stop health checker background task."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Write final status
        status = self.get_status()
        self._write_health_file(status)

        logger.info("Health checker stopped")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    async def __aenter__(self):
        """Async context manager entry."""
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
