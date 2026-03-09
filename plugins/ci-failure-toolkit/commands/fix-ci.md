---
description: "Analyze and fix CI/CD failures using specialized agents"
argument-hint: "[owner/repo] [run-id-or-pr-number] [failure-type]"
allowed-tools:
  [
    "Task",
    "Bash",
    "Glob",
    "Grep",
    "Read",
    "Write",
    "Edit",
    "List",
    "Search",
    "mcp__github__*",
  ]
---

# CI/CD Failure Analysis and Fix

Analyze GitHub Actions workflow failures and implement fixes using specialized agents. Agents run in a git worktree with direct file access and use GitHub MCP to interact with GitHub.

**Arguments:** "$ARGUMENTS"

- First argument: Repository (owner/repo format, required)
- Second argument: Workflow run ID or PR number (required)
- Third argument: Failure type (optional: build, test, lint, deploy, all)

## Workflow:

### 1. Parse Arguments & Gather Context

Extract from $ARGUMENTS:

- Repository (owner/repo)
- Run ID or PR number
- Failure type filter (optional)

### 2. Fetch Workflow Failure Information

Use GitHub MCP to get failure details:

```bash
# Get workflow run details
mcp__github__get_workflow_run(owner, repo, run_id)

# Get workflow run logs
mcp__github__get_workflow_run_logs(owner, repo, run_id)

# If PR number provided, get associated workflow runs
mcp__github__list_workflow_runs_for_pr(owner, repo, pr_number)
```

### 3. Analyze Failure Logs

Parse logs to identify:

- **Failure type**: build, test, lint, type-check, deploy
- **Error messages**: Extract key error text
- **Failed step**: Which CI step failed
- **Stack traces**: Full error context
- **Exit codes**: Process exit status

### 4. Determine Applicable Agents

Based on failure type:

- **Build failures** → `build-failure-analyzer`
  - Compilation errors
  - Dependency issues
  - Missing environment variables
  - Configuration problems

- **Test failures** → `test-failure-analyzer`
  - Unit test failures
  - Integration test failures
  - Flaky tests
  - Timeout issues

- **Lint/Type failures** → `lint-failure-analyzer`
  - Code style violations
  - Type errors
  - Import issues
  - Formatting problems

- **Deployment failures** → `deploy-failure-analyzer`
  - Docker build failures
  - Container issues
  - Health check failures
  - Resource constraints

- **Unknown/Multiple** → Launch all applicable agents

### 5. Launch Specialized Agents

Use Task tool to delegate to specialized agents:

```python
# Example: Analyze test failure
result = Task(
    agent="test-failure-analyzer",
    prompt=f"""Analyze test failure in {repo}:

Error log:
{error_log}

Failed tests:
{failed_tests}

Identify root cause and implement fixes."""
)
```

**Sequential approach** (recommended):

1. Launch primary agent for failure type
2. Review findings
3. Launch additional agents if needed
4. Aggregate results

### 6. Implement Fixes

Agents will:

1. Read relevant files using local tools (Read, List, Search)
2. Identify root cause (not just symptoms)
3. Implement targeted fixes using Edit/Write
4. Run local tests to verify: `bash -c "pytest tests/"`
5. Check for similar issues in codebase

### 7. Commit and Push Changes

After fixes are implemented:

```bash
# Stage changes
git add .

# Commit with descriptive message
git commit -m "fix: resolve CI failure - [brief description]

- Root cause: [explanation]
- Changes: [what was fixed]
- Tested: [how it was verified]

Fixes workflow run #${run_id}"

# Push to branch
git push origin HEAD
```

### 8. Post Results to GitHub

Use GitHub MCP to communicate results:

**Option A: Comment on PR**

```python
mcp__github__add_issue_comment(
    owner=owner,
    repo=repo,
    issue_number=pr_number,
    body=summary_comment
)
```

**Option B: Create new PR with fixes**

```python
# Create branch
mcp__github__create_branch(owner, repo, f"fix/ci-failure-{run_id}", base_branch)

# Push commits (already done in step 7)

# Create PR
mcp__github__create_pull_request(
    owner=owner,
    repo=repo,
    title=f"Fix CI failure from run #{run_id}",
    body=detailed_description,
    head=f"fix/ci-failure-{run_id}",
    base="main"
)
```

### 9. Summary Format

Post a comprehensive summary:

```markdown
# CI Failure Analysis - Run #${run_id}

## Failure Type

${failure_type}

## Root Cause

${root_cause_explanation}

## Changes Made

- ${change_1}
- ${change_2}
- ${change_3}

## Files Modified

- `${file_1}` - ${description}
- `${file_2}` - ${description}

## Verification

${how_fix_was_tested}

## Prevention

${recommendations_to_prevent_recurrence}

---

🤖 Analyzed and fixed by CI Failure Toolkit
```

## Failure Type Detection

Auto-detect failure type from logs:

**Build failures:**

- Keywords: "compilation error", "build failed", "cannot find module"
- Exit codes: 1, 2
- Failed steps: "build", "compile", "install"

**Test failures:**

- Keywords: "test failed", "assertion error", "expected", "actual"
- Exit codes: 1
- Failed steps: "test", "pytest", "jest", "mocha"

**Lint failures:**

- Keywords: "lint error", "style violation", "formatting"
- Exit codes: 1
- Failed steps: "lint", "format", "style"

**Type failures:**

- Keywords: "type error", "mypy", "typescript error"
- Exit codes: 1
- Failed steps: "type-check", "mypy", "tsc"

**Deploy failures:**

- Keywords: "deployment failed", "docker build", "container"
- Exit codes: 1, 125, 126, 127
- Failed steps: "deploy", "docker", "push"

## Usage Examples:

**Auto-triggered on workflow failure:**

```
# Webhook receives workflow_job.completed with conclusion=failure
# Automatically triggers: /ci-failure-toolkit:fix-ci owner/repo 12345
```

**Manual trigger with run ID:**

```
/ci-failure-toolkit:fix-ci owner/repo 12345
# Analyzes workflow run #12345 and fixes issues
```

**Manual trigger with PR number:**

```
/ci-failure-toolkit:fix-ci owner/repo 456
# Finds failed workflow runs for PR #456 and fixes
```

**Specific failure type:**

```
/ci-failure-toolkit:fix-ci owner/repo 12345 test
# Only analyzes test failures

/ci-failure-toolkit:fix-ci owner/repo 12345 build
# Only analyzes build failures
```

## Agent Descriptions:

**build-failure-analyzer**:

- Diagnoses compilation errors
- Resolves dependency conflicts
- Fixes configuration issues
- Handles missing environment variables

**test-failure-analyzer**:

- Identifies failing test cases
- Fixes test logic errors
- Resolves flaky tests
- Updates test expectations

**lint-failure-analyzer**:

- Fixes code style violations
- Resolves import issues
- Applies formatting rules
- Handles linter configuration

**deploy-failure-analyzer**:

- Fixes Docker build issues
- Resolves container problems
- Handles deployment configuration
- Fixes health check failures

## GitHub MCP Tools:

- `get_workflow_run` - Get workflow run details
- `get_workflow_run_logs` - Fetch failure logs
- `list_workflow_runs_for_pr` - Find runs for PR
- `add_issue_comment` - Post analysis results
- `create_branch` - Create fix branch
- `create_pull_request` - Open PR with fixes

## Tips:

- **Auto-triggered**: Runs automatically on CI failures
- **Root cause focus**: Fix underlying issues, not symptoms
- **Test locally**: Verify fixes before pushing
- **Clear commits**: Descriptive commit messages with context
- **Prevention**: Suggest improvements to prevent recurrence

## Workflow Integration:

**Automatic trigger:**

```
1. CI workflow fails
2. GitHub sends workflow_job.completed webhook
3. Agent analyzes logs and identifies failure
4. Specialized agent implements fix
5. Changes committed and pushed
6. Summary posted to PR/issue
```

**Manual trigger:**

```
1. Developer comments: /fix-ci owner/repo 12345
2. Agent fetches workflow logs
3. Analyzes failure and implements fix
4. Posts results to GitHub
```

## Notes:

- Agents run in git worktree with direct file system access
- Each agent specializes in specific failure types
- Fixes are tested locally before committing
- GitHub MCP handles all GitHub interactions
- All agents available in `/agents` list
