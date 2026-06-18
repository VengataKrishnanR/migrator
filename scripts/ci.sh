#!/usr/bin/env bash
# CI entrypoint — runs the offline V3 test suite (stub mode, no network).
# Usage: bash scripts/ci.sh
set -euo pipefail

cd "$(dirname "$0")/.."

# Prefer the project venv's interpreter; fall back to python3.
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

echo "Using interpreter: $PY"
"$PY" -m pytest tests/test_v3_workflow.py \
                tests/test_v3_ingestion.py \
                tests/test_v3_service.py \
                tests/test_v3_api.py \
                tests/test_v3_phase1.py \
                tests/test_v3_phase2.py \
                tests/test_v3_phase3.py \
                tests/test_v3_phase4.py \
                tests/test_v3_auth.py \
                -q
