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

`./e2e-local.sh` does all that from the repo root, against a fresh `horatio_e2e`
database in the dev Postgres, on port 8766 (`--help` for its options). It's one
run at a time, so several worktrees share it through a lock.

#### Parallel e2e runs

`./e2e-local.sh --parallel` runs in a stack of its own instead, so runs from
several worktrees (or two from one) can go side by side:

```bash
./e2e-local.sh --parallel                          # build, wait for a free slot, run everything
./e2e-local.sh --parallel -- -g "Scene view"       # a subset
HORATIO_E2E_SLOT=2 ./e2e-local.sh --parallel       # slot 2 only, waiting for it if it's busy
```

- There are `HORATIO_E2E_SLOTS` slots (2 unless set). A run takes the first free
  one, or waits for one to come free; the slot is held by a `flock` on
  `.e2e-slot-<n>.lock` in `HORATIO_E2E_LOCK_DIR` (`$XDG_RUNTIME_DIR/horatio-e2e`
  unless set), shared by every worktree on the machine.
- Slot N is compose project `horatio-e2e-N`, a Postgres of its own from
  `compose.e2e.yaml` on port `18032+100*N`, and the API on `18066+100*N`: slot 1
  is 18132 and 18166, slot 2 is 18232 and 18266. The dev stack (`horatio`, port
  54329) isn't touched.
- When the run ends, however it ends, the API stops and the slot's containers,
  network and volume are removed. Whatever a killed run left behind is removed by
  the next run in that slot. To remove one by hand:
  `HORATIO_E2E_DB_PORT=18132 docker compose -p horatio-e2e-1 -f compose.e2e.yaml down -v`.
- The app is built before a slot is taken. Two runs from one worktree share
  `frontend/dist`, so give the second `--no-build`. Each slot's results go in
  `frontend/test-results-slot-N/`, its API log in `.local/logs/e2e-api-slot-N.log`.

Each run is a Postgres, an API and two browsers, about 2 GB and two to three
cores while it runs. Two slots suit a 12-core, 16 GB machine that also runs other
work; raise `HORATIO_E2E_SLOTS` on a bigger one.

#### e2e in CI

CI runs the e2e suite in Microsoft's Playwright image
(`mcr.microsoft.com/playwright:v<version>-noble`, in `.github/workflows/frontend.yml`).
The image has Chromium and the libraries and fonts it needs built in, so a run
doesn't install anything through apt and doesn't fail when Ubuntu's package
mirrors are down. The browsers in the image belong to one Playwright version, so
the image's version must be the `@playwright/test` version in
`frontend/package-lock.json`; a step at the start of each shard fails the run if
they differ. To upgrade Playwright, update it in `frontend/` and change the image
tag to the version now in the lock file, in the same PR.

#### Flaky tests

On CI a failed e2e test runs once more (`retries` in `playwright.config.ts`; none
locally). A test that passes the second time is *flaky*: the run stays green, but
each shard lists its flaky tests in its job summary, marks each with a warning on
the run, and keeps them, with the tests that failed outright, in an `e2e-flaky-*`
artifact for 30 days. Every Monday the `flaky-tests` workflow gathers the last two
weeks of those into one list, in its run's summary and a `flaky-tests` artifact:
each test that failed and then passed, on the retry or when its job was re-run,
with how many runs it happened in and links to them. Run it by hand from the
Actions tab at any time. A flaky test may be a race in the app, not the test
(#1168), so look at one that repeats. None of this can fail a build:
`frontend/scripts/flaky-tests.mjs` only reports.

In production the backend serves the built frontend itself
(`HORATIO_FRONTEND_DIST`), so the app and API share one origin. The live site,
https://horatio.lotslarp.org, is deployed with `deploy/deploy.sh`; see
[deploy/README.md](deploy/README.md).

Someone whose account the custodian has suspended is told, when they try to sign
in, to contact the custodian. Set `HORATIO_CUSTODIAN_CONTACT` (an email address
or a web page) to say how.

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

**Phone notifications** (web push). People turn them on per device on
Account › Notifications; the delivery worker sends them through each
browser's push service. Set:

- `HORATIO_VAPID_PRIVATE_KEY`: the server's key. Make one with
  `cd backend && uv run python -m horatio.web_push`, which prints the line.
  Keep it in the settings, never the database; a new key stops pushes to every
  device until it is turned on again there.
- `HORATIO_VAPID_SUBJECT` (optional): a `mailto:` address the push services can
  reach you at; the site's address by default.

Unset, phone notifications aren't available, and the page says so. Browsers
only allow push over HTTPS or on `localhost`, and only with the service worker,
which the dev server doesn't run: try it on a build served by the API
(`npm run build`, then `HORATIO_FRONTEND_DIST=../frontend/dist`).

Model changes need a migration: `uv run alembic revision --autogenerate -m "..."`,
then read what it generated. `tests/test_migrations.py` fails if the models and
migrations disagree.

## Dark Pack

Horatio is unofficial fan-made material under Paradox Interactive's
[Dark Pack Agreement](https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement):
free, with the agreement's notices on its About page and every page's footer.
Paradox's own art (the Dark Pack logo, clan symbols) is licensed to each server's
operator and never committed. The custodian fetches it onto the server in
Custodian › Tools, or imports it into `dark-pack/`; see `dark-pack/README.md`.

## Logo and icons

`branding/logo.png` is Horatio's logo with a transparent background, at full
size. `branding/make_graphics.py` makes it, and everything in `frontend/public`
(the loading screen and sign-in logo, favicons, app icons and the link preview
image), from the original 1024px logo on white:

```bash
python3 branding/make_graphics.py path/to/logo.jpeg   # needs Pillow and NumPy
```

## License

AGPL-3.0. See `LICENSE`.
