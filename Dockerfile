# syntax=docker/dockerfile:1
# Multi-stage build using plain pip on a Python 3.12 slim base. Stage 1 installs
# third-party deps + the six local packages (editable) into a venv; stage 2 is a
# slim runtime that copies the venv + source. Produces one app image run via
# Uvicorn (single entry point: the `fdp` console script).

# ---- Stage 1: builder ------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Create the venv the runtime stage will copy.
RUN python -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install third-party deps first so this layer caches independently of source
# changes. requirements.txt is the flattened runtime dependency set.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Now copy the package manifests + source and install the local packages
# editable, in dependency order (--no-deps so pip never tries to fetch the local
# fdp-* names from PyPI; their third-party deps are already installed above).
COPY packages/ packages/
RUN for pkg in shared ingestion unification api ui app; do \
        pip install --no-deps -e "packages/$pkg"; \
    done

# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# Bring the prepared venv and source from the builder. The editable installs
# reference /app/packages, so both must be copied to the same paths.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/packages /app/packages

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

USER appuser
EXPOSE 8000

# Container-level liveness probe hits the health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# Single entry point: the console script boots Uvicorn.
CMD ["fdp"]
