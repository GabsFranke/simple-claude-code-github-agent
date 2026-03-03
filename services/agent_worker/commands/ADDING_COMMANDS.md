# How to Add New Commands - Quick Guide

## 3-Step Process

### Step 1: Create Your Command File

Create a new file in `commands/builtin/` (or your own directory):

```python
# commands/builtin/fix_bug.py
from commands.base import Command, CommandContext, CommandResult

class FixBugCommand(Command):
    """Command to help fix bugs."""

    def __init__(self):
        super().__init__(
            name="fix-bug",
            description="Help fix a bug",
            aliases=["fix", "debug", "bugfix"],
        )

    async def build_prompt(self, context: CommandContext) -> CommandResult:
        """Build the prompt for bug fixing."""
        prompt = f"""You are helping fix a bug in {context.repo}.

Issue #{context.issue_number}: {context.command_text}

Please:
1. Analyze the bug description
2. Identify the root cause
3. Suggest a fix with code
4. Explain why this fixes the issue

Use GitHub MCP tools to read relevant code."""

        return CommandResult(
            prompt=prompt,
            metadata={"command_type": "fix_bug"},
        )
```

### Step 2: Register Your Command

Add to `commands/registry.py`:

```python
def _register_builtin_commands(registry: CommandRegistry):
    from .builtin import (
        PRReviewCommand,
        IssueTriageCommand,
        GenericCommand,
        FixBugCommand,  # Add this
    )

    registry.register(PRReviewCommand(), auto_trigger="auto_review")
    registry.register(IssueTriageCommand(), auto_trigger="auto_triage")
    registry.register(GenericCommand())
    registry.register(FixBugCommand())  # Add this
```

### Step 3: Use Your Command

Users can now use any of these:

- `/agent fix-bug the login issue`
- `/agent fix the authentication problem`
- `/agent debug why users can't log in`
- `/agent bugfix the session timeout`

## Examples

### Example 1: Simple Command

```python
class HelloCommand(Command):
    def __init__(self):
        super().__init__(name="hello", description="Say hello")

    async def build_prompt(self, context: CommandContext) -> CommandResult:
        return CommandResult(
            prompt=f"Say hello to {context.user} in issue #{context.issue_number}",
        )
```

### Example 2: Command with Metadata

```python
class SecurityScanCommand(Command):
    def __init__(self):
        super().__init__(
            name="security-scan",
            description="Scan for security issues",
            aliases=["scan", "security"],
        )

    async def build_prompt(self, context: CommandContext) -> CommandResult:
        prompt = f"Scan {context.repo} for security issues..."

        return CommandResult(
            prompt=prompt,
            metadata={
                "command_type": "security",
                "requires_elevated_permissions": True,
                "estimated_duration": "5-10 minutes",
            },
        )
```

### Example 3: Auto-Trigger Command

```python
class AutoTestCommand(Command):
    def __init__(self):
        super().__init__(
            name="auto-test",
            description="Automatically run tests on PR",
        )

    async def build_prompt(self, context: CommandContext) -> CommandResult:
        return CommandResult(
            prompt=f"Run tests for PR #{context.issue_number}...",
        )

# Register with auto-trigger
registry.register(AutoTestCommand(), auto_trigger="auto_test")
```

## Command Best Practices

### ✅ DO:

- Use clear, descriptive names (`fix-bug`, not `fb`)
- Provide helpful aliases (`review`, `review-pr`, `pr-review`)
- Include context in prompts (repo, issue number)
- Add metadata for tracking
- Keep prompts focused and specific

### ❌ DON'T:

- Hardcode repository names
- Make assumptions about context
- Create overly generic commands
- Duplicate existing functionality
- Forget to register the command

## Testing Your Command

```python
# tests/unit/test_fix_bug_command.py
import pytest
from commands.builtin.fix_bug import FixBugCommand
from commands.base import CommandContext

@pytest.mark.asyncio
async def test_fix_bug_command():
    cmd = FixBugCommand()

    # Test name and aliases
    assert cmd.name == "fix-bug"
    assert "fix" in cmd.aliases
    assert "debug" in cmd.aliases

    # Test prompt building
    context = CommandContext(
        repo="owner/repo",
        issue_number=42,
        command_text="fix the login bug",
        user="developer",
        event_type="manual",
        raw_data={},
    )

    result = await cmd.build_prompt(context)

    assert "owner/repo" in result.prompt
    assert "42" in result.prompt
    assert "fix the login bug" in result.prompt
    assert result.metadata["command_type"] == "fix_bug"
```

## Advanced: Dynamic Commands

### Load Commands from Config

```python
# commands/dynamic_loader.py
import yaml

def load_commands_from_yaml(file_path: str):
    with open(file_path) as f:
        config = yaml.safe_load(f)

    for cmd_config in config["commands"]:
        cmd = DynamicCommand(
            name=cmd_config["name"],
            description=cmd_config["description"],
            prompt_template=cmd_config["prompt"],
        )
        registry.register(cmd)
```

### Per-Repository Commands

```python
# Load custom commands from .github/agent-commands/
async def load_repo_commands(repo: str):
    commands_dir = f".github/agent-commands/"
    # Load Python files or YAML configs
    # Register with registry
```

## Summary

Adding a command is as simple as:

1. **Create** a class that extends `Command`
2. **Implement** `build_prompt()` method
3. **Register** in `registry.py`

That's it! The command system handles:

- Routing user input to your command
- Passing context (repo, issue, user, etc.)
- Executing your prompt with Claude SDK
- Tracking metadata and analytics

No need to modify core code, no hardcoded prompts, fully testable!
