# Horatio in one image: the API, serving the built frontend on the same origin
# (HORATIO_FRONTEND_DIST). Built by deploy/cloudbuild.yaml; see deploy/README.md.

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
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
RUN useradd --system --no-create-home horatio
USER horatio
EXPOSE 8000
# Behind the host's nginx, which terminates TLS and says so in X-Forwarded-*.
CMD ["uvicorn", "horatio.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
