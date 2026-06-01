"""Core scheduler implementation using APScheduler."""

import datetime
import logging

import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import]

from shared import get_queue
from shared.github_auth import GitHubAuthService
from workflows import WorkflowEngine

from .config import get_scheduler_config

logger = logging.getLogger(__name__)


class WorkflowScheduler:
    """Manages scheduling and triggering of time-based workflows."""

    def __init__(self):
        self.config = get_scheduler_config()
        self.scheduler = AsyncIOScheduler()
        self.workflow_engine = WorkflowEngine(build_routing=False)
        self.queue = get_queue()
        self.redis_client: redis.Redis | None = None
        self._running = False

    async def start(self) -> None:
        """Start the scheduler service."""
        if self._running:
            logger.warning("Scheduler is already running")
            return

        logger.info("Starting workflow scheduler...")

        # Initialize Redis client for locking and status tracking
        try:
            self.redis_client = redis.from_url(
                self.config.queue.redis_url,
                password=self.config.queue.redis_password,
                decode_responses=True,
            )
            await self.redis_client.ping()  # type: ignore[misc]
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        self._running = True
        self.scheduler.start()
        await self.load_schedules()

    async def stop(self) -> None:
        """Stop the scheduler service."""
        if not self._running:
            return

        logger.info("Stopping workflow scheduler...")
        self._running = False
        self.scheduler.shutdown()

        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

        logger.info("Scheduler service stopped")

    async def load_schedules(self) -> None:
        """Load schedules from workflows.yaml and register with APScheduler."""
        # Clear existing jobs first
        self.scheduler.remove_all_jobs()

        # Re-initialize engine to get fresh config
        self.workflow_engine = WorkflowEngine(build_routing=False)
        scheduled_workflows = self.workflow_engine.get_scheduled_workflows()

        logger.info(f"Loading schedules for {len(scheduled_workflows)} workflows")

        for name, workflow in scheduled_workflows.items():
            schedule_trigger = workflow.triggers.schedule
            if not schedule_trigger or not schedule_trigger.enabled:
                continue

            cron_expr = schedule_trigger.cron
            timezone = schedule_trigger.timezone or "UTC"

            logger.info(
                f"Registering job for workflow '{name}' with schedule: '{cron_expr}' ({timezone})"
            )

            try:
                # Add cron job to scheduler
                self.scheduler.add_job(
                    func=self.trigger_workflow,
                    trigger=CronTrigger.from_crontab(cron_expr, timezone=timezone),
                    args=[name],
                    id=name,
                    replace_existing=True,
                )
            except Exception as e:
                logger.error(
                    f"Failed to register schedule for workflow '{name}': {e}",
                    exc_info=True,
                )

    async def trigger_workflow(self, workflow_name: str) -> None:
        """Trigger a scheduled workflow execution on targeted repositories.

        Args:
            workflow_name: Name of the workflow to run
        """
        logger.info(f"Scheduled tick fired for workflow '{workflow_name}'")

        if not self._running or not self.redis_client:
            logger.warning(
                "Scheduler not running or Redis client not initialized, skipping tick"
            )
            return

        workflow = self.workflow_engine.workflows.get(workflow_name)
        if not workflow or not workflow.triggers.schedule:
            logger.warning(f"Workflow '{workflow_name}' no longer has schedule trigger")
            return

        schedule = workflow.triggers.schedule
        if not schedule.enabled:
            logger.info(
                f"Schedule for workflow '{workflow_name}' is disabled, skipping"
            )
            return

        # 1. Resolve repositories to target
        repos = await self._resolve_repositories(schedule.repos)
        if not repos:
            logger.warning(
                f"No repositories resolved for workflow '{workflow_name}', skipping"
            )
            return

        # 2. Get current timestamp for locking
        now = datetime.datetime.now(datetime.UTC)
        timestamp_str = now.strftime("%Y%m%d%H%M")  # Minute-precision lock

        for repo in repos:
            # 3. Acquire distributed lock in Redis to avoid duplicates across instances
            lock_key = f"scheduler:lock:{workflow_name}:{repo}:{timestamp_str}"
            acquired = await self.redis_client.set(lock_key, "1", ex=300, nx=True)

            if not acquired:
                logger.debug(
                    f"Lock already held for {workflow_name} on {repo} at {timestamp_str}, skipping duplicate execution"
                )
                continue

            # 4. Construct payload and publish job
            job_payload = {
                "repository": repo,
                "issue_number": None,
                "event_data": {
                    "event_type": "schedule",
                    "action": "tick",
                    "trigger_type": "schedule",
                    "scheduled_at": now.isoformat(),
                    "installation_id": str(self.config.github.github_installation_id),
                },
                "user_query": "",
                "user": "scheduler",
                "ref": "main",
                "workflow_name": workflow_name,
            }

            try:
                # Track run status in Redis
                run_time_str = now.isoformat()
                await self.redis_client.set(
                    f"scheduler:last_run:{workflow_name}:{repo}", run_time_str
                )

                # Push history (keep last 10 runs)
                history_key = f"scheduler:runs:{workflow_name}:{repo}"
                await self.redis_client.lpush(history_key, run_time_str)  # type: ignore[misc]
                await self.redis_client.ltrim(history_key, 0, 9)  # type: ignore[misc]

                # Publish to message queue
                await self.queue.publish(job_payload)
                logger.info(
                    f"Enqueued scheduled job for workflow '{workflow_name}' on repository '{repo}'"
                )
            except Exception as e:
                logger.error(
                    f"Failed to enqueue scheduled job for workflow '{workflow_name}' on repository '{repo}': {e}",
                    exc_info=True,
                )

    async def _resolve_repositories(self, repo_configs: list[str]) -> list[str]:
        """Resolve list of repositories to target based on configuration.

        Args:
            repo_configs: Configured repositories list. Possible values:
                - ["owner/repo", ...] — run on specific repos only
                - ["*"] — run on all installed repos
                - [] — no repos (schedule is effectively disabled)

        Returns:
            Resolved repository full names, or empty list if no repos apply.
        """
        # If specific repositories are configured without wildcard
        if repo_configs and "*" not in repo_configs:
            return repo_configs

        # If wildcard is explicitly set, fetch all installation repos
        if "*" in repo_configs:
            if (
                not self.config.github.github_app_id
                or not self.config.github.github_installation_id
            ):
                logger.warning(
                    "GitHub App credentials not fully configured in scheduler config. "
                    "Cannot dynamically resolve installation repositories. "
                    "Ensure GITHUB_APP_ID and GITHUB_INSTALLATION_ID are set."
                )
                return []

            try:
                logger.info("Dynamically fetching installation repositories...")
                async with GitHubAuthService(
                    app_id=self.config.github.github_app_id,
                    private_key=self.config.github.github_private_key,
                    installation_id=self.config.github.github_installation_id,
                ) as auth_service:
                    repos: list[str] = (
                        await auth_service.get_installation_repositories()
                    )
                    logger.info(
                        f"Successfully resolved {len(repos)} installation repositories: {repos}"
                    )
                    return repos
            except Exception as e:
                logger.error(
                    f"Failed to fetch installation repositories: {e}", exc_info=True
                )
                return []

        # Empty list: no repos configured, schedule is a no-op
        logger.warning(
            "Schedule trigger has no repositories configured (repos: []). "
            'Add specific repos or use ["*"] for all. '
            "Skipping execution."
        )
        return []

    async def schedule_one_shot(
        self,
        workflow_name: str,
        repo: str,
        run_at: datetime.datetime,
        issue_number: int | None = None,
        ref: str = "main",
        user: str = "scheduler",
        user_query: str = "",
    ) -> str:
        """Schedule a one-shot execution of a workflow on a repository.

        Args:
            workflow_name: Name of the workflow
            repo: Repository full name (owner/repo)
            run_at: Datetime to run at
            issue_number: Optional issue/PR number
            ref: Git ref (defaults to main)
            user: User name (defaults to scheduler)
            user_query: Optional custom prompt query

        Returns:
            Job ID
        """
        import uuid

        from apscheduler.triggers.date import DateTrigger

        job_id = f"oneshot_{workflow_name}_{repo.replace('/', '_')}_{issue_number or 0}_{uuid.uuid4().hex[:8]}"

        logger.info(
            f"Scheduling one-shot execution of workflow '{workflow_name}' on {repo} at {run_at}"
        )

        self.scheduler.add_job(
            func=self.trigger_one_shot_workflow,
            trigger=DateTrigger(run_date=run_at),
            args=[workflow_name, repo, issue_number, ref, user, user_query],
            id=job_id,
        )
        return job_id

    async def trigger_one_shot_workflow(
        self,
        workflow_name: str,
        repo: str,
        issue_number: int | None,
        ref: str,
        user: str,
        user_query: str,
    ) -> None:
        """Trigger function executed by APScheduler for one-shot runs."""
        logger.info(f"One-shot trigger fired for workflow '{workflow_name}' on {repo}")

        if not self._running:
            logger.warning("Scheduler not running, skipping one-shot trigger")
            return

        # Construct job payload
        job_payload = {
            "repository": repo,
            "issue_number": issue_number,
            "event_data": {
                "event_type": "schedule",
                "action": "one-shot",
                "trigger_type": "schedule",
                "scheduled_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "installation_id": str(self.config.github.github_installation_id),
            },
            "user_query": user_query,
            "user": user,
            "ref": ref,
            "workflow_name": workflow_name,
        }

        try:
            await self.queue.publish(job_payload)
            logger.info(
                f"Enqueued one-shot scheduled job for workflow '{workflow_name}' on repository '{repo}'"
            )
        except Exception as e:
            logger.error(
                f"Failed to enqueue one-shot scheduled job for workflow '{workflow_name}' on repository '{repo}': {e}",
                exc_info=True,
            )
