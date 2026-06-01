"""FastAPI entry point for the Scheduler service."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from shared.logging_utils import setup_logging

from .config import get_scheduler_config
from .scheduler import WorkflowScheduler

# Load configuration
config = get_scheduler_config()

# Configure logging
setup_logging(level=config.log_level)
logger = logging.getLogger(__name__)

# Initialize scheduler
workflow_scheduler = WorkflowScheduler()


async def watch_workflows_config(scheduler: WorkflowScheduler, file_path: Path):
    """Background task to watch workflows.yaml and hot-reload schedules.

    This implements config hot-reloading without external library dependencies,
    making it extremely lightweight and portable.
    """
    if not file_path.exists():
        logger.warning(f"Workflows config file not found for watching: {file_path}")
        return

    try:
        last_mtime = file_path.stat().st_mtime
        logger.info(
            f"Started config file watcher for: {file_path} (mtime: {last_mtime})"
        )
    except OSError as e:
        logger.error(f"Failed to stat config file: {e}")
        return

    while scheduler._running:
        await asyncio.sleep(5)
        try:
            if file_path.exists():
                current_mtime = file_path.stat().st_mtime
                if current_mtime != last_mtime:
                    logger.info(
                        "workflows.yaml change detected! Hot-reloading schedules..."
                    )
                    await scheduler.load_schedules()
                    last_mtime = current_mtime
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error checking workflows.yaml status: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for starting and stopping the scheduler gracefully."""
    # Start scheduler
    await workflow_scheduler.start()

    # Start config hot-reload file watcher
    workflows_path = Path(__file__).parent.parent.parent / "workflows.yaml"
    watcher_task = asyncio.create_task(
        watch_workflows_config(workflow_scheduler, workflows_path)
    )

    # Write initial healthy state to health check file
    try:
        health_path = Path(config.health_check_file)
        health_path.parent.mkdir(parents=True, exist_ok=True)
        health_path.write_text(
            "healthy=1\nservice=scheduler\nmessage=Scheduler is running\n",
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning(f"Failed to write initial health file: {e}")

    yield

    # Stop file watcher
    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass

    # Stop scheduler
    await workflow_scheduler.stop()

    # Write unhealthy/stopped state to health check file
    try:
        health_path = Path(config.health_check_file)
        if health_path.exists():
            health_path.write_text(
                "healthy=0\nservice=scheduler\nmessage=Scheduler has stopped\n",
                encoding="utf-8",
            )
    except OSError as e:
        logger.warning(f"Failed to write final health file: {e}")


app = FastAPI(title="ClaudeCodeGitHubAgent Scheduler Service", lifespan=lifespan)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"status": "ClaudeCodeGitHubAgent scheduler service is running"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    # Determine if scheduler is running
    is_running = workflow_scheduler._running
    status = "healthy" if is_running else "unhealthy"

    # Get active jobs
    jobs = []
    if is_running:
        for job in workflow_scheduler.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run_time": (
                        job.next_run_time.isoformat() if job.next_run_time else None
                    ),
                }
            )

    return {
        "status": status,
        "service": "scheduler",
        "scheduler_running": is_running,
        "active_schedules": jobs,
    }


class OneShotScheduleRequest(BaseModel):
    workflow_name: str = Field(..., description="Name of the workflow to trigger")
    repo: str = Field(..., description="Repository full name (owner/repo)")
    run_at: datetime = Field(
        ..., description="Date and time when the workflow should execute"
    )
    issue_number: int | None = Field(
        default=None, description="Optional issue or PR number"
    )
    ref: str = Field(default="main", description="Target git ref/branch")
    user: str = Field(
        default="scheduler", description="User who triggered this schedule"
    )
    user_query: str = Field(
        default="", description="Optional query instruction for the workflow"
    )


@app.post("/schedule/one-shot")
async def schedule_one_shot(request: OneShotScheduleRequest):
    """Schedule a workflow execution for a single specific time in the future."""
    from fastapi import HTTPException

    try:
        job_id = await workflow_scheduler.schedule_one_shot(
            workflow_name=request.workflow_name,
            repo=request.repo,
            run_at=request.run_at,
            issue_number=request.issue_number,
            ref=request.ref,
            user=request.user,
            user_query=request.user_query,
        )
        return {
            "status": "success",
            "message": "One-shot workflow scheduled successfully",
            "job_id": job_id,
            "run_at": request.run_at.isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to schedule one-shot workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.port)
