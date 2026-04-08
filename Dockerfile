# Rewired Index — Multi-stage Docker build
# Usage:
#   docker build -t rewired-index .
#   docker run --env-file .env -v ./config:/app/config -v ./data:/app/data rewired-index monitor

FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/rewired /usr/local/bin/rewired
COPY config/ config/

# Data directory created at runtime; mount a volume for persistence
RUN mkdir -p data

ENV REWIRED_LOG_FORMAT=json
ENV REWIRED_LOG_LEVEL=INFO

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD rewired health || exit 1

ENTRYPOINT ["rewired"]
CMD ["monitor"]
