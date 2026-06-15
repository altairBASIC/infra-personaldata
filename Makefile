COMPOSE := $(shell command -v docker >/dev/null 2>&1 && echo "docker compose" || echo "podman compose")
ENGINE := $(shell command -v docker >/dev/null 2>&1 && echo "docker" || echo "podman")

.PHONY: up down test lint clean logs status

up:
	$(COMPOSE) -f compose.yml up --build

up-detach:
	$(COMPOSE) -f compose.yml up --build -d

down:
	$(COMPOSE) -f compose.yml down -v

test:
	$(ENGINE) run --rm \
		-v $$(pwd):/app \
		-w /app \
		--entrypoint "" \
		python:3.12-slim \
		sh -c "pip install --no-cache-dir -r requirements.txt -q && python -m pytest tests/ -v"

lint:
	$(ENGINE) run --rm \
		-v $$(pwd):/app \
		-w /app \
		--entrypoint "" \
		python:3.12-slim \
		sh -c "pip install ruff -q && ruff check ."

clean:
	$(COMPOSE) -f compose.yml down -v --rmi local
	rm -rf data/silver data/chroma data/metrics
	rm -f linaje.json

logs:
	$(COMPOSE) -f compose.yml logs -f

status:
	$(COMPOSE) -f compose.yml ps
