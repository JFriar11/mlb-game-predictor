# Python and OS base are digest-pinned; update intentionally after model smoke tests.
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS build
WORKDIR /build
COPY requirements/ requirements/
RUN python -m pip install --no-cache-dir -r requirements/build.txt
COPY pyproject.toml README.md ./
COPY src/ src/
COPY config/ config/
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir /wheels .

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS runtime-base
ARG SOURCE_REVISION=unknown
ENV MLB_CODE_VERSION=${SOURCE_REVISION}
LABEL org.opencontainers.image.revision=${SOURCE_REVISION}
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LOKY_MAX_CPU_COUNT=1
WORKDIR /app
COPY requirements/runtime.txt requirements/runtime.txt
RUN python -m pip install --no-cache-dir --only-binary=:all: -r requirements/runtime.txt
COPY --from=build /wheels/ /wheels/
RUN python -m pip install --no-cache-dir --no-deps /wheels/*.whl && rm -r /wheels \
    && useradd --create-home --uid 10001 predictor \
    && mkdir -p /app/data/processed /app/data/raw /app/data/interim \
    && chown -R predictor:predictor /app/data
COPY alembic.ini ./
COPY migrations/ migrations/
COPY config/ config/
COPY scripts/verify_runtime.py scripts/verify_runtime.py
COPY scripts/verify_api.py scripts/verify_api.py
USER predictor
ENTRYPOINT ["mlb-predictor"]
CMD ["--help"]

FROM node:22-slim@sha256:4b150b48b4116e2a22f2c39cc27025fbf4f153e2078fd3b14d159fdb5c7279da AS dashboard-build
WORKDIR /dashboard
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src/ src/
RUN npx tsc --noEmit --project tsconfig.json && npx vite build

FROM runtime-base AS web
COPY --from=dashboard-build /dashboard/dist/ /app/web/
ENV MLB_WEB_DIRECTORY=/app/web MLB_API_HOST=0.0.0.0 MLB_API_PORT=8000
EXPOSE 8000
ENTRYPOINT ["mlb-predictor-api"]
CMD []

# Explicit private release target. The model is a trusted artifact, not a credential.
# BuildKit keeps it out of the source context. DB/registry secrets are never copied.
FROM web AS release
USER root
RUN --mount=type=secret,id=accepted_model,required=true \
    mkdir -p /opt/mlb \
    && install -m 0444 /run/secrets/accepted_model /opt/mlb/accepted_model_v1.joblib \
    && python -c 'import hashlib; from pathlib import Path; assert hashlib.sha256(Path("/opt/mlb/accepted_model_v1.joblib").read_bytes()).hexdigest() == "2d2f6bdd557bb9f4fa981fd88358774617fc246810f2efb2e4c79917ba9df945"'
ENV MLB_ARTIFACT_PATH=/opt/mlb/accepted_model_v1.joblib
USER predictor

# Preserve the existing default CLI-only build and artifact-free CI behavior.
FROM runtime-base AS runtime
