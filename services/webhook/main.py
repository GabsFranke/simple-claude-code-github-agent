"""GitHub webhook receiver."""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from handlers import (
    handle_comment_created,
    handle_issue_opened,
    handle_pr_opened,
    handle_pr_other_action,
)
from validators import verify_signature

from shared import get_queue
from shared.config import get_webhook_config

# Load configuration
try:
    config = get_webhook_config()
except Exception as e:
    print(f"FATAL: Configuration validation failed: {e}", file=sys.stderr)
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

logger.info(f"Logging configured at {config.log_level} level")
logger.info(f"Configuration loaded: Port={config.port}")

app = FastAPI(title="SimpleClaudeCodeGitHubAgent Webhook Service")

# Initialize queue
queue = get_queue()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"status": "SimpleClaudeCodeGitHubAgent webhook service is running"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "webhook",
        "queue_type": config.queue.queue_type,
    }


@app.post("/webhook")
async def webhook(request: Request):
    """Handle GitHub webhook events."""
    try:
        # Get payload and headers
        payload = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        event_type = request.headers.get("X-GitHub-Event", "")

        # Verify signature
        webhook_secret = config.github.github_webhook_secret
        if webhook_secret and not verify_signature(payload, signature, webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse payload
        data = await request.json()
        action = data.get("action", "N/A")

        logger.info("Received %s event (action: %s)", event_type, action)

        # Ignore push events
        if event_type == "push":
            logger.debug("Ignoring push event to %s", data.get("ref", "unknown ref"))
            return {"status": "ignored", "message": "Push events are not handled"}

        # Route to appropriate handler
        if event_type == "issues" and action == "opened":
            return await handle_issue_opened(data, queue)

        if event_type == "issue_comment" and action == "created":
            result = await handle_comment_created(data, queue)
            if result:
                return result
            # No command found, return ignored
            return {"status": "ignored", "message": "No /agent command found"}

        if event_type == "pull_request":
            if action == "opened":
                return await handle_pr_opened(data, queue)
            return handle_pr_other_action(action, data["pull_request"]["number"])

        return {"status": "ignored", "message": "Event not handled"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing webhook: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.port)
