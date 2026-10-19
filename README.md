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
(`HORATIO_FRONTEND_DIST`), so the app and API share one origin. The live site,
https://horatio.lotslarp.org, is deployed with `deploy/deploy.sh`; see
[deploy/README.md](deploy/README.md).

### Delivering downtime results

Results always appear in Horatio. Troupes can also switch on connectors that
send a copy; a worker inside the API sends them every
`HORATIO_DELIVERY_INTERVAL` seconds (default 15; `0` turns it off). Links in
messages use `HORATIO_PUBLIC_URL` (default `http://localhost:5173`).

**Discord.** Horatio posts through one bot that each troupe adds to its own
server. To set it up once for the whole site:

1. Create an application at <https://discord.com/developers/applications>.
2. Under *Bot*, reset and copy the token. No privileged intents are needed.
3. Under *OAuth2*, copy the client id and secret, and add the redirect
   `{HORATIO_PUBLIC_URL}/api/discord/callback`.
4. Set `HORATIO_DISCORD_CLIENT_ID`, `HORATIO_DISCORD_CLIENT_SECRET` and
   `HORATIO_DISCORD_BOT_TOKEN`.

Storytellers then use *Add Horatio to your Discord* on their troupe's
Connectors tab and pick each character's private channel. The bot asks only
to view channels and send messages.

**Email.** Horatio sends mail from its own address through one SMTP service,
with the troupe's storyteller address as Reply-To; no troupe connects its own
mail account. Set:

- `HORATIO_SMTP_HOST`, `HORATIO_SMTP_PORT` (587), `HORATIO_SMTP_USERNAME`,
  `HORATIO_SMTP_PASSWORD`; `HORATIO_SMTP_STARTTLS` (true, for port 587) or
  `HORATIO_SMTP_SSL` (true, for port 465).
- `HORATIO_MAIL_FROM`, such as `Horatio <horatio@mail.example.org>`.

Any provider with SMTP works (Amazon SES, Postmark, Mailgun…). So that mail
from the sending domain is delivered rather than marked as spam, publish:

- **SPF**: a TXT record on the sending domain allowing the provider, such as
  `v=spf1 include:amazonses.com ~all` (your provider gives the exact value).
- **DKIM**: the CNAME or TXT records your provider gives, so it signs mail for
  your domain.
- **DMARC**: a TXT record at `_dmarc.<domain>`, starting with
  `v=DMARC1; p=none; rua=mailto:<you>` and tightening to `p=quarantine` once
  reports look clean.

Locally, `./start-local.sh` starts Mailpit and points Horatio at it: mail
appears at <http://localhost:8025>.

Model changes need a migration: `uv run alembic revision --autogenerate -m "..."`,
then read what it generated. `tests/test_migrations.py` fails if the models and
migrations disagree.

## License

AGPL-3.0. See `LICENSE`.
