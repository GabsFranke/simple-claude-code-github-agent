# Rate Limiting

The worker service includes built-in rate limiting to prevent exceeding API rate limits for GitHub and Anthropic.

## Overview

Rate limiting uses a token bucket algorithm to control request rates:

- GitHub API: 5000 requests per hour (default)
- Anthropic API: 100 requests per minute (default)

## How It Works

### Token Bucket Algorithm

1. Each API has a bucket with a maximum number of tokens
2. Each request consumes one token
3. Tokens are replenished over time
4. If no tokens available, requests wait

### Implementation

```python
from shared import MultiRateLimiter

# Initialize rate limiters
rate_limiters = MultiRateLimiter()
rate_limiters.add_limiter("github", max_requests=5000, time_window=3600)
rate_limiters.add_limiter("anthropic", max_requests=100, time_window=60)

# Use before API calls
await rate_limiters.acquire("github")  # Waits if rate limit reached
# Make GitHub API call

await rate_limiters.acquire("anthropic", timeout=60.0)  # With timeout
# Make Anthropic API call
```

## Configuration

```bash
# .env
GITHUB_RATE_LIMIT=5000  # Requests per hour
ANTHROPIC_RATE_LIMIT=100  # Requests per minute
```

### Adjusting Limits

Based on your API plan:

**GitHub:**

- Free tier: 5000 requests/hour
- GitHub App: 5000 requests/hour per installation
- Enterprise: Higher limits (check your plan)

**Anthropic:**

- Tier 1: 50 requests/minute
- Tier 2: 100 requests/minute
- Tier 3: 200 requests/minute
- Tier 4: 400 requests/minute

## Where Rate Limiting is Applied

### GitHub API Calls

Rate limiting is applied to:

- Fetching CLAUDE.md from repositories
- Creating GitHub App installation tokens
- Any direct GitHub API calls

```python
# In RequestProcessor._fetch_claude_md()
if self.rate_limiters:
    await self.rate_limiters.acquire("github", timeout=30.0)

# Make GitHub API call
response = await self.http_client.get(url, headers=headers)
```

### Anthropic API Calls

Rate limiting is applied to:

- Claude SDK execution
- All Claude API requests

```python
# In RequestProcessor._execute_claude_sdk()
if self.rate_limiters:
    await self.rate_limiters.acquire("anthropic", timeout=60.0)

# Execute Claude SDK
async with ClaudeSDKClient(options=options) as client:
    await client.query(prompt)
```

## Behavior

### Normal Operation

When rate limit is available:

```
[INFO] Acquiring Anthropic API rate limit...
[DEBUG] anthropic: Request acquired (42/100)
```

### Rate Limit Reached

When rate limit is exhausted:

```
[DEBUG] anthropic: Rate limit reached, waiting 15.23s
[INFO] Acquiring Anthropic API rate limit...
[DEBUG] anthropic: Request acquired (100/100)
```

### Timeout

If waiting exceeds timeout:

```python
try:
    await rate_limiters.acquire("github", timeout=30.0)
except asyncio.TimeoutError:
    logger.error("Rate limit timeout exceeded")
```

## Monitoring

### Logs

Rate limiter logs include:

- Current usage (e.g., "42/100")
- Wait times when rate limited
- Timeout warnings

### Metrics

Track these metrics:

- Rate limit wait time
- Number of rate limit hits
- Current usage percentage

Example:

```python
limiter = rate_limiters.get_limiter("github")
usage = len(limiter.requests) / limiter.max_requests * 100
logger.info(f"GitHub API usage: {usage:.1f}%")
```

## Scaling Considerations

### Multiple Workers

Each worker has its own rate limiter. If you run multiple workers:

```bash
docker-compose up --scale worker=3
```

Effective rate limit = `RATE_LIMIT / NUM_WORKERS`

Example:

- GitHub limit: 5000/hour
- 3 workers: ~1667/hour per worker
- Total: Still 5000/hour (shared across workers)

**Solution**: Adjust per-worker limits:

```bash
# For 3 workers
GITHUB_RATE_LIMIT=1667  # 5000 / 3
ANTHROPIC_RATE_LIMIT=33  # 100 / 3
```

### Distributed Rate Limiting

For true distributed rate limiting across workers, you'd need:

1. Shared Redis counter
2. Distributed lock
3. Centralized rate limiter service

This is not currently implemented but can be added if needed.

## Troubleshooting

### Requests Taking Too Long

If requests are slow:

1. **Check rate limit usage**:

   ```bash
   docker-compose logs worker | grep "Rate limit"
   ```

2. **Increase limits** (if your API plan allows):

   ```bash
   ANTHROPIC_RATE_LIMIT=200  # If you have Tier 3
   ```

3. **Reduce workers** if running multiple:
   ```bash
   docker-compose up --scale worker=1
   ```

### Rate Limit Errors from API

If you still get rate limit errors from the API:

1. **Lower the configured limit**:

   ```bash
   GITHUB_RATE_LIMIT=4000  # Leave buffer
   ANTHROPIC_RATE_LIMIT=80  # Leave buffer
   ```

2. **Check for other API consumers** using the same credentials

3. **Monitor actual API usage** via provider dashboards

### Timeout Errors

If you see timeout errors:

1. **Increase timeout**:

   ```python
   await rate_limiters.acquire("anthropic", timeout=120.0)  # 2 minutes
   ```

2. **Reduce request rate** by lowering limits

3. **Add more workers** with distributed rate limiting

## Advanced Usage

### Custom Rate Limiter

```python
from shared import RateLimiter

# Create custom rate limiter
custom_limiter = RateLimiter(
    max_requests=1000,
    time_window=3600,
    name="custom-api"
)

# Use it
await custom_limiter.acquire(timeout=30.0)
```

### Multiple Rate Limiters

```python
rate_limiters = MultiRateLimiter()

# Add multiple limiters
rate_limiters.add_limiter("github", 5000, 3600)
rate_limiters.add_limiter("anthropic", 100, 60)
rate_limiters.add_limiter("custom", 1000, 3600)

# Use them
await rate_limiters.acquire("github")
await rate_limiters.acquire("anthropic")
await rate_limiters.acquire("custom")
```

### Conditional Rate Limiting

```python
# Only rate limit if configured
if self.rate_limiters:
    await self.rate_limiters.acquire("github")

# Make API call
```

## Best Practices

1. **Set conservative limits** - Leave 10-20% buffer
2. **Monitor usage** - Track rate limit hits in logs
3. **Adjust for scaling** - Divide limits by number of workers
4. **Use timeouts** - Prevent indefinite waiting
5. **Handle errors** - Catch `asyncio.TimeoutError`
6. **Test limits** - Verify behavior under load

## Testing Rate Limiting

```python
import asyncio
from shared import RateLimiter

async def test_rate_limiting():
    limiter = RateLimiter(max_requests=5, time_window=10, name="test")

    # Make 5 requests quickly (should succeed)
    for i in range(5):
        await limiter.acquire()
        print(f"Request {i+1} succeeded")

    # 6th request should wait
    print("Making 6th request (should wait)...")
    start = time.time()
    await limiter.acquire()
    elapsed = time.time() - start
    print(f"6th request succeeded after {elapsed:.2f}s")

asyncio.run(test_rate_limiting())
```

Expected output:

```
Request 1 succeeded
Request 2 succeeded
Request 3 succeeded
Request 4 succeeded
Request 5 succeeded
Making 6th request (should wait)...
[DEBUG] test: Rate limit reached, waiting 10.00s
6th request succeeded after 10.02s
```
