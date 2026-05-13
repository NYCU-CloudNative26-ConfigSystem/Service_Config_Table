.PHONY: run migrate migrate-down migrate-new test lint

run:
	uvicorn main:app --reload --host 0.0.0.0 --port 18001

migrate:
	alembic upgrade head

migrate-down:
	alembic downgrade -1

migrate-new:
	alembic revision --autogenerate -m "$(message)"

test:
	pytest tests/ -v

lint:
	ruff check .
