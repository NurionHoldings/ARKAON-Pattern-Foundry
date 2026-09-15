.PHONY: install test lint run

install:
	pip install -e '.[dev]'

test:
	pytest -q

lint:
	ruff check src tests

run:
	uvicorn apf.api:app --reload

