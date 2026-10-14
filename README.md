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

Needs [uv](https://docs.astral.sh/uv/) and Docker.

```bash
docker compose up -d          # Postgres 18 on localhost:54329

cd backend
uv sync
uv run alembic upgrade head   # create the tables
uv run python -m horatio.rules  # load the generic rule sets
uv run uvicorn horatio.app:app --reload

uv run pytest                 # starts its own throwaway Postgres
uv run ruff check . && uv run ruff format --check . && uv run pyright
```

Model changes need a migration: `uv run alembic revision --autogenerate -m "..."`,
then read what it generated. `tests/test_migrations.py` fails if the models and
migrations disagree.

## License

AGPL-3.0. See `LICENSE`.
