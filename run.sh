#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
  echo 'First run: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt'
  exit 1
fi
exec .venv/bin/python -m uvicorn splitwise_receipts.server:app --host 127.0.0.1 --port 8010
