"""Command registry for managing available commands."""

import logging

from .base import Command, CommandContext, CommandResult

logger = logging.getLogger(__name__)


class CommandRegistry:
    """Registry for all available commands."""

    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._auto_triggers: dict[str, Command] = {}

    def register(self, command: Command, auto_trigger: str | None = None):
        """Register a command.

        Args:
            command: Command instance to register
            auto_trigger: Optional event type that auto-triggers this command
                         (e.g., "auto_review", "auto_triage")
        """
        self._commands[command.name] = command

        # Register aliases
        for alias in command.aliases:
            self._commands[alias] = command

        # Register auto-trigger
        if auto_trigger:
            self._auto_triggers[auto_trigger] = command

        logger.info(f"Registered command: {command.name}")

    def get_command(self, command_text: str) -> Command | None:
        """Get command by name or alias."""
        # Extract first word as command name, rest is arguments
        cmd = command_text.strip().lower().split()[0] if command_text.strip() else ""
        return self._commands.get(cmd)

    def get_auto_trigger(self, event_type: str) -> Command | None:
        """Get command for auto-trigger event."""
        return self._auto_triggers.get(event_type)

    async def execute(self, context: CommandContext) -> CommandResult:
        """Execute a command based on context.

        Args:
            context: Command execution context

        Returns:
            CommandResult with prompt

        Raises:
            ValueError: If command not found
        """
        # Check for auto-trigger first
        if context.event_type.startswith("auto_"):
            command = self.get_auto_trigger(context.event_type)
            if command:
                logger.info(f"Auto-triggering command: {command.name}")
                return await command.build_prompt(context)

        # Parse manual command
        command = self.get_command(context.command_text)
        if not command:
            # Fallback to generic command
            command = self._commands.get("generic")
            if not command:
                raise ValueError(f"Unknown command: {context.command_text}")

        logger.info(f"Executing command: {command.name}")
        return await command.build_prompt(context)

    def list_commands(self) -> list[Command]:
        """List all registered commands (excluding aliases)."""
        seen = set()
        commands = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                commands.append(cmd)
                seen.add(cmd.name)
        return commands


# Global registry instance
_registry: CommandRegistry | None = None


def get_command_registry() -> CommandRegistry:
    """Get the global command registry."""
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
        _register_builtin_commands(_registry)
    return _registry


def _register_builtin_commands(registry: CommandRegistry):
    """Register built-in commands."""
    from .builtin import GenericCommand, IssueTriageCommand, PRReviewCommand

    # Register commands
    registry.register(PRReviewCommand(), auto_trigger="auto_review")
    registry.register(IssueTriageCommand(), auto_trigger="auto_triage")
    registry.register(GenericCommand())  # Fallback
