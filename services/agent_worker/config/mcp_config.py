"""MCP server configuration."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def setup_mcp_config(github_token: str):
    """Configure GitHub MCP server."""
    mcp_config_file = Path.home() / ".claude" / "mcp.json"
    mcp_config_file.parent.mkdir(parents=True, exist_ok=True)

    mcp_config = {
        "mcpServers": {
            "github": {
                "type": "http",
                "url": "https://api.githubcopilot.com/mcp",
                "headers": {"Authorization": f"Bearer {github_token}"},
            }
        }
    }

    with open(mcp_config_file, "w", encoding="utf-8") as f:
        json.dump(mcp_config, f, indent=2)

    logger.info("MCP config created")
