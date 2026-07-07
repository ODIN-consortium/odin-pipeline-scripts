#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir=$(dirname "${SCRIPT_DIR}")
docker_compose_file="${root_dir}/enlighten/docker-compose.yml"
docker_compose_dir=$(dirname "${docker_compose_file}")

cd "${docker_compose_dir}" || exit 1

# Name of your compose project (defaults to directory name if not set)
PROJECT_NAME=${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}

echo "Bringing down docker compose project: $PROJECT_NAME"
docker compose down || true

# Find any leftover containers from this project
LEFTOVER_CONTAINERS=$(docker ps -a --filter "label=com.docker.compose.project=$PROJECT_NAME" -q)

if [ -n "$LEFTOVER_CONTAINERS" ]; then
  echo "Stopping and removing leftover containers:"
  echo "$LEFTOVER_CONTAINERS"
  docker stop $LEFTOVER_CONTAINERS || true
  docker rm -f $LEFTOVER_CONTAINERS || true
else
  echo "No leftover containers found."
fi
