#!/bin/bash
# Start the World Cup predictor app with gunicorn
set -e
cd "$(dirname "$0")"
source .env 2>/dev/null || true
mkdir -p logs
exec gunicorn app:app \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --timeout 30 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log \
    --log-level info
