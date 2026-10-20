#!/bin/bash
# Deploy Horatio to the shared docker host (the infra repo's docker-host), the way
# codex-mysterium and the lotslarp bot deploy: build the image with Cloud Build,
# push it to Artifact Registry in the lotslarp project, then run
# deploy/playbook.yml against the host. See deploy/README.md.
#
#   deploy/deploy.sh             build and deploy
#   deploy/deploy.sh --no-build  redeploy the image already tagged latest
set -euo pipefail

GCP_PROJECT_ID=lotslarp
GCP_REGION=us-east1
ARTIFACT_REGISTRY_REPO=horatio
SERVICE_NAME=horatio
SSH_KEY_PATH="${HOME}/.ssh/ansible_gce_key"

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$DEPLOY_DIR")"
ENV_FILE="$DEPLOY_DIR/production.env"
IMAGE="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT_ID/$ARTIFACT_REGISTRY_REPO/$SERVICE_NAME"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || fail "$ENV_FILE not found. Copy production.env.example and fill it in."
setting() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
db_password="$(setting HORATIO_DB_PASSWORD)"
(( ${#db_password} >= 16 )) || fail "HORATIO_DB_PASSWORD in production.env must be 16 characters or more."
[[ -n "$(setting HORATIO_LETSENCRYPT_EMAIL)" ]] || fail "HORATIO_LETSENCRYPT_EMAIL in production.env is empty."
[[ -n "$(setting HORATIO_PUBLIC_URL)" ]] || fail "HORATIO_PUBLIC_URL in production.env is empty."
[[ -f "$SSH_KEY_PATH" ]] || fail "SSH key $SSH_KEY_PATH not found (the infra repo's ansible key)."

HOST_IP=$(gcloud storage cat gs://mtracey-tofu-state/infra/default.tfstate | jq -r '.outputs.host_ip.value')
[[ -n "$HOST_IP" && "$HOST_IP" != null ]] || fail "Could not read the host IP from the infra Tofu state."

cd "$ROOT"
if [[ "${1:-}" != "--no-build" ]]; then
  COMMIT="$(git rev-parse HEAD)"
  if [[ -n "$(git status --porcelain -- backend frontend Dockerfile)" ]]; then
    echo "Warning: backend/, frontend/ or the Dockerfile have uncommitted changes; they will be deployed."
    COMMIT="$COMMIT-dirty"
  fi
  TAG="$(git rev-parse --short HEAD)-$(date -u +%Y%m%d%H%M)"
  echo "--- Building $IMAGE:$TAG with Cloud Build ---"
  gcloud builds submit \
    --project="$GCP_PROJECT_ID" --region="$GCP_REGION" \
    --config=deploy/cloudbuild.yaml \
    --substitutions="_SERVICE_NAME=$SERVICE_NAME,_REGION=$GCP_REGION,_ARTIFACT_REGISTRY_REPO=$ARTIFACT_REGISTRY_REPO,_TAG=$TAG,_COMMIT=$COMMIT,_BUILT_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    .
  DEPLOY_IMAGE="$IMAGE:$TAG"
else
  DEPLOY_IMAGE="$IMAGE:latest"
fi

INVENTORY=$(mktemp)
trap 'rm -f "$INVENTORY"' EXIT
cat > "$INVENTORY" <<INV
[horatio]
$HOST_IP ansible_user=ansible ansible_ssh_private_key_file=$SSH_KEY_PATH ansible_python_interpreter=/usr/bin/python3 ansible_ssh_common_args='-o StrictHostKeyChecking=no'
INV

echo "--- Deploying $DEPLOY_IMAGE to $HOST_IP ---"
ansible-playbook -i "$INVENTORY" "$DEPLOY_DIR/playbook.yml" \
  --extra-vars "docker_image=$DEPLOY_IMAGE env_file_src=$ENV_FILE"

echo "--- Removing all but the newest 5 images from Artifact Registry ---"
gcloud artifacts docker images list "$IMAGE" --project="$GCP_PROJECT_ID" \
  --include-tags --sort-by="~UPDATE_TIME" --format="value(DIGEST)" | tail -n +6 \
  | while read -r digest; do
      gcloud artifacts docker images delete "$IMAGE@$digest" \
        --project="$GCP_PROJECT_ID" --delete-tags --quiet || true
    done

echo "Deployed: $(setting HORATIO_PUBLIC_URL)"
