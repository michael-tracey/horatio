#!/bin/bash
# Import a troupe's influence log from LotsLarp's old spreadsheet on the deployed site:
#   deploy/import-influence-log.sh SOURCE --troupe TROUPE [--dry-run] [--timezone ZONE]
# SOURCE is the spreadsheet downloaded as .xlsx (File > Download > Microsoft Excel),
# or a folder holding its "Elite Infl." and "UW Infl." tabs downloaded as CSV. It is
# copied into the horatio-api container, imported by horatio.import_influence_log,
# and removed again. Run it with --dry-run first to see what it would do.
set -euo pipefail
usage="usage: deploy/import-influence-log.sh SOURCE --troupe TROUPE [--dry-run] [--timezone ZONE]"
[[ $# -ge 1 && -e $1 ]] || { echo "$usage" >&2; exit 2; }
SOURCE=$(realpath "$1")
shift
NAME=$(basename "$SOURCE")
HOST_IP=$(gcloud storage cat gs://mtracey-tofu-state/infra/default.tfstate | jq -r '.outputs.host_ip.value')
on_host() {
  ssh -i "${HOME}/.ssh/ansible_gce_key" -o StrictHostKeyChecking=no "ansible@$HOST_IP" "$@"
}

DIR=$(on_host docker exec horatio-api mktemp -d)
trap 'on_host docker exec horatio-api rm -rf "$DIR"' EXIT
tar -C "$(dirname "$SOURCE")" -cf - "$NAME" | on_host docker exec -i horatio-api tar -C "$DIR" -xf -

ARGS=$(printf ' %q' "$DIR/$NAME" "$@")
on_host docker exec horatio-api python -m horatio.import_influence_log "$ARGS"
