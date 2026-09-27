#!/usr/bin/env bash
# Start the CI-Sense API (port 8787) and web UI (port 5173) together; Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."

uvicorn server.app:app --port 8787 &
api=$!
trap 'kill $api 2>/dev/null' EXIT

cd web
[ -d node_modules ] || npm install
npm run dev
