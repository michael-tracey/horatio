#!/bin/bash
# Make an existing account the custodian on the deployed site:
#   deploy/custodian.sh someone@example.com
# They sign up on the site first. The custodian can do anything, so this is only
# possible from a machine with the host's SSH key.
set -euo pipefail
[[ $# -eq 1 ]] || { echo "usage: deploy/custodian.sh EMAIL" >&2; exit 2; }
HOST_IP=$(gcloud storage cat gs://mtracey-tofu-state/infra/default.tfstate | jq -r '.outputs.host_ip.value')
ssh -i "${HOME}/.ssh/ansible_gce_key" -o StrictHostKeyChecking=no "ansible@$HOST_IP" \
  docker exec horatio-api python -m horatio.custodian "$(printf '%q' "$1")"
