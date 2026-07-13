# syntax=docker/dockerfile:1

# ---- builder: resolve deps + build the venv with uv, then drop uv ----
FROM python:3.12-slim-bookworm AS builder

# Pin uv by copying its binary from the official image (the combined
# uv+python+distro tags aren't published for every uv release).
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies first, in their own layer — only busts when the lock changes,
# so editing app code doesn't re-resolve dependencies.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Then the project itself.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime: clean slim image, just python + the prebuilt venv ----
FROM python:3.12-slim-bookworm

# Run as a non-root user.
RUN groupadd -r app && useradd -r -g app -d /app app

COPY --from=builder --chown=app:app /app /app

# PYTHONUNBUFFERED: flush stdout/stderr immediately so `kubectl logs` isn't blank
# (Python block-buffers when stdout isn't a tty, e.g. a container's log pipe).
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
USER app

# Defaults to the API; the worker Deployment overrides `command`.
EXPOSE 8000
CMD ["uvicorn", "sandbox_control_plane.app:app", "--host", "0.0.0.0", "--port", "8000"]
