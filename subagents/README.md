# Subagents

This directory contains specialized subagent definitions for Claude Code. Subagents are focused agents that the main agent can delegate specific tasks to.

## Available Subagents

### PR Review Subagents

These subagents are automatically invoked by the coordinator for comprehensive PR reviews:

#### architecture-reviewer
Reviews architectural decisions, design patterns, and system design. Checks SOLID principles, coupling, separation of concerns, and consistency with existing architecture.

**Use when:**
- Reviewing significant code changes
- Evaluating new features or modules
- Assessing technical debt

#### security-reviewer
Scans for security vulnerabilities including SQL injection, XSS, CSRF, authentication flaws, sensitive data exposure, and insecure dependencies.

**Use when:**
- Reviewing security-critical code
- Changes to authentication/authorization
- API endpoints and data handling

#### bug-hunter
Identifies potential bugs, edge cases, null handling issues, race conditions, error handling problems, and logic errors.

**Use when:**
- Reviewing complex logic
- Changes to critical paths
- Error-prone code areas

#### code-quality-reviewer
Reviews code quality, style, maintainability, documentation, naming conventions, and adherence to coding standards.

**Use when:**
- Ensuring code maintainability
- Onboarding new contributors
- Enforcing style guides

### General Purpose Subagents

#### context-gatherer
Explores repository structure to identify relevant files and code sections for a given task. Read-only permissions for safe exploration.

**Use when:**
- Starting work on unfamiliar code
- Investigating issues across multiple files
- Understanding component relationships

#### bug-investigator
Traces bugs to their root causes by analyzing execution paths and error conditions. Suggests specific fixes.

**Use when:**
- Investigating reported bugs
- Debugging unexpected behavior
- Tracing error conditions

#### test-writer
Creates comprehensive test cases covering happy paths, edge cases, and error conditions. Has write permissions to create test files.

**Use when:**
- Adding test coverage
- Testing new features
- Writing integration tests

## Creating New Subagents

To add a new subagent, create a JSON file in this directory:

```json
{
  "name": "my-subagent",
  "description": "Brief description of what this subagent does",
  "systemPrompt": "Detailed instructions for the subagent...",
  "permissions": {
    "allow": ["Read", "Glob", "Grep"],
    "deny": ["Write", "Edit", "Bash"],
    "ask": []
  }
}
```

### Permission Options

**allow**: Tools the subagent can use
- `Read` - Read files
- `Write` - Create/modify files
- `Edit` - Edit existing files
- `Bash` - Execute shell commands
- `Glob` - Search files by pattern
- `Grep` - Search file contents
- `mcp__github` - Use GitHub MCP tools

**deny**: Tools explicitly blocked

**ask**: Tools that require confirmation (empty array = auto-approve allowed tools)

## Using Subagents

### Automatic Delegation (PR Reviews)

When a PR is opened, the main agent automatically coordinates a multi-agent review:

1. Spawns 4 specialized subagents in parallel
2. Each subagent analyzes the PR from their perspective
3. Coordinator synthesizes findings into unified review
4. Posts summary comment and inline comments for critical issues

No manual intervention needed - this happens automatically.

### Explicit Invocation

Users can request specific subagents:
```
/agent use context-gatherer to find authentication files
/agent have security-reviewer check for vulnerabilities
/agent ask architecture-reviewer to evaluate this design
```

### Programmatic Use

In code or prompts:
```bash
claude subagent architecture-reviewer "Review the design of the new payment service"
claude subagent security-reviewer "Check for security issues in the auth module"
```

## Best Practices

1. **Keep subagents focused** - Each should have a clear, specific purpose
2. **Minimal permissions** - Only grant permissions needed for the task
3. **Clear system prompts** - Provide detailed instructions and examples
4. **Descriptive names** - Use names that clearly indicate the subagent's purpose
5. **Test thoroughly** - Verify subagents work as expected before deploying

## Deployment

Subagents are automatically copied to `~/.claude/subagents/` in the Docker container during build. After adding or modifying subagents, rebuild the container:

```bash
docker-compose build worker
docker-compose up -d
```
