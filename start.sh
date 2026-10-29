#!/usr/bin/env bash
# Single process: builds the frontend, then Flask serves the app and API on :5001 (macOS keeps :5000 for AirPlay).
# Open http://localhost:5001
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Creating Python environment…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r backend/requirements.txt
fi
(cd frontend && { [ -d node_modules ] || npm install; } && npm run build)

export DEMO_SIGNUP=${DEMO_SIGNUP:-1}  # test install: the sign-in page offers "Create a test account"
export PUBLIC_URL=${PUBLIC_URL:-http://localhost:5001}
if [ ! -f backend/creativeflow.db ]; then
  (cd backend && ../.venv/bin/flask --app app seed && ../.venv/bin/flask --app app seed-demo-calendar)
fi
cd backend && exec ../.venv/bin/flask --app app run -p 5001
