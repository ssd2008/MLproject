.PHONY: install install-ml dev infra migrate run test lint smoke

install:
	python -m pip install -r requirements-runtime.lock.txt

install-ml:
	python -m pip install -r requirements-ml.lock.txt

dev:
	python -m pip install -r requirements-dev.lock.txt

infra:
	docker compose up -d postgres qdrant

migrate:
	python -m scripts.migrate

run:
	uvicorn app.main:app --reload

test:
	python -m pytest

lint:
	ruff check .

smoke:
	python -m scripts.smoke_test
