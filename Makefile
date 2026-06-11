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
	@test -f secrets/gemini_api_key || : > secrets/gemini_api_key
	@test -f secrets/database_url || printf '%s' 'postgresql+psycopg2://rag:changeme_local_only@db:5432/rag' > secrets/database_url
	@test -f secrets/redis_url || printf '%s' 'redis://redis:6379/0' > secrets/redis_url
	@test -f secrets/postgres_password || printf '%s' 'changeme_local_only' > secrets/postgres_password
	@echo "Secrets generated under ./secrets (write a real Gemini key to secrets/gemini_api_key when GEMINI_MOCK_MODE=false)"

demo:
	docker-compose -f docker-compose.demo.yml up --build

demo-down:
	docker-compose -f docker-compose.demo.yml down -v --remove-orphans
