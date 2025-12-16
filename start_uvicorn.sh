#!/usr/bin/env bash
set -euo pipefail

# Start the FastAPI application with uvicorn.
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info
