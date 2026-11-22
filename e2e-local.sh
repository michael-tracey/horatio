#!/usr/bin/env bash
# Run the Playwright suite locally against its own database, so test troupes and
# players never land in the one ./start-local.sh uses. The `horatio_e2e`
# database is made afresh in the same Postgres container on every run.
#
#   ./e2e-local.sh                   build the app, then run every test
#   ./e2e-local.sh --no-build        reuse frontend/dist as it is
#   ./e2e-local.sh --parallel        run in a stack of its own, beside other runs
#   ./e2e-local.sh -- --project=phone   pass the rest to `playwright test`
#
# Port: HORATIO_E2E_PORT (default 8766). Needs Docker, uv and Node 22.
#
# --parallel (or HORATIO_E2E_PARALLEL=1) waits for one of HORATIO_E2E_SLOTS
# slots (default 2) to come free, or takes slot HORATIO_E2E_SLOT=N. Slot N runs
# its own Postgres in compose project horatio-e2e-N (compose.e2e.yaml) on port
# 18032+100*N, and the API on 18066+100*N; the stack and its volume are removed
# when the run ends. The slot locks are in HORATIO_E2E_LOCK_DIR (default
# $XDG_RUNTIME_DIR/horatio-e2e), shared by every worktree on the machine.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${HORATIO_E2E_PORT:-8766}"
DB=horatio_e2e
DB_PORT=54329
LOG="$ROOT/.local/logs/e2e-api.log"
UPLOADS="$ROOT/.local/e2e-uploads"

build=true
parallel=false
[[ -n "${HORATIO_E2E_SLOT:-}" || "${HORATIO_E2E_PARALLEL:-}" == 1 ]] && parallel=true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) build=false ;;
    --parallel) parallel=true ;;
    --) shift; break ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) break ;;
  esac
  shift
done

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
listening() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

if $parallel; then
  # Build before taking a slot, so a slot is held only while tests can run in it.
  if $build; then
    say "Building the app"
    (cd "$ROOT/frontend" && npm run -s build >/dev/null)
    build=false
  fi

  SLOTS="${HORATIO_E2E_SLOTS:-2}"
  LOCKS="${HORATIO_E2E_LOCK_DIR:-${XDG_RUNTIME_DIR:-/tmp}/horatio-e2e}"
  mkdir -p "$LOCKS"
  [[ "$SLOTS" =~ ^[1-9][0-9]*$ ]] || fail "HORATIO_E2E_SLOTS must be a number from 1."
  # The lock is held on fd 9 until this script exits. A slot whose API port is
  # taken (by a server a killed run left behind, say) is passed over.
  slot=""
  passed=" "
  try_slot() {
    exec 9>"$LOCKS/.e2e-slot-$1.lock"
    if flock -n 9; then
      if ! listening $((18066 + 100 * $1)); then slot=$1; return 0; fi
      [[ "$passed" == *" $1 "* ]] || say "Slot $1's port $((18066 + 100 * $1)) is in use by something else; passing it over"
      passed+="$1 "
    fi
    exec 9>&-
    return 1
  }
  if [[ -n "${HORATIO_E2E_SLOT:-}" ]]; then
    n="$HORATIO_E2E_SLOT"
    [[ "$n" =~ ^[1-9][0-9]*$ ]] && ((n <= SLOTS)) || fail "HORATIO_E2E_SLOT must be a number from 1 to $SLOTS."
    exec 9>"$LOCKS/.e2e-slot-$n.lock"
    flock -n 9 || { say "Waiting for e2e slot $n"; flock 9; }
    slot=$n
    if listening $((18066 + 100 * n)); then fail "Something is already listening on port $((18066 + 100 * n))."; fi
  else
    waited=false
    until [[ -n "$slot" ]]; do
      for n in $(seq 1 "$SLOTS"); do try_slot "$n" && break; done
      [[ -n "$slot" ]] && break
      $waited || say "All the e2e slots ($SLOTS) are busy; waiting for one to come free"
      waited=true
      sleep 5
    done
  fi

  PORT=$((18066 + 100 * slot))
  DB_PORT=$((18032 + 100 * slot))
  PROJECT="horatio-e2e-$slot"
  LOG="$ROOT/.local/logs/e2e-api-slot-$slot.log"
  UPLOADS="$ROOT/.local/e2e-uploads-slot-$slot"
  export HORATIO_E2E_DB_PORT="$DB_PORT"
  stack() { docker compose -p "$PROJECT" -f "$ROOT/compose.e2e.yaml" "$@"; }
  remove_stack() { stack down -v --remove-orphans >/dev/null 2>&1 || true; }
  say "Slot $slot: compose project $PROJECT, Postgres on :$DB_PORT, API on :$PORT"
else
  if listening "$PORT"; then fail "Something is already listening on port $PORT."; fi
fi
mkdir -p "$(dirname "$LOG")"

cd "$ROOT"
if $parallel; then
  # Whatever a killed run left in this slot goes first: the slot is ours now.
  remove_stack
  trap remove_stack EXIT
  say "Starting Postgres"
  stack up -d db >/dev/null
  # Over TCP: during its first start the image runs a server on the socket alone.
  for _ in $(seq 1 60); do
    stack exec -T db pg_isready -h 127.0.0.1 -U horatio -d "$DB" >/dev/null 2>&1 && break
    sleep 1
  done
  stack exec -T db pg_isready -h 127.0.0.1 -U horatio -d "$DB" >/dev/null 2>&1 || fail "Postgres did not start."
else
  say "Starting Postgres"
  docker compose up -d >/dev/null
  for _ in $(seq 1 60); do
    docker compose exec -T db pg_isready -U horatio >/dev/null 2>&1 && break
    sleep 1
  done
  say "Making a fresh $DB database"
  docker compose exec -T db psql -U horatio -d postgres -q \
    -c "drop database if exists $DB with (force)" -c "create database $DB owner horatio" >/dev/null
fi

export HORATIO_DATABASE_URL="postgresql+psycopg://horatio:horatio@localhost:$DB_PORT/$DB"
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
# Pictures go in a fresh directory of their own, like the database. No limits on
# sign-ins and sign-ups (horatio.auth.attempts): every test signs up from here.
# Keep-alive: Playwright's request contexts keep idle connections open with no
# timeout of their own, so with uvicorn's 5 s one, a call made just as the server
# drops the connection fails with ECONNRESET. 300 s outlasts the longest test.
# The custodian isn't held to two-step sign-in: tests make custodians partway through,
# already signed in. Authenticator apps get a key of the suite's own, and passkeys
# are signed for the address the suite opens. Nobody hears of new blog articles on
# the bell (horatio.blog_bell): a notice to every account would change the bell's
# count in whatever other test is running then.
E2E_TOTP_KEY="ZTJlIG9ubHk6IG5vdCBhIHJlYWwga2V5ICEhISEhISE="
rm -rf "$UPLOADS" && mkdir -p "$UPLOADS"
HORATIO_COOKIE_SECURE=false HORATIO_FRONTEND_DIST="$ROOT/frontend/dist" HORATIO_UPLOAD_DIR="$UPLOADS" \
  HORATIO_AUTH_LIMITS=false HORATIO_TWO_STEP_FOR_CUSTODIANS=false HORATIO_TOTP_KEY="$E2E_TOTP_KEY" \
  HORATIO_WEBAUTHN_ORIGIN="http://localhost:$PORT" \
  HORATIO_DISCORD_BOT_TOKEN= HORATIO_SMTP_HOST= HORATIO_DARK_PACK_DIR= HORATIO_BLOG_BELL=false \
  setsid uv run uvicorn horatio.app:app --port "$PORT" --timeout-keep-alive 300 >"$LOG" 2>&1 < /dev/null 9>&- &
api=$!
stop_api() {
  kill -TERM -- "-$api" 2>/dev/null || kill -TERM "$api" 2>/dev/null || true
  wait "$api" 2>/dev/null || true
}
if $parallel; then
  trap 'stop_api; remove_stack' EXIT
else
  trap stop_api EXIT
fi
for _ in $(seq 1 30); do
  curl -sf "localhost:$PORT/api/health" >/dev/null && break
  sleep 1
done
curl -sf "localhost:$PORT/api/health" >/dev/null || fail "The API did not start; see $LOG"

cd "$ROOT/frontend"
if $parallel; then
  # Results of a slot of their own, so two runs from one worktree keep theirs.
  set -- --output "test-results-slot-$slot" "$@"
fi
HORATIO_E2E_URL="http://localhost:$PORT" npx playwright test "$@"
