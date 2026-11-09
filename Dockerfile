# Horatio in one image: the API, serving the built frontend on the same origin
# (HORATIO_FRONTEND_DIST). Built by deploy/cloudbuild.yaml; see deploy/README.md.

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# The user manual, which the build bundles from ../docs/manual (src/manual/content.ts).
COPY docs/manual /docs/manual
RUN npm run build

FROM python:3.12-slim
# pg_dump for the custodian's backups (horatio.backups), from PostgreSQL's own
# repository: it must be at least the server's version, 18.
# The repository's signing key, vendored so the build does not fetch it from
# www.postgresql.org (#583): https://www.postgresql.org/media/keys/ACCC4CF8.asc,
# fingerprint B97B 0AFC AA1A 47F0 44F2  44A0 7FCC 7D46 ACCC 4CF8.
COPY deploy/pgdg-ACCC4CF8.asc /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
# apt retries a dropped connection to Debian or apt.postgresql.org.
RUN echo 'Acquire::Retries "5";' > /etc/apt/apt.conf.d/80-retries \
 && apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "$VERSION_CODENAME")-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-18 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so a code change does not reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/src ./src
RUN uv sync --locked --no-dev
COPY --from=frontend /frontend/dist ./frontend

ENV PATH="/app/.venv/bin:$PATH" \
    HORATIO_FRONTEND_DIST=/app/frontend
# A fixed uid, which owns the backups directory mounted from the host.
RUN useradd --system --uid 10001 --no-create-home horatio
# What was built and when, for the custodian's System tab (horatio.api.system).
# Last, so a new commit does not rebuild the layers above.
ARG HORATIO_COMMIT=""
ARG HORATIO_BUILT_AT=""
ENV HORATIO_COMMIT=$HORATIO_COMMIT \
    HORATIO_BUILT_AT=$HORATIO_BUILT_AT
USER horatio
EXPOSE 8000
# Behind the host's nginx, which terminates TLS and says so in X-Forwarded-*.
CMD ["uvicorn", "horatio.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
