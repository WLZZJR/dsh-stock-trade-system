.PHONY: lint format typecheck test test-integration audit secret-scan ci install-hooks check-config up down migrate
PY_DIRS := apps packages tests
COMPOSE_FILE := deploy/compose/docker-compose.dev.yml
# Load .env (if present) for runtime commands only; tests never read it.
ENV_FILE := $(if $(wildcard .env),--env-file .env,)

lint:
	uv run ruff check $(PY_DIRS)
	uv run ruff format --check $(PY_DIRS)
	PYTHONPATH=packages:apps uv run lint-imports

format:
	uv run ruff format $(PY_DIRS)
	uv run ruff check --fix $(PY_DIRS)

typecheck:
	uv run mypy apps packages

test:
	uv run pytest -m "not integration" --cov --cov-report=term-missing

# Needs a real PostgreSQL 16: `make up`, then GEI_DATABASE_URL pointing at it.
test-integration:
	uv run $(ENV_FILE) pytest -m integration --no-cov

ci: lint typecheck test

# Known-vulnerability scan of the locked dependency set (hash-pinned export).
audit:
	uv export --frozen --no-emit-project 2>/dev/null | uv run pip-audit -r /dev/stdin --disable-pip

# Secret scan of the working tree and git history (gitleaks, pinned image).
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1
secret-scan:
	docker run --rm -v "$(CURDIR):/repo" $(GITLEAKS_IMAGE) detect --source /repo --redact --verbose

# Installs pre-commit and pre-push hooks into .git/hooks (not versioned by git).
install-hooks:
	uv run pre-commit install

check-config:
	PYTHONPATH=packages uv run $(ENV_FILE) python -m application.config

up:
	@test -f $(COMPOSE_FILE) || { echo "missing $(COMPOSE_FILE) (created in P1-05)"; exit 1; }
	docker compose $(ENV_FILE) -f $(COMPOSE_FILE) up -d --build --wait

down:
	@test -f $(COMPOSE_FILE) || { echo "missing $(COMPOSE_FILE) (created in P1-05)"; exit 1; }
	docker compose $(ENV_FILE) -f $(COMPOSE_FILE) down

migrate:
	@test -f alembic.ini || { echo "missing alembic.ini (created in P1-10)"; exit 1; }
	PYTHONPATH=packages:apps uv run $(ENV_FILE) alembic upgrade head
