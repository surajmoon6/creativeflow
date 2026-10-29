#!/usr/bin/env bash
# Development: Flask API on :5001 (macOS keeps :5000 for AirPlay) with auto-reload + Vite on :5173.
# Open http://localhost:5173
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating Python environment…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r backend/requirements.txt
fi
[ -d frontend/node_modules ] || (cd frontend && npm install)

export DEMO_SIGNUP=${DEMO_SIGNUP:-1}  # test install: the sign-in page offers "Create a test account"
export PUBLIC_URL=${PUBLIC_URL:-http://localhost:5173}
if [ ! -f backend/creativeflow.db ]; then
  (cd backend && ../.venv/bin/flask --app app seed && ../.venv/bin/flask --app app seed-demo-calendar)
fi

(cd backend && ../.venv/bin/flask --app app run -p 5001 --debug) &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd frontend && npm run dev
