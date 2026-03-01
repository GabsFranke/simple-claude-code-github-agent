FROM python:3.11-slim

WORKDIR /app

# Install Node.js (required by bundled Claude Code CLI)
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy shared module
COPY shared/ ./shared/

# Copy agent-worker requirements and install
COPY services/agent-worker/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy agent-worker code
COPY services/agent-worker/worker.py ./services/agent-worker/

# Copy hooks
COPY hooks/langfuse_hook.py /app/hooks/langfuse_hook.py
RUN chmod +x /app/hooks/langfuse_hook.py

# Copy subagents to Claude Code's agents directory (Markdown format)
RUN mkdir -p /root/.claude/agents
COPY subagents/*.md /root/.claude/agents/

WORKDIR /app/services/agent-worker

CMD ["python3", "worker.py"]
