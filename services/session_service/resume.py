"""Resume job creation module — handles user messages to completed sessions.

Ported from session_proxy/_handle_resume_message().  Creates a resume job
when a browser user sends a message to a completed/errored session.

Flow:
    1. Acquire atomic resume lock (SETNX) — duplicate prevention
    2. Get streaming session, validate status (completed/error)
    3. Transition session: completed/error → running
    4. Increment run_count
    5. Drain inbox atomically (no message duplication)
    6. Publish user message to msg channel + persist to history
    7. Build job data (session_mode=resume, original session_id)
    8. Enqueue job in Redis pending queue
    9. Release resume lock

Does NOT import from session_proxy — this is a clean port using
SessionStore and direct Redis operations.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from shared.constants import (
    DEFAULT_SESSION_TTL_HOURS,
    DEFAULT_SESSION_TTL_SECONDS,
    JOB_DATA_PREFIX,
    JOB_STATUS_PREFIX,
    JOB_TTL_SECONDS,
    MSG_CHANNEL,
    PENDING_JOB_QUEUE,
    _now_iso,
    history_key,
)
from shared.session_store import SessionStore

logger = logging.getLogger(__name__)

RESUME_LOCK_PREFIX = "agent:session:resume:lock:"
RESUME_LOCK_TTL = 30

_RESUMABLE_STATUSES = frozenset({"completed", "error"})


async def handle_resume(
    token: str,
    message: str,
    store: SessionStore,
    redis: Any,
) -> dict | None:
    """Handle a user message to a completed or errored session.

    Returns the job_data dict if a resume job was created, or ``None``
    if the session is already running, expired, not found, or a resume
    is already pending (lock not acquired).

    Args:
        token: Streaming session token.
        message: User message content from the browser.
        store: ``SessionStore`` instance for session operations.
        redis: Redis client for job queue and lock management.
    """
    lock_acquired = await _acquire_resume_lock(token, redis)
    if not lock_acquired:
        logger.info(
            "[Resume] Lock not acquired for %s... — resume already in progress",
            token[:8],
        )
        return None

    try:
        session = await store.get_streaming_session(token)
        if session is None:
            logger.info(
                "[Resume] Session not found for %s... — cannot resume",
                token[:8],
            )
            return None

        current_status = str(session.status)
        if current_status not in _RESUMABLE_STATUSES:
            logger.info(
                "[Resume] Session %s... status=%s — not resumable (expected completed/error)",
                token[:8],
                current_status,
            )
            return None

        conversation_config = _parse_conversation_config(session.conversation_config)
        ttl_hours = conversation_config.get("ttl_hours", DEFAULT_SESSION_TTL_HOURS)
        ttl_seconds = ttl_hours * 3600

        await store.set_running(token, ttl_seconds=ttl_seconds)

        await store.increment_run_count(token)

        channel = MSG_CHANNEL.format(token)
        now = _now_iso()

        # Notify the SPA that the session is now running again
        sensitive = {"installation_id"}
        safe_meta = {
            k: v
            for k, v in session.model_dump(mode="json").items()
            if k not in sensitive
        }
        safe_meta["status"] = "running"
        safe_meta["workflow"] = safe_meta.get("workflow_name", "")
        meta_msg = json.dumps({"type": "session_meta", "data": safe_meta, "ts": now})
        await redis.publish(channel, meta_msg)

        # Show a run boundary so the user knows a new run is starting
        new_run = (session.run_count or 0) + 1
        run_msg = json.dumps(
            {
                "type": "run_start",
                "data": {"run_number": new_run, "session_id": session.session_id},
                "ts": now,
            }
        )
        await redis.publish(channel, run_msg)

        # Echo the user message on msg channel so other browser tabs see it.
        # The sending tab already shows it via optimistic render.
        user_msg = json.dumps(
            {"type": "user_message", "data": {"content": message}, "ts": now}
        )
        await redis.publish(channel, user_msg)

        hist_key = history_key(token)
        await redis.rpush(hist_key, user_msg)
        await redis.expire(hist_key, DEFAULT_SESSION_TTL_SECONDS)

        inbox_messages = await store.pop_inbox_messages(token)
        for inbox_msg in inbox_messages:
            inbox_payload = json.dumps(
                {"type": "user_message", "data": {"content": inbox_msg}, "ts": now}
            )
            await redis.publish(channel, inbox_payload)
            await redis.rpush(hist_key, inbox_payload)

        session_dict = session.model_dump(mode="json")
        session_dict.setdefault("issue_number", str(session.issue_number or "0"))

        job_data = await _build_job_data(
            session=session_dict,
            content=message,
            conversation_config=conversation_config,
            token=token,
        )
        job_id = await _create_job(job_data, redis)

        logger.info(
            "[Resume] Created job %s for session %s... (mode=%s, status was %s)",
            job_id[:8],
            token[:8],
            job_data["session_mode"],
            current_status,
        )
        return job_data

    finally:
        await _release_resume_lock(token, redis)


async def _acquire_resume_lock(token: str, redis: Any) -> bool:
    """Atomically acquire the resume lock for *token*.

    Uses ``SETNX`` to ensure only one caller can create a resume job
    for this session at a time.  The lock has a short TTL as a safety
    net in case the holder crashes before releasing it.
    """
    lock_key = f"{RESUME_LOCK_PREFIX}{token}"
    acquired = await redis.setnx(lock_key, "1")
    if acquired:
        await redis.expire(lock_key, RESUME_LOCK_TTL)
    return bool(acquired)


async def _release_resume_lock(token: str, redis: Any) -> None:
    """Release the resume lock for *token*."""
    lock_key = f"{RESUME_LOCK_PREFIX}{token}"
    try:
        await redis.delete(lock_key)
    except Exception:
        logger.warning("[Resume] Failed to release resume lock for %s...", token[:8])


def _parse_conversation_config(raw: str) -> dict[str, Any]:
    """Parse conversation_config JSON, falling back to sensible defaults."""
    if not raw:
        return {"persist": True, "ttl_hours": DEFAULT_SESSION_TTL_HOURS}
    try:
        config: dict[str, Any] = json.loads(raw)
        config.setdefault("persist", True)
        return config
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("[Resume] Invalid conversation_config, using defaults")
        return {"persist": True, "ttl_hours": DEFAULT_SESSION_TTL_HOURS}


async def _build_job_data(
    session: dict[str, str],
    content: str,
    conversation_config: dict,
    token: str,
) -> dict:
    """Build a job_data dict for a resume job.

    Mirrors session_proxy/_build_job_data() but without GitHub token
    regeneration — the worker handles that independently.
    """
    repo = session.get("repo", "")
    issue_number_str = str(session.get("issue_number", "0"))
    issue_number = int(issue_number_str) if issue_number_str.isdigit() else 0
    workflow = session.get("workflow_name", "") or session.get("workflow", "generic")
    session_id = session.get("session_id", "")
    thread_type = session.get("thread_type", "issue")
    ref = session.get("ref", "main")
    user = session.get("user", "remote-control")
    installation_id = session.get("installation_id", "")

    return {
        "repo": repo,
        "issue_number": issue_number,
        "prompt": content,
        "user": user,
        "workflow_name": workflow,
        "ref": ref,
        "session_mode": "resume" if session_id else "new",
        "session_id": session_id or None,
        "session_token": token,
        "streaming_enabled": True,
        "installation_id": installation_id,
        "github_token": None,
        "thread_type": thread_type,
        "thread_id": str(issue_number),
        "conversation_config": conversation_config,
        "user_query": content,
        "event_data": {"event_type": "remote_control"},
    }


async def _create_job(job_data: dict, redis: Any) -> str:
    """Create a job directly in Redis.

    Stores job data and status with TTL, then pushes the job ID
    onto the pending queue so a worker picks it up.
    """
    job_id = str(uuid.uuid4())
    await redis.setex(
        f"{JOB_DATA_PREFIX}{job_id}", JOB_TTL_SECONDS, json.dumps(job_data)
    )
    await redis.setex(f"{JOB_STATUS_PREFIX}{job_id}", JOB_TTL_SECONDS, "pending")
    await redis.rpush(PENDING_JOB_QUEUE, job_id)
    logger.info(
        "[Resume] Enqueued job %s (mode=%s)", job_id[:8], job_data.get("session_mode")
    )
    return job_id
