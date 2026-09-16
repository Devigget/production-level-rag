#!/usr/bin/env sh
set -eu

compose="docker compose"

for service in backend frontend qdrant neo4j; do
    status=$($compose ps --status running --services | grep -Fx "$service" || true)
    if [ "$status" != "$service" ]; then
        echo "Service is not running: $service" >&2
        $compose ps
        exit 1
    fi
done

curl --fail --silent --show-error http://localhost:8000/api/health > /dev/null
curl --fail --silent --show-error http://localhost:3000/ > /dev/null
curl --fail --silent --show-error http://localhost:6333/readyz > /dev/null

echo "All containers are running and responding."