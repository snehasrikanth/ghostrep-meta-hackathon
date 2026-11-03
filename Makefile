.PHONY: setup backend backend-dev frontend demo test check

setup:
	@test -f .env || cp .env.example .env
	cd backend && uv sync --frozen --group dev
	cd frontend && npm ci

backend:
	cd backend && uv run --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000

backend-dev:
	cd backend && uv run --frozen uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

demo:
	cd backend && uv run --frozen python -m app.demo seed

test:
	cd backend && uv run --frozen pytest
	cd frontend && npm test

check:
	cd frontend && npm run lint
	cd frontend && npx tsc --noEmit
	cd frontend && npm run build
