# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535
FROM ghcr.io/astral-sh/uv:0.9.30@sha256:538e0b39736e7feae937a65983e49d2ab75e1559d35041f9878b7b7e51de91e4 AS uv
FROM denoland/deno:bin-2.9.8@sha256:b507583d3c68ba69f3ed2ce5969ae5b8b70f43421c781279c7aea06435263543 AS deno

FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.11 \
    UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE} AS runtime
ARG APP_UID=1000
ARG APP_GID=1000
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN test "$APP_UID" -gt 0 && test "$APP_GID" -gt 0 \
    && groupadd --gid "$APP_GID" app \
    && useradd --uid "$APP_UID" --gid "$APP_GID" --create-home app \
    && mkdir -p /data/output /models /input \
    && chown app:app /data/output /models
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=deno /deno /usr/local/bin/deno
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    HOME=/home/app \
    YT_MIDI_MODEL_DIR=/models/yourmt3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DENO_NO_UPDATE_CHECK=1 \
    DENO_NO_PROMPT=1
USER app
WORKDIR /data
ENTRYPOINT ["yt-midi"]
CMD ["--help"]
