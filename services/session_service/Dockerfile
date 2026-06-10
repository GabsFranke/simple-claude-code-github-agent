FROM python:3.12-slim

WORKDIR /app

# Copy and install dependencies
COPY services/session_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and shared library
COPY services/session_service/ .
COPY shared/ ./shared/

# Expose session service port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
