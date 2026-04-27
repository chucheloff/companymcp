COMPOSE ?= docker compose
SERVICE ?= company-api

.PHONY: help build up down restart logs ps pull clean test shell health

help:
	@echo "Targets:"
	@echo "  make build     - Build container images"
	@echo "  make up        - Start all services in background"
	@echo "  make down      - Stop and remove services"
	@echo "  make restart   - Restart all services"
	@echo "  make logs      - Follow compose logs"
	@echo "  make ps        - Show compose service status"
	@echo "  make pull      - Pull base images"
	@echo "  make clean     - Remove containers, volumes, and orphans"
	@echo "  make test      - Run pytest in uv environment"
	@echo "  make shell     - Open shell in app container"
	@echo "  make health    - Check app health endpoint"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down && $(COMPOSE) up -d --build

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

pull:
	$(COMPOSE) pull

clean:
	$(COMPOSE) down -v --remove-orphans

test:
	uv run pytest -q

shell:
	$(COMPOSE) exec $(SERVICE) sh

health:
	curl -fsS http://localhost:8080/healthz && echo ""
