#!/usr/bin/env bash
# Build the database and start the API server.
set -e
echo "Building catalogue database from MEI XML..."
python3 transform/pipeline.py data catalogue.db
echo ""
echo "Starting API at http://localhost:8000 (docs at /docs)"
uvicorn api.main:app --reload
