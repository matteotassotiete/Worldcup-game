#!/bin/bash
# Run the app LOCALLY against an isolated sqlite DB (mock_bracket.db).
# This never touches production — DATABASE_URL is forced empty so the app
# ignores the Neon URL in .env and uses local sqlite instead.
#
#   ./run_local.sh        -> http://localhost:8000
#
# Pair with: python3 scripts/mock_bracket.py {open|simulate|reset|status}
set -e
cd "$(dirname "$0")"

export DATABASE_URL=                       # force sqlite (overrides .env's Neon URL)
export DB_PATH="$(pwd)/mock_bracket.db"
export SECRET_KEY="${SECRET_KEY:-local-dev-secret}"
export ADMIN_KEY="${ADMIN_KEY:-local-admin}"
export FOOTBALL_DATA_TOKEN="${FOOTBALL_DATA_TOKEN:-unused-locally}"

echo "Local app → http://localhost:8000"
echo "Local DB  → $DB_PATH  (production is untouched)"
python3 app.py
