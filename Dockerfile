FROM python:3.12-slim

# Drop all Linux capabilities at build time via labels (enforced in compose)
# Create non-root user and group
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/sh --create-home appuser && \
    mkdir -p /app/logs && \
    chown -R appuser:appgroup /app

WORKDIR /app

# Install dependencies as root before switching users (layer cached separately)
COPY app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/main.py .


RUN chown -R appuser:appgroup /app

# Switch to non-root user for all subsequent instructions and runtime
USER appuser

# Document the port — actual exposure controlled exclusively by Nginx in compose
EXPOSE 3000

# Health check — Docker will poll this every 30s
# 3 retries before marking unhealthy, 10s startup grace period
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:3000/healthz')" \
    || exit 1


CMD ["gunicorn", \
    "--workers=1", \
    "--threads=8", \
    "--bind=0.0.0.0:3000", \
    "--timeout=120", \
    "--access-logfile=/app/logs/access.log", \
    "--error-logfile=/app/logs/error.log", \
    "main:app"]