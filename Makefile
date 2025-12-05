COMPOSE_DEV=docker-compose
COMPOSE_PROD=docker-compose -f docker-compose.prod.yml --env-file .env

.PHONY: up-prod up-dev down logs logs-all migrate shell test clean secrets

up-prod:
	$(COMPOSE_PROD) up -d --build

down-prod:
	$(COMPOSE_PROD) down

up-dev:
	$(COMPOSE_DEV) up --build

down:
	$(COMPOSE_DEV) down

logs:
	$(COMPOSE_DEV) logs -f backend worker

logs-all:
	$(COMPOSE_DEV) logs -f

logs-prod:
	$(COMPOSE_PROD) logs -f backend worker

migrate:
	$(COMPOSE_DEV) run --rm migrations alembic upgrade head

migrate-prod:
	$(COMPOSE_PROD) exec backend alembic upgrade head

shell:
	$(COMPOSE_DEV) exec backend sh

test:
	./scripts/test-backend.sh && ./scripts/test-frontend.sh

clean:
	$(COMPOSE_DEV) down -v --remove-orphans

secrets:
	@mkdir -p secrets
	@test -f secrets/jwt_secret || openssl rand -hex 32 > secrets/jwt_secret
	@echo "Secrets generated under ./secrets (fill GEMINI_API_KEY, DB/Redis URLs as needed)"

demo:
	docker-compose -f docker-compose.demo.yml up --build

demo-down:
	docker-compose -f docker-compose.demo.yml down -v --remove-orphans
