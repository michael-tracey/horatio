#!/usr/bin/env bash
# Stop what ./start-local.sh started: the app, the API and Postgres.
# Data stays in the database volume; ./start-local.sh --reset wipes it.
#
#   ./stop-local.sh            stop everything
#   ./stop-local.sh --keep-db  stop the servers but leave Postgres running
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE="$ROOT/.local"

keep_db=false
case "${1:-}" in
  --keep-db) keep_db=true ;;
  "") ;;
  -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
  *) echo "Unknown option: $1 (try --help)" >&2; exit 2 ;;
esac

say() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }

stop() {
  local name="$1" pidfile="$STATE/$1.pid"
  if [[ ! -f "$pidfile" ]]; then
    return
  fi
  local pid
  pid="$(cat "$pidfile")"
  if kill -0 "$pid" 2>/dev/null; then
    say "Stopping the $name"
    # The server was started in its own process group; stop the whole group.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    kill -KILL -- "-$pid" 2>/dev/null || true
  fi
  rm -f "$pidfile"
}

stop app
stop api

if ! $keep_db; then
  say "Stopping Postgres"
  (cd "$ROOT" && docker compose stop >/dev/null 2>&1) || true
fi
say "Stopped."
