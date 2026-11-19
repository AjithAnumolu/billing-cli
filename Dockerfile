FROM python:3.10-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Install runtime dependencies without installing the project package.
# Application code will be imported directly from /app/src.
COPY pyproject.toml uv.lock ./

RUN uv sync \
    --locked \
    --no-dev \
    --no-install-project \
    --python /usr/local/bin/python \
    --no-cache

# Copy only application code and logging configuration.
COPY src/ ./src/
COPY log_config.json ./

# Run the server as a non-root user.
RUN groupadd --system app \
    && useradd --system --gid app --no-create-home app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/app/log_config.json", "--no-access-log"]