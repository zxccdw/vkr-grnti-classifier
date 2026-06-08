#!/usr/bin/env bash
set -euo pipefail

# YC_REGISTRY_ID, YC_CONTAINER_ID, YC_SA_ID, YC_CONTAINER_NAME — from ~/.zshrc

IMAGE="cr.yandex/${YC_REGISTRY_ID}/${YC_CONTAINER_NAME}:latest"

# Skip vars that are only used locally
SKIP_PATTERN='^(TEI_|EMBEDDING_MODEL|WEB_HOST_PORT)'

# Build --environment flags from .env (app vars only)
ENV_FLAGS=()
while IFS='=' read -r key value; do
  [[ -z "${key}" || "${key}" =~ ^# ]] && continue
  [[ "${key}" =~ $SKIP_PATTERN ]] && continue
  [[ -z "${value}" ]] && continue
  ENV_FLAGS+=("--environment" "${key}=${value}")
done < .env

echo "=== Building image for linux/amd64 ==="
docker buildx build \
  --platform linux/amd64 \
  --tag "${IMAGE}" \
  --push \
  .

echo "=== Deploying revision ==="
yc serverless container revision deploy \
  --container-id "${YC_CONTAINER_ID}" \
  --image "${IMAGE}" \
  --cores 1 \
  --memory 512MB \
  --concurrency 4 \
  --execution-timeout 300s \
  --service-account-id "${YC_SA_ID}" \
  "${ENV_FLAGS[@]}"

echo "=== Done ==="
yc serverless container get "${YC_CONTAINER_NAME}" --format json | jq -r '.url'
