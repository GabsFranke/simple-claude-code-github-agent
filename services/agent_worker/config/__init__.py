"""Configuration modules."""

from .claude_settings import setup_claude_settings
from .mcp_config import setup_mcp_config

__all__ = ["setup_claude_settings", "setup_mcp_config"]
