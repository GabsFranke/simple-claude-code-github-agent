# Installation Guide

## Prerequisites

- Docker & Docker Compose (recommended) OR Python 3.11+
- GitHub App with appropriate permissions
- Anthropic API Key
- ngrok (for local webhook testing)

## Option 1: Docker Installation (Recommended)

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/simple-claude-code-github-agent.git
cd simple-claude-code-github-agent
```

### 2. Install as Package (Optional but Recommended)

This eliminates sys.path hacks and enables clean imports:

```bash
# Install in editable mode
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

### 3. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Required variables:

```bash
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_APP_ID=123456
GITHUB_INSTALLATION_ID=789012
GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
GITHUB_WEBHOOK_SECRET=your-webhook-secret
REDIS_PASSWORD=myredissecret
```

See [CONFIGURATION.md](CONFIGURATION.md) for all options.

### 4. Start Services

```bash
# Minimal setup (without Langfuse)
docker-compose -f docker-compose.minimal.yml up --build -d

# Full setup with Langfuse observability
docker-compose up --build -d

# Scale workers for parallel processing
docker-compose up --scale worker=2 -d
```

### 5. Verify Health

```bash
# Check webhook health
curl http://localhost:10000/health

# Check worker health
docker-compose exec worker cat /tmp/worker_health

# View logs
docker-compose logs -f worker
docker-compose logs -f webhook
```

## Option 2: Manual Installation

### 1. Install Python Dependencies

```bash
# Install package
pip install -e .

# Install worker dependencies
pip install -r services/agent-worker/requirements.txt

# Install webhook dependencies
pip install -r services/webhook/requirements.txt

# Install dev dependencies (optional)
pip install -r requirements-dev.txt
```

### 2. Install Redis

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt-get install redis-server
sudo systemctl start redis

# Windows
# Download from https://redis.io/download
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Run Services

Terminal 1 (Webhook):

```bash
cd services/webhook
python main.py
```

Terminal 2 (Worker):

```bash
cd services/agent-worker
python worker.py
```

Terminal 3 (Redis):

```bash
redis-server
```

## Verification

### 1. Check Configuration

```bash
# Test configuration loading
python -c "from shared.config import get_worker_config; print(get_worker_config())"
```

If configuration is invalid, you'll see clear error messages:

```
FATAL: Configuration validation failed: 1 validation error for WorkerConfig
github -> github_app_id
  Field required [type=missing]
```

### 2. Check Health

```bash
# Webhook health
curl http://localhost:10000/health

# Worker health (Docker)
docker-compose exec worker cat /tmp/worker_health

# Worker health (Manual)
cat /tmp/worker_health
```

Expected output:

```
healthy=1
last_activity=1709123456
uptime=120
processed=0
errors=0
message=Healthy: Last activity 30s ago
```

### 3. Test Webhook

```bash
# Send test webhook
curl -X POST http://localhost:10000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: ping" \
  -d '{"zen": "test"}'
```

### 4. Check Logs

```bash
# Docker
docker-compose logs -f worker
docker-compose logs -f webhook

# Manual
# Check terminal outputs
```

## Troubleshooting

### Configuration Errors

If you see configuration validation errors:

1. **Check required fields**:

   ```bash
   grep -E "GITHUB_|ANTHROPIC_" .env
   ```

2. **Validate PEM format**:

   ```bash
   echo "$GITHUB_PRIVATE_KEY" | head -1
   # Should show: -----BEGIN RSA PRIVATE KEY-----
   ```

3. **Test configuration**:
   ```python
   from shared.config import get_worker_config
   try:
       config = get_worker_config()
       print("✓ Configuration valid")
   except Exception as e:
       print(f"✗ Configuration error: {e}")
   ```

### Import Errors

If you see import errors like `ModuleNotFoundError: No module named 'shared'`:

1. **Install package**:

   ```bash
   pip install -e .
   ```

2. **Verify installation**:

   ```bash
   python -c "import shared; print(shared.__file__)"
   ```

3. **Check PYTHONPATH** (if not using package install):
   ```bash
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   ```

### Health Check Failures

If worker shows unhealthy:

1. **Check health file exists**:

   ```bash
   ls -la /tmp/worker_health
   ```

2. **Check file age**:

   ```bash
   stat /tmp/worker_health
   ```

3. **Check worker logs**:

   ```bash
   docker-compose logs worker | tail -50
   ```

4. **Restart worker**:
   ```bash
   docker-compose restart worker
   ```

### Rate Limiting Issues

If requests are slow or timing out:

1. **Check rate limit logs**:

   ```bash
   docker-compose logs worker | grep "Rate limit"
   ```

2. **Adjust limits** in `.env`:

   ```bash
   GITHUB_RATE_LIMIT=4000  # Lower if hitting limits
   ANTHROPIC_RATE_LIMIT=80
   ```

3. **Reduce workers** if running multiple:
   ```bash
   docker-compose up --scale worker=1
   ```

See [RATE_LIMITING.md](RATE_LIMITING.md) for details.

### Redis Connection Errors

If you see Redis connection errors:

1. **Check Redis is running**:

   ```bash
   redis-cli ping
   # Should return: PONG
   ```

2. **Check Redis URL**:

   ```bash
   echo $REDIS_URL
   # Should be: redis://localhost:6379 or redis://redis:6379
   ```

3. **Test connection**:
   ```bash
   redis-cli -h localhost -p 6379 -a "$REDIS_PASSWORD" ping
   ```

## Next Steps

1. **Set up GitHub App** - See [README.md](../README.md#setup-self-hosting)
2. **Configure ngrok** - For local webhook testing
3. **Install GitHub App** - On your test repository
4. **Test with PR** - Open a PR and watch the agent review it
5. **Monitor health** - Set up alerts for unhealthy workers
6. **Tune rate limits** - Adjust based on your API plan

## Upgrading

### From Previous Version

If upgrading from a version without Pydantic Settings:

1. **Pull latest code**:

   ```bash
   git pull origin main
   ```

2. **Install new dependencies**:

   ```bash
   pip install -e .
   # Or rebuild Docker images
   docker-compose build
   ```

3. **Update .env** - No changes needed, same variables

4. **Restart services**:

   ```bash
   docker-compose down
   docker-compose up -d
   ```

5. **Verify configuration**:
   ```bash
   docker-compose logs worker | head -20
   # Should see: "Configuration loaded: GitHub App ID=..."
   ```

### Breaking Changes

None - the configuration system is backward compatible. All environment variables work the same way.

## Development Setup

For development with hot reload:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest

# Run linters
black .
isort .
mypy .
ruff check .

# Or use the check script
./check-code.ps1  # Windows
# Or create check-code.sh for Linux/macOS
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.
