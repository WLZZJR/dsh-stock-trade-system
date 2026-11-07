FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Dependencies first for layer caching.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps ./apps
COPY packages ./packages
COPY configs ./configs

ENV PYTHONPATH=/app/packages:/app/apps PATH="/app/.venv/bin:$PATH"
RUN useradd --system --no-create-home gei
USER gei
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
