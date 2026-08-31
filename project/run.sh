#!/usr/bin/env bash
# Build the database and start the server (web UI + API).
set -e
echo "Building catalogue database from MEI XML..."
python3 transform/pipeline.py data catalogue.db
echo ""
echo "Starting server at http://localhost:8000"
echo "  Web interface:     http://localhost:8000/"
echo "  API documentation: http://localhost:8000/docs"
uvicorn api.main:app --reload
