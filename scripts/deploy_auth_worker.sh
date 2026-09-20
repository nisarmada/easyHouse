#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKER_DIR="$ROOT/cloudflare/auth-worker"

if [[ -f "$ROOT/.env" ]]; then
  eval "$(ROOT="$ROOT" python3 - <<'PY'
import os
import shlex
import sys
from pathlib import Path

sys.path.insert(0, os.environ["ROOT"])
from config.env import load_dotenv

load_dotenv(Path(os.environ["ROOT"]) / ".env")
for key in ("SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
    value = os.environ.get(key, "")
    if value:
        print(f"export {key}={shlex.quote(value)}")
PY
)"
fi

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required (install Node.js first)" >&2
  exit 1
fi

cd "$WORKER_DIR"
npm install

if ! npx wrangler whoami >/dev/null 2>&1; then
  echo "Log in to Cloudflare first:"
  echo "  cd cloudflare/auth-worker && npx wrangler login"
  exit 1
fi

if ! npx wrangler d1 info easyhouse-auth >/dev/null 2>&1; then
  echo "Creating D1 database easyhouse-auth …"
  npx wrangler d1 create easyhouse-auth
  echo "Update database_id in cloudflare/auth-worker/wrangler.jsonc, then re-run this script."
  exit 0
fi

npx wrangler d1 execute easyhouse-auth --remote --file=./schema.sql

if [[ -z "${SMTP_USER:-}" || -z "${SMTP_PASSWORD:-}" ]]; then
  echo "Set Gmail app password secrets before deploy:"
  echo "  export SMTP_USER=you@gmail.com"
  echo "  export SMTP_PASSWORD=your-gmail-app-password"
  echo "  export SMTP_FROM='easyHouse <you@gmail.com>'  # optional"
  exit 1
fi

printf '%s' "$SMTP_USER" | npx wrangler secret put SMTP_USER
printf '%s' "$SMTP_PASSWORD" | npx wrangler secret put SMTP_PASSWORD
# SMTP_FROM is a plain var in wrangler.jsonc — do not upload as a secret.

DEPLOY_OUTPUT="$(npx wrangler deploy 2>&1 | tee /dev/stderr)"
WORKER_URL="$(echo "$DEPLOY_OUTPUT" | grep -Eo 'https://[a-zA-Z0-9.-]+\.workers\.dev' | head -1 || true)"
if [[ -z "$WORKER_URL" ]]; then
  echo "Could not detect worker URL from deploy output. Set it manually with scripts/set_auth_url.py" >&2
  exit 1
fi

AUTH_JSON="$HOME/.easyhouse/auth.json"
mkdir -p "$(dirname "$AUTH_JSON")"
cat > "$AUTH_JSON" <<EOF
{
  "auth_url": "$WORKER_URL"
}
EOF
chmod 600 "$AUTH_JSON"
echo "Saved auth URL to $AUTH_JSON"
