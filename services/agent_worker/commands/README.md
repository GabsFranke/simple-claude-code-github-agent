# Command System Architecture

## Overview

The command system provides a scalable, maintainable way to add new agent commands without modifying core code. Commands are self-contained, testable, and can be registered dynamically.

## Architecture

```
commands/
├── base.py                    # Base classes (Command, CommandContext, CommandResult)
├── registry.py                # Command registry and routing
├── builtin/                   # Built-in commands
│   ├── pr_review.py          # /review-pr command
│   ├── issue_triage.py       # Auto-triage command
│   └── generic.py            # Fallback for unknown commands
├── examples/                  # Example custom commands
│   └── custom_command.py     # How to add new commands
└── prompts/                   # Prompt templates (future)
    └── README.md             # Template documentation
```

## Key Concepts

### 1. Command

A command is a handler that builds a prompt for the Claude SDK.

```python
class Command(ABC):
    def __init__(self, name: str, description: str, aliases: list[str] = None)

    @abstractmethod
    async def build_prompt(self, context: CommandContext) -> CommandResult:
        pass
```

### 2. CommandContext

Rich context passed to command handlers:

```python
@dataclass
class CommandContext:
    repo: str                    # Repository name
    issue_number: int            # Issue/PR number
    command_text: str            # Command text after /agent
    user: str                    # GitHub username
    event_type: str              # "manual", "auto_review", "auto_triage"
    raw_data: Dict[str, Any]     # Original webhook data
```

### 3. CommandRegistry

Central registry that routes commands:

```python
registry = get_command_registry()

# Register a command
registry.register(MyCommand(), auto_trigger="auto_review")

# Execute a command
result = await registry.execute(context)
```

## Adding a New Command

### Step 1: Create Command Class

```python
# commands/builtin/explain.py
from commands.base import Command, CommandContext, CommandResult

class ExplainCommand(Command):
    def __init__(self):
        super().__init__(
            name="explain",
            description="Explain code in detail",
            aliases=["explain-code", "what"],
        )

    async def build_prompt(self, context: CommandContext) -> CommandResult:
        prompt = f"""Explain the code in {context.repo} issue #{context.issue_number}.

{context.command_text}

Provide:
1. What the code does
2. How it works
3. Potential issues

Use GitHub MCP tools."""

        return CommandResult(
            prompt=prompt,
            metadata={"command_type": "explain"},
        )
```

### Step 2: Register Command

```python
# commands/registry.py
def _register_builtin_commands(registry: CommandRegistry):
    from .builtin import ExplainCommand

    registry.register(ExplainCommand())
```

### Step 3: Use Command

Users can now use:

- `/agent explain this function`
- `/agent explain-code the authentication logic`
- `/agent what does this do`

## Auto-Trigger Commands

Commands can be triggered automatically by events:

```python
# Register with auto-trigger
registry.register(PRReviewCommand(), auto_trigger="auto_review")

# Triggered when webhook has auto_review=True
```

### Supported Auto-Triggers:

- `auto_review` - PR opened
- `auto_triage` - Issue opened without /agent command

## Command Routing

```
User types: /agent review-pr

1. Webhook parses "/agent review-pr"
2. Worker receives: command_text="review-pr", event_type="manual"
3. Registry looks up "review-pr" command
4. PRReviewCommand.build_prompt() is called
5. Prompt is sent to Claude SDK
```

## Benefits

### ✅ Scalability

- Add commands without modifying core code
- Each command is self-contained
- No if/else chains

### ✅ Maintainability

- Single responsibility per command
- Easy to understand and modify
- Clear separation of concerns

### ✅ Testability

- Mock CommandContext for testing
- Test each command independently
- No dependencies on SDK or HTTP

### ✅ Flexibility

- Commands can be added at runtime
- Aliases for user convenience
- Metadata for tracking/analytics

## Testing Commands

```python
# tests/unit/test_commands.py
import pytest
from commands.builtin import PRReviewCommand
from commands.base import CommandContext

@pytest.mark.asyncio
async def test_pr_review_command():
    cmd = PRReviewCommand()
    context = CommandContext(
        repo="owner/repo",
        issue_number=123,
        command_text="review-pr",
        user="developer",
        event_type="manual",
        raw_data={},
    )

    result = await cmd.build_prompt(context)

    assert "owner/repo" in result.prompt
    assert "123" in result.prompt
    assert result.metadata["uses_plugin"] is True
```

## Future Enhancements

### 1. Prompt Templates (YAML)

```yaml
# prompts/review-pr.yaml
name: review-pr
template: |
  Review PR #{issue_number} in {repo}.
  Focus on: {focus_areas}
variables:
  - repo
  - issue_number
  - focus_areas (optional)
```

### 2. Per-Repo Custom Commands

```
.github/agent-commands/
├── custom-review.py
└── prompts/
    └── custom-review.yaml
```

### 3. Command Plugins

```python
# Load commands from external packages
registry.load_plugin("my-agent-commands")
```

### 4. Command Chaining

```
/agent review-pr then explain the changes
```

### 5. Command Parameters

```
/agent review-pr --focus=security,performance
```

## Migration from Old System

### Before (Hardcoded):

```python
def _build_prompt(repo, issue, command, auto_review, auto_triage):
    if auto_review:
        return f"/pr-review-toolkit:review-pr {repo} {issue} all"
    elif auto_triage:
        return f"Triage issue #{issue}..."
    else:
        return f"Generic prompt for {command}..."
```

### After (Command System):

```python
context = CommandContext(repo, issue, command, user, event_type, {})
registry = get_command_registry()
result = await registry.execute(context)
prompt = result.prompt
```

## Summary

The command system provides:

- **Pluggable architecture** - Add commands without core changes
- **Clean separation** - Commands, prompts, and execution are separate
- **Easy testing** - Mock context, test commands independently
- **User-friendly** - Aliases, auto-triggers, clear naming
- **Future-proof** - Ready for templates, plugins, parameters

This makes it easy for developers to add new commands and for users to discover and use them.
