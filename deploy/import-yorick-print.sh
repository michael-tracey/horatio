#!/bin/bash
# Import a troupe's characters from Yorick's Print Characters page on the deployed site:
#   deploy/import-yorick-print.sh PAGE --troupe TROUPE [--dry-run] [--names TABLE.toml]
#       [--as HANDLE]
# PAGE is the page saved from the browser as HTML, with its "_files" folder (the
# portraits) beside it. Both, and any --names table, are copied into the horatio-api
# container, imported by horatio.import_yorick_print, and removed again. The report
# and the JSON come back into yorick-import/ beside PAGE: keep them out of git, as
# they hold what the page holds. Run it with --dry-run first.
set -euo pipefail
usage="usage: deploy/import-yorick-print.sh PAGE --troupe TROUPE [--dry-run] [--names TABLE.toml] [--as HANDLE]"
[[ $# -ge 1 && -f $1 ]] || { echo "$usage" >&2; exit 2; }
SOURCE=$(realpath "$1")
shift
HERE=$(dirname "$SOURCE")
NAME=$(basename "$SOURCE")
FILES="${NAME%.*}_files"
HOST_IP=$(gcloud storage cat gs://mtracey-tofu-state/infra/default.tfstate | jq -r '.outputs.host_ip.value')
on_host() {
  ssh -i "${HOME}/.ssh/ansible_gce_key" -o StrictHostKeyChecking=no "ansible@$HOST_IP" "$@"
}
copy_in() {  # copy_in FOLDER NAME...: into the container's import folder
  tar -C "$1" -cf - "${@:2}" | on_host docker exec -i horatio-api tar -C "$DIR" -xf -
}

DIR=$(on_host docker exec horatio-api mktemp -d)
trap 'on_host docker exec horatio-api rm -rf "$DIR"' EXIT
if [[ -d "$HERE/$FILES" ]]; then copy_in "$HERE" "$NAME" "$FILES"; else copy_in "$HERE" "$NAME"; fi

args=()
while [[ $# -gt 0 ]]; do
  if [[ $1 == --names && $# -ge 2 ]]; then
    TABLE=$(realpath "$2")
    copy_in "$(dirname "$TABLE")" "$(basename "$TABLE")"
    args+=(--names "$DIR/$(basename "$TABLE")")
    shift 2
  else
    args+=("$1")
    shift
  fi
done

ARGS=$(printf ' %q' "$DIR/$NAME" --out "$DIR/out" "${args[@]}")
status=0
on_host docker exec horatio-api python -m horatio.import_yorick_print "$ARGS" || status=$?
mkdir -p "$HERE/yorick-import"
on_host docker exec horatio-api tar -C "$DIR/out" -cf - . | tar -C "$HERE/yorick-import" -xf - \
  || echo "No report came back." >&2
exit "$status"
