# Horatio

A character database and downtime system for Mind's Eye Theatre LARP troupes.

Horatio is the successor to [Yorick](https://github.com/gnu-lorien/yorick). It
keeps Yorick's features (characters, XP, approvals, troupes, printable sheets)
and replaces the troupe's spreadsheet-based downtime tooling with downtimes
handled inside the app.

It is a fresh codebase, not a port: see `docs/adr/0001-rewrite-rather-than-port.md`.

## Docs

- `CONTEXT.md`: the domain glossary. Read it before naming anything.
- `docs/adr/`: architecture decisions and why they were made.
- `docs/design/schema.md`: the agreed database design.

## Development

Needs [uv](https://docs.astral.sh/uv/), Docker and Node 22.

### Quick start

```bash
./start-local.sh                          # database, API on :8010, app on http://localhost:5173
./start-local.sh --reset                  # the same, with an empty database
./start-local.sh --custodian you@example.com   # also make an existing account the custodian
./stop-local.sh                           # stop it all (--keep-db leaves Postgres running)
```

Sign up in the app, then make yourself custodian to create troupes. Use real-looking
emails (`@example.com` works): reserved domains such as `.test` and `.local` are
refused. Logs are in `.local/logs/`. Different ports:
`HORATIO_API_PORT=8020 HORATIO_APP_PORT=5180 ./start-local.sh`.

### By hand

```bash
docker compose up -d          # Postgres 18 on localhost:54329

cd backend
uv sync
uv run alembic upgrade head   # create the tables
uv run python -m horatio.rules  # load the generic rule sets
HORATIO_COOKIE_SECURE=false uv run uvicorn horatio.app:app --reload
# API docs: http://localhost:8000/docs (everything is under /api)
# After signing up, make yourself custodian:
uv run python -m horatio.custodian you@example.com

uv run pytest                 # starts its own throwaway Postgres
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

In another terminal, the frontend (React, TypeScript, Vite) at http://localhost:5173:

```bash
cd frontend
npm install
npm run dev          # proxies /api to the backend on :8000
npm run api          # regenerate API types after changing the backend
npm run typecheck && npm test
```

End-to-end tests drive the whole app in a browser, against a backend serving
the built frontend:

```bash
npm run build
(cd ../backend && HORATIO_COOKIE_SECURE=false HORATIO_FRONTEND_DIST=$PWD/../frontend/dist \
  uv run uvicorn horatio.app:app --port 8766) &
npx playwright test
```

In production the backend serves the built frontend itself
(`HORATIO_FRONTEND_DIST`), so the app and API share one origin.

Model changes need a migration: `uv run alembic revision --autogenerate -m "..."`,
then read what it generated. `tests/test_migrations.py` fails if the models and
migrations disagree.

## License

AGPL-3.0. See `LICENSE`.
