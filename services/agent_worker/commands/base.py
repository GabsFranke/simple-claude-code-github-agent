"""Base classes for command system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CommandContext:
    """Context passed to command handlers."""

    repo: str
    issue_number: int
    command_text: str
    user: str
    event_type: str  # "manual", "auto_review", "auto_triage", etc.
    raw_data: dict[str, Any]  # Original webhook data


@dataclass
class CommandResult:
    """Result from command execution."""

    prompt: str
    metadata: dict[str, Any] | None = None


class Command(ABC):
    """Base class for all commands."""

    def __init__(self, name: str, description: str, aliases: list[str] | None = None):
        self.name = name
        self.description = description
        self.aliases = aliases or []

    @abstractmethod
    async def build_prompt(self, context: CommandContext) -> CommandResult:
        """Build the prompt for this command.

        Args:
            context: Command execution context

        Returns:
            CommandResult with prompt and optional metadata
        """
        raise NotImplementedError

    def matches(self, command_text: str) -> bool:
        """Check if this command matches the given text."""
        cmd = command_text.strip().lower()
        return cmd == self.name or cmd in self.aliases
