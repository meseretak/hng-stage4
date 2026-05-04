# Lightweight Python image — under 300MB
FROM python:3.12-alpine

# Create non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app

# Install wget for healthcheck + dependencies
COPY app/requirements.txt .
RUN apk add --no-cache wget && pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ .

# Create log directory
RUN mkdir -p /app/logs && chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Drop all capabilities (handled in docker-compose)
EXPOSE 3000

ENV MODE=stable
ENV APP_VERSION=1.0.0
ENV APP_PORT=3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:3000/healthz || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "2", "--timeout", "60", "main:app"]
