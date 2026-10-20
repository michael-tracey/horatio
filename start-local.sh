#!/usr/bin/env bash
# Start Horatio locally for hand testing: Postgres, the API on :8010, and the
# app on http://localhost:5173. Stop it all with ./stop-local.sh.
# Other ports: HORATIO_API_PORT=8020 HORATIO_APP_PORT=5180 ./start-local.sh
#
#   ./start-local.sh                         start (keeps existing data)
#   ./start-local.sh --reset                 wipe the local database first
#   ./start-local.sh --custodian EMAIL       also make EMAIL the custodian
#                                            (they must have signed up already)
#
# Logs go to .local/logs/. Needs Docker, uv and Node 22.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$ROOT/.local"
LOGS="$STATE/logs"
API_PORT="${HORATIO_API_PORT:-8010}"
APP_PORT="${HORATIO_APP_PORT:-5173}"

reset=false
custodian=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset) reset=true ;;
    --custodian) custodian="${2:?--custodian needs an email}"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

for tool in docker uv npm curl; do
  command -v "$tool" >/dev/null || fail "$tool is not installed."
done

running() { [[ -f "$STATE/$1.pid" ]] && kill -0 "$(cat "$STATE/$1.pid")" 2>/dev/null; }
if running api || running app; then
  fail "Horatio already seems to be running. Run ./stop-local.sh first."
fi
for port in "$API_PORT" "$APP_PORT"; do
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    fail "Something is already listening on port $port."
  fi
done
mkdir -p "$LOGS"

# --- database ---------------------------------------------------------------------
cd "$ROOT"
if $reset; then
  say "Wiping the local database"
  docker compose down -v >/dev/null 2>&1 || true
fi
say "Starting Postgres"
docker compose up -d >/dev/null
for _ in $(seq 1 60); do
  docker compose exec -T db pg_isready -U horatio >/dev/null 2>&1 && break
  sleep 1
done
docker compose exec -T db pg_isready -U horatio >/dev/null 2>&1 || fail "Postgres did not start."

# --- backend ----------------------------------------------------------------------
cd "$ROOT/backend"
unset VIRTUAL_ENV  # use the project's own .venv, whatever shell this came from
say "Installing backend dependencies"
uv sync --quiet
say "Migrating the database"
uv run alembic upgrade head >"$LOGS/migrate.log" 2>&1 || fail "Migration failed; see $LOGS/migrate.log"
say "Loading the rule sets"
uv run python -m horatio.rules >"$LOGS/rules.log" 2>&1 || fail "Loading rules failed; see $LOGS/rules.log"

# Mail goes to the local Mailpit (http://localhost:8025), unless backend/.env or
# the environment names a real mail server.
if [[ -z "${HORATIO_SMTP_HOST:-}" ]] && ! grep -qs '^HORATIO_SMTP_HOST=' .env; then
  export HORATIO_SMTP_HOST=localhost HORATIO_SMTP_PORT=1025 HORATIO_SMTP_STARTTLS=false
  export HORATIO_MAIL_FROM="${HORATIO_MAIL_FROM:-Horatio <horatio@example.com>}"
fi

# Links in messages Horatio sends point at the app.
if [[ -z "${HORATIO_PUBLIC_URL:-}" ]] && ! grep -qs '^HORATIO_PUBLIC_URL=' .env; then
  export HORATIO_PUBLIC_URL="http://localhost:$APP_PORT"
fi

# Uploaded pictures are kept under .local/, unless backend/.env says elsewhere.
if [[ -z "${HORATIO_UPLOAD_DIR:-}" ]] && ! grep -qs '^HORATIO_UPLOAD_DIR=' .env; then
  export HORATIO_UPLOAD_DIR="$STATE/uploads"
  mkdir -p "$HORATIO_UPLOAD_DIR"
fi

say "Starting the API on :$API_PORT"
# setsid gives each server its own process group, so stop-local.sh can stop it
# together with its children (uvicorn's reloader, Vite's workers).
HORATIO_COOKIE_SECURE=false setsid nohup uv run uvicorn horatio.app:app --reload --port "$API_PORT" \
  >"$LOGS/api.log" 2>&1 < /dev/null &
echo $! >"$STATE/api.pid"

# --- frontend ---------------------------------------------------------------------
cd "$ROOT/frontend"
if [[ ! -f node_modules/.package-lock.json || package-lock.json -nt node_modules/.package-lock.json ]]; then
  say "Installing frontend dependencies"
  npm install --silent
fi
say "Starting the app on :$APP_PORT"
HORATIO_API_PORT="$API_PORT" setsid nohup npm run dev -- --port "$APP_PORT" --strictPort >"$LOGS/app.log" 2>&1 < /dev/null &
echo $! >"$STATE/app.pid"

# --- wait until both answer -----------------------------------------------------------
wait_for() {
  local name="$1" url="$2" log="$3"
  for _ in $(seq 1 60); do
    curl -sf "$url" >/dev/null 2>&1 && return 0
    running "$name" || fail "The $name stopped while starting; see $log"
    sleep 1
  done
  fail "The $name did not answer at $url; see $log"
}
wait_for api "http://localhost:$API_PORT/api/health" "$LOGS/api.log"
wait_for app "http://localhost:$APP_PORT/" "$LOGS/app.log"

if [[ -n "$custodian" ]]; then
  (cd "$ROOT/backend" && uv run python -m horatio.custodian "$custodian") \
    || say "Could not make $custodian custodian: sign up first, then run this again with --custodian."
fi

cat <<EOF

Horatio is running.
  App       http://localhost:$APP_PORT
  API docs  http://localhost:$API_PORT/docs
  Mail      http://localhost:8025 (unless backend/.env names a mail server)
  Logs      $LOGS/

After signing up, make yourself custodian (to create troupes):
  cd backend && uv run python -m horatio.custodian you@example.com

Stop everything with ./stop-local.sh
EOF
