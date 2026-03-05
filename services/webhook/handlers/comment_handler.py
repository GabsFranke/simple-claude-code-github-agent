"""Handle GitHub comment events."""

import logging
import sys
from pathlib import Path
from typing import Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers.command_parser import parse_command  # noqa: E402

logger = logging.getLogger(__name__)


async def handle_comment_created(
    data: dict[str, Any], queue, sync_queue
) -> dict[str, str] | None:
    """Handle issue comment created event."""
    comment_body = data["comment"]["body"]
    command = parse_command(comment_body)

    if not command:
        logger.debug(
            "Comment on issue #%s does not contain /agent command",
            data["issue"]["number"],
        )
        return None

    # Determine ref before building request_data
    ref = "main"
    if "pull_request" in data["issue"]:
        ref = f"refs/pull/{data['issue']['number']}/head"

    request_data = {
        "repository": data["repository"]["full_name"],
        "issue_number": data["issue"]["number"],
        "command": command,
        "user": data["comment"]["user"]["login"],
        "ref": ref,  # Include ref so agent_worker uses the correct one
    }

    logger.info("Agent command detected: /agent %s", command)
    logger.info(
        "Processing request for %s issue #%s",
        request_data["repository"],
        request_data["issue_number"],
    )

    # Publish sync request - sync worker will use GitHub App credentials
    await sync_queue.publish({"repo": request_data["repository"], "ref": ref})

    logger.info(f"Publishing job with ref: {ref}")
    logger.info(f"Request data: {request_data}")
    await queue.publish(request_data)

    return {"status": "accepted", "message": "Agent is processing your request"}
