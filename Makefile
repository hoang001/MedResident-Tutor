.PHONY: up down logs migrate seed test lint
up:
	docker compose up --build
down:
	docker compose down
logs:
	docker compose logs -f
migrate:
	docker compose run --rm backend alembic upgrade head
seed:
	docker compose run --rm backend python -m app.scripts.seed
test:
	docker compose run --rm backend pytest
lint:
	docker compose run --rm backend ruff check app tests
	docker compose run --rm frontend npm run lint

