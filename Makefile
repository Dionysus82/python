PYTHON ?= .venv/bin/python
export PYTHONPATH := .

.PHONY: setup seed test evaluation lint api ui docker

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

seed:
	$(PYTHON) scripts/seed_database.py

test:
	$(PYTHON) -m pytest

evaluation:
	$(PYTHON) scripts/run_evaluation.py

lint:
	$(PYTHON) -m ruff check app scripts synthetic_data tests

api:
	$(PYTHON) -m uvicorn app.api.app:app --host 0.0.0.0 --port 8000

ui:
	$(PYTHON) -m streamlit run app/ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8501

docker:
	docker compose up --build
