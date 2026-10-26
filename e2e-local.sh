#!/usr/bin/env bash
# Run the Playwright suite locally against its own database, so test troupes and
# players never land in the one ./start-local.sh uses. The `horatio_e2e`
# database is made afresh in the same Postgres container on every run.
#
#   ./e2e-local.sh                   build the app, then run every test
#   ./e2e-local.sh --no-build        reuse frontend/dist as it is
#   ./e2e-local.sh -- --project=phone   pass the rest to `playwright test`
#
# Port: HORATIO_E2E_PORT (default 8766). Needs Docker, uv and Node 22.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${HORATIO_E2E_PORT:-8766}"
DB=horatio_e2e
LOG="$ROOT/.local/logs/e2e-api.log"

build=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) build=false ;;
    --) shift; break ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) break ;;
  esac
  shift
done

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  fail "Something is already listening on port $PORT."
fi
mkdir -p "$(dirname "$LOG")"

cd "$ROOT"
say "Starting Postgres"
docker compose up -d >/dev/null
for _ in $(seq 1 60); do
  docker compose exec -T db pg_isready -U horatio >/dev/null 2>&1 && break
  sleep 1
done
say "Making a fresh $DB database"
docker compose exec -T db psql -U horatio -d postgres -q \
  -c "drop database if exists $DB with (force)" -c "create database $DB owner horatio" >/dev/null

export HORATIO_DATABASE_URL="postgresql+psycopg://horatio:horatio@localhost:54329/$DB"
cd "$ROOT/backend"
unset VIRTUAL_ENV
uv run alembic upgrade head >/dev/null 2>&1 || fail "Migrating $DB failed."
uv run python -m horatio.rules >/dev/null 2>&1 || fail "Loading rules into $DB failed."

cd "$ROOT/frontend"
if $build; then
  say "Building the app"
  npm run -s build >/dev/null
fi

say "Starting the API on :$PORT"
cd "$ROOT/backend"
# No connectors, whatever backend/.env sets up for development: the suite
# expects Discord and email to be unavailable, and sends nothing outside.
# Pictures go in a fresh directory of their own, like the database.
# Keep-alive: Playwright's request contexts keep idle connections open with no
# timeout of their own, so with uvicorn's 5 s one, a call made just as the server
# drops the connection fails with ECONNRESET. 300 s outlasts the longest test.
UPLOADS="$ROOT/.local/e2e-uploads"
rm -rf "$UPLOADS" && mkdir -p "$UPLOADS"
HORATIO_COOKIE_SECURE=false HORATIO_FRONTEND_DIST="$ROOT/frontend/dist" HORATIO_UPLOAD_DIR="$UPLOADS" \
  HORATIO_DISCORD_BOT_TOKEN= HORATIO_SMTP_HOST= \
  setsid uv run uvicorn horatio.app:app --port "$PORT" --timeout-keep-alive 300 >"$LOG" 2>&1 < /dev/null &
api=$!
stop_api() {
  kill -TERM -- "-$api" 2>/dev/null || kill -TERM "$api" 2>/dev/null || true
  wait "$api" 2>/dev/null || true
}
trap stop_api EXIT
for _ in $(seq 1 30); do
  curl -sf "localhost:$PORT/api/health" >/dev/null && break
  sleep 1
done
curl -sf "localhost:$PORT/api/health" >/dev/null || fail "The API did not start; see $LOG"

cd "$ROOT/frontend"
HORATIO_E2E_URL="http://localhost:$PORT" npx playwright test "$@"
