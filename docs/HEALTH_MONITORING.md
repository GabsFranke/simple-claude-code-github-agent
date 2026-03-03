# Health Monitoring

The worker service includes built-in health monitoring to track service health and enable Docker health checks.

## Health Check System

### How It Works

The `HealthChecker` class:

1. Tracks last activity timestamp
2. Counts processed messages and errors
3. Writes health status to a file periodically
4. Determines health based on idle time

### Health Status File

Location: `/tmp/worker_health` (configurable via `HEALTH_CHECK_FILE`)

Format:

```
healthy=1
last_activity=1709123456
uptime=3600
processed=42
errors=2
message=Healthy: Last activity 15s ago
```

### Health Criteria

A worker is considered **healthy** if:

- Activity occurred within the last 5 minutes (300 seconds)
- The health file is updated regularly

A worker is considered **unhealthy** if:

- No activity for more than 5 minutes
- Health file is stale (not updated in 2 minutes)

## Docker Health Check

The worker Dockerfile includes a health check:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD test -f /tmp/worker_health && \
      [ $(( $(date +%s) - $(stat -c %Y /tmp/worker_health 2>/dev/null || echo 0) )) -lt 120 ] || exit 1
```

This checks:

1. Health file exists
2. Health file was modified within the last 2 minutes

### Check Health Status

```bash
# View health status
docker-compose exec worker cat /tmp/worker_health

# Check Docker health
docker-compose ps
# Look for "healthy" or "unhealthy" status

# View health check logs
docker inspect --format='{{json .State.Health}}' <container-id> | jq
```

## Configuration

```bash
# .env
HEALTH_CHECK_INTERVAL=30  # Update interval in seconds (default: 30)
HEALTH_CHECK_FILE=/tmp/worker_health  # File path (default: /tmp/worker_health)
```

## Monitoring Integration

### Prometheus

You can expose health metrics by reading the health file:

```python
from pathlib import Path

def get_worker_health():
    health_file = Path("/tmp/worker_health")
    if not health_file.exists():
        return {"healthy": 0}

    data = {}
    for line in health_file.read_text().splitlines():
        key, value = line.split("=", 1)
        data[key] = value

    return data
```

### Alerting

Set up alerts based on:

- Container health status (Docker/Kubernetes)
- Health file age
- Error count in health file
- Processed message count (detect stalls)

## Troubleshooting

### Worker Shows Unhealthy

1. **Check logs**:

   ```bash
   docker-compose logs -f worker
   ```

2. **Check health file**:

   ```bash
   docker-compose exec worker cat /tmp/worker_health
   ```

3. **Common causes**:
   - No messages in queue (expected if idle)
   - Worker stuck processing a message
   - Configuration error preventing startup
   - Resource exhaustion (CPU/memory)

### Health File Not Updating

1. **Check worker is running**:

   ```bash
   docker-compose ps worker
   ```

2. **Check for errors**:

   ```bash
   docker-compose logs worker | grep -i error
   ```

3. **Restart worker**:
   ```bash
   docker-compose restart worker
   ```

### False Positives

If the worker is healthy but shows unhealthy:

1. **Increase max idle time** (if queue is legitimately empty):

   ```python
   # In worker.py
   health_checker = HealthChecker(
       max_idle_time=600,  # 10 minutes instead of 5
   )
   ```

2. **Adjust health check interval**:
   ```bash
   # .env
   HEALTH_CHECK_INTERVAL=15  # More frequent updates
   ```

## Activity Tracking

The health checker automatically tracks:

### Successful Processing

```python
# In worker callback
await processor.process(...)
health_checker.record_activity()  # Automatically called
```

### Errors

```python
# In worker callback
except Exception as e:
    logger.error(f"Error: {e}")
    health_checker.record_error()  # Automatically called
```

## Health Check API

### Webhook Service

The webhook service has a simple health endpoint:

```bash
curl http://localhost:10000/health
```

Response:

```json
{
  "status": "healthy",
  "service": "webhook",
  "queue_type": "redis"
}
```

### Worker Service

The worker doesn't expose an HTTP endpoint (by design). Use the health file instead:

```bash
# Read health file
cat /tmp/worker_health

# Or via Docker
docker-compose exec worker cat /tmp/worker_health
```

## Best Practices

1. **Monitor health status** in your orchestration platform
2. **Set up alerts** for unhealthy workers
3. **Auto-restart** unhealthy containers
4. **Track trends** in processed/error counts
5. **Adjust thresholds** based on your workload

## Example: Kubernetes Liveness Probe

```yaml
livenessProbe:
  exec:
    command:
      - sh
      - -c
      - |
        test -f /tmp/worker_health && \
        [ $(( $(date +%s) - $(stat -c %Y /tmp/worker_health) )) -lt 120 ]
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 10
  failureThreshold: 3
```

## Example: Docker Compose with Auto-Restart

```yaml
worker:
  # ... other config ...
  restart: unless-stopped
  healthcheck:
    test:
      [
        "CMD",
        "sh",
        "-c",
        "test -f /tmp/worker_health && [ $$(( $$(date +%s) - $$(stat -c %Y /tmp/worker_health) )) -lt 120 ]",
      ]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 10s
```
