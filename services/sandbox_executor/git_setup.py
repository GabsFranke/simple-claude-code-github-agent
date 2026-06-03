"""Git configuration and submodule setup for sandbox worktrees.

Extracted from processor.py to keep the JobProcessor class focused.
These are standalone async operations that run after worktree creation.
"""

import logging
import os
import re
from pathlib import Path

from shared import WorktreeCreationError, execute_git_command

logger = logging.getLogger(__name__)

_SAFE_PATTERN = re.compile(r"^[a-zA-Z0-9\s.\-\[\]@]+$")


async def configure_git(workspace: str, github_token: str) -> None:
    """Configure git credentials and identity in a worktree.

    Sets up a per-job credential store, configures user.name/user.email,
    and enables submodule authentication via global credential helper.
    """
    credentials_file = os.path.join(workspace, ".git-credentials")
    # Set worktree-level credential helper for primary repo operations
    config_code, _, config_err = await execute_git_command(
        ["git", "config", "credential.helper", f"store --file={credentials_file}"],
        cwd=workspace,
    )
    if config_code != 0:
        raise WorktreeCreationError(
            f"Failed to configure git credentials: {config_err}"
        )

    # Also set globally — submodule clone operations spawn new git repos
    # that don't inherit worktree-level config.  The global setting
    # ensures submodule `git clone` can authenticate without an
    # interactive terminal.
    await execute_git_command(
        [
            "git",
            "config",
            "--global",
            "credential.helper",
            f"store --file={credentials_file}",
        ]
    )

    fd = os.open(credentials_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(
            fd,
            f"https://x-access-token:{github_token}@github.com\n".encode(),
        )
    finally:
        os.close(fd)

    bot_username = os.getenv("BOT_USERNAME", "Claude Code Agent")
    bot_email = os.getenv(
        "BOT_USER_EMAIL", "claude-code-agent[bot]@users.noreply.github.com"
    )

    if not _SAFE_PATTERN.match(bot_username):
        raise ValueError(f"BOT_USERNAME contains invalid characters: {bot_username!r}")
    if not _SAFE_PATTERN.match(bot_email):
        raise ValueError(f"BOT_USER_EMAIL contains invalid characters: {bot_email!r}")

    await execute_git_command(
        ["git", "config", "user.name", bot_username], cwd=workspace
    )
    await execute_git_command(["git", "config", "user.email", bot_email], cwd=workspace)


async def init_submodules(workspace: str, repo: str) -> None:
    """Initialize git submodules if .gitmodules exists in the worktree.

    Runs after worktree creation and git credential configuration so
    that private submodules can authenticate.  Failure is non-fatal —
    the agent can still work with source code, just without submodules.
    """
    gitmodules = Path(workspace) / ".gitmodules"
    if not gitmodules.exists():
        return

    logger.info(f"Found .gitmodules, initializing submodules for {repo}...")
    code, _, err = await execute_git_command(
        [
            "git",
            "-C",
            workspace,
            "submodule",
            "update",
            "--init",
            "--recursive",
        ]
    )
    if code != 0:
        logger.warning(
            f"Submodule init failed for {repo} (exit {code}): "
            f"{err}. Continuing without submodules."
        )
    else:
        logger.info(f"Submodules initialized successfully for {repo}")
