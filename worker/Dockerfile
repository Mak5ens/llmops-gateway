# The job worker (worker/README.md). Dependencies come from uv.lock, installed with uv in a first stage; the final
# image only has Python, the virtual environment and the code, and runs as a non-root user.
FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

FROM python:3.13-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1
USER 10001
# SIGTERM stops the worker cleanly: it finishes the jobs it holds, then exits (src/llmops_worker/worker.py).
CMD ["llmops-worker"]
