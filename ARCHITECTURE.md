# Architecture

## Overview

Simple Claude Code GitHub Agent is a lightweight system that uses Claude Code CLI with GitHub's official MCP server to provide automated code reviews and respond to developer commands.

## System Architecture

```
┌─────────────────┐
│  GitHub Events  │
│  (PR, Comments) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Webhook Service│
│    (FastAPI)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Message Queue  │
│  Redis/Pub/Sub  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Worker Service │
│  Spawns Claude  │
│   Code CLI      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Claude Code    │
│      CLI        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  GitHub MCP     │
│  Server (HTTP)  │
│   (Official)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   GitHub API    │
└─────────────────┘
```

## Components

### 1. Webhook Service

**Technology:** FastAPI (Python)  
**Port:** 8080  
**Purpose:** Receives GitHub webhook events

**Responsibilities:**
- Validates webhook signatures
- Parses GitHub events (issue_comment, pull_request)
- Extracts `/agent` commands from comments
- Publishes requests to message queue
- Triggers automatic PR reviews

**Key Files:**
- `services/webhook/main.py`

### 2. Message Queue

**Technology:** Redis (self-hosted) or Google Pub/Sub (cloud)  
**Purpose:** Decouples webhook from worker for async processing

**Benefits:**
- Handles webhook timeouts (GitHub expects response in 10s)
- Enables horizontal scaling of workers
- Provides retry mechanism
- Allows long-running agent tasks

**Key Files:**
- `shared/queue.py` - Abstraction layer

### 3. Worker Service

**Technology:** Python + Claude Code CLI (Node.js)  
**Purpose:** Processes agent requests

**Responsibilities:**
- Subscribes to message queue
- Configures Claude Code settings from environment
- Fetches CLAUDE.md from repositories (if present)
- Spawns Claude Code CLI with appropriate prompts
- Handles both manual commands and automatic reviews

**Key Files:**
- `services/agent-worker/worker.py`

### 4. Claude Code CLI

**Technology:** Node.js CLI tool by Anthropic  
**Purpose:** Autonomous coding agent

**Capabilities:**
- Reads and analyzes code
- Creates branches and commits
- Opens pull requests
- Posts comments and reviews
- Executes bash commands
- Iterates on feedback

**Configuration:**
- `~/.claude/settings.json` - Permissions and model settings
- `~/.claude/mcp.json` - MCP server configurations

### 5. GitHub MCP Server

**Technology:** HTTP-based MCP server by GitHub  
**Endpoint:** `https://api.githubcopilot.com/mcp`  
**Authentication:** GitHub Personal Access Token

**Tools Provided:**
- `read_file` - Read file contents
- `list_files` - List directory contents
- `create_branch` - Create new branches
- `update_file` - Create/update files
- `create_pull_request` - Open PRs
- `get_issue` - Get issue details
- And more...

## Data Flow

### Automatic PR Review

1. Developer opens PR
2. GitHub sends `pull_request` webhook
3. Webhook service receives event
4. Webhook publishes to queue: `{repo, pr_number, command: "Review this PR", auto_review: true}`
5. Worker picks up message
6. Worker spawns Claude Code with review prompt
7. Claude Code uses GitHub MCP to read PR diff
8. Claude Code posts review comments
9. Developer sees review on GitHub

### Manual Command

1. Developer comments `/agent explain this function`
2. GitHub sends `issue_comment` webhook
3. Webhook service parses command
4. Webhook publishes to queue: `{repo, issue_number, command: "explain this function"}`
5. Worker picks up message
6. Worker checks for CLAUDE.md in repo
7. Worker spawns Claude Code with command
8. Claude Code uses GitHub MCP to read code
9. Claude Code posts explanation as comment
10. Developer sees response on GitHub

## Deployment Options

### Self-Hosted (Development)

**Infrastructure:**
- Docker Compose
- Redis container
- Local ngrok tunnel

**Pros:**
- Easy to set up
- Free (except API costs)
- Full control

**Cons:**
- Not production-ready
- Requires always-on machine
- Manual scaling

### Cloud (Production)

**Infrastructure:**
- Google Cloud Run (webhook + worker)
- Google Pub/Sub (message queue)
- Cloud Load Balancer

**Pros:**
- Auto-scaling
- High availability
- Managed infrastructure

**Cons:**
- More complex setup
- Cloud costs

## Security

### Authentication

- **GitHub:** Personal Access Token with `repo` scope
- **Anthropic:** API key for Claude Code
- **Webhooks:** HMAC signature verification

### Permissions

Claude Code permissions configured in `~/.claude/settings.json`:
- Allow: Read, Write, Edit, Bash, MCP tools
- Deny: Empty (trust Claude Code's judgment)
- Ask: Empty (auto-approve allowed tools)

### Best Practices

- Store secrets in environment variables
- Use webhook signature verification
- Limit GitHub PAT scope to required repos
- Review Claude Code's actions in logs
- Use CLAUDE.md to set repository-specific rules

## Scalability

### Horizontal Scaling

- Multiple worker instances can subscribe to same queue
- Each worker processes messages independently
- Redis/Pub/Sub handles distribution

### Performance

- Webhook responds immediately (< 100ms)
- Worker processes in background (1-10 minutes)
- Claude Code timeout: 10 minutes per request

### Limits

- GitHub API rate limits: 5000 requests/hour (with PAT)
- Anthropic API rate limits: Varies by plan
- Claude Code: One request at a time per worker

## Monitoring

### Logs

- Webhook: Request/response logs
- Worker: Claude Code output, errors
- Queue: Message counts, processing times

### Metrics

- Requests processed
- Success/failure rates
- Average processing time
- Queue depth

## Future Enhancements

- [ ] Support for GitHub App authentication (bot identity)
- [ ] Multi-repository management dashboard
- [ ] Custom review rules per repository
- [ ] Integration with CI/CD pipelines
- [ ] Slack/Discord notifications
- [ ] Analytics and insights
