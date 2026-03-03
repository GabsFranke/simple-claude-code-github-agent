"""Example: How to add a custom command.

This file shows how developers can easily add new commands.
"""

from commands.base import Command, CommandContext, CommandResult


class CodeExplainCommand(Command):
    """Explain code in detail."""

    def __init__(self):
        super().__init__(
            name="explain",
            description="Explain code in detail",
            aliases=["explain-code", "what-does-this-do"],
        )

    async def build_prompt(self, context: CommandContext) -> CommandResult:
        """Build code explanation prompt."""
        prompt = f"""You are analyzing code in {context.repo}.

Issue #{context.issue_number}: {context.command_text}

Please provide a detailed explanation of:
1. What the code does
2. How it works (step by step)
3. Any potential issues or improvements
4. Related code that might be affected

Use GitHub MCP tools to read the relevant files."""

        return CommandResult(
            prompt=prompt,
            metadata={"command_type": "explain"},
        )


# To register this command, add to commands/registry.py:
# from .examples.custom_command import CodeExplainCommand
# registry.register(CodeExplainCommand())
