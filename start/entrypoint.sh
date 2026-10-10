#!/bin/sh
set -eu
cd /app
export PYTHONPATH=/app
mkdir -p data
if [ ! -f data/harbour_meridian.db ]; then
  python scripts/bootstrap.py
fi
python -m uvicorn app.api.app:app --host 0.0.0.0 --port 8000 &
exec python -m streamlit run app/ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
