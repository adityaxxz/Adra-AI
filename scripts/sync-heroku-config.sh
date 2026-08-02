#!/usr/bin/env bash
# Push config vars from .env.prod (local, gitignored) to a Heroku app's config.
# Never prints secret values to the terminal.
#
# Usage: bash scripts/sync-heroku-config.sh <heroku-app-name>

set -euo pipefail

APP_NAME="${1:?Usage: sync-heroku-config.sh <heroku-app-name>}"
ENV_FILE="$(dirname "$0")/../.env.prod"

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE not found" >&2
  exit 1
fi

VARS_TO_SYNC=(
  # NOTE: DATABASE_URL and POSTGRES_PASSWORD are intentionally NOT listed here.
  # DATABASE_URL is auto-set by the Heroku Postgres addon — pushing a local value
  # here would overwrite it with the wrong (droplet/local) connection string.
  # POSTGRES_PASSWORD is a droplet/local-only var not read by the backend on Heroku.
  QDRANT_URL
  QDRANT_API_KEY
  SECRET_KEY
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET
  GITHUB_OAUTH_CLIENT_ID
  GITHUB_OAUTH_CLIENT_SECRET
  FRONTEND_URL
  ALLOWED_ORIGINS
  LLM_PROVIDER
  GROQ_API_KEY
  GOOGLE_API_KEY
  NVIDIA_API_KEY
  LLM_MIN_INTERVAL_SEC
  LLM_MAX_RETRIES
  LLM_MAX_CONTENT_CHARS
  ADMIN_EMAILS
  LANGSMITH_TRACING_V2
  LANGSMITH_ENDPOINT
  LANGSMITH_API_KEY
  LANGSMITH_PROJECT
)

for VAR in "${VARS_TO_SYNC[@]}"; do
  VALUE=$(grep "^${VAR}=" "$ENV_FILE" | cut -d '=' -f2- || true)
  if [ -n "$VALUE" ]; then
    heroku config:set "${VAR}=${VALUE}" -a "$APP_NAME" >/dev/null
    echo "set ${VAR}"
  else
    echo "skipped ${VAR} (not set in .env.prod)"
  fi
done
