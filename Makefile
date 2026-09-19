.PHONY: bootstrap lint test test-unit build docker-up docker-down help

help:
	@echo "bootstrap lint test build docker-up docker-down"

bootstrap:
	python -m pip install -U pip
	pip install -e ".[dev]" || pip install -e .
	@echo "bootstrap done (install Docker Desktop separately for ground_iot)"

lint:
	@command -v ruff >/dev/null 2>&1 && ruff check src tests || echo "ruff not installed — skip (Phase 1)"

test test-unit:
	pytest tests/test_sensing_p1.py tests/test_mqtt_topics.py -q

build:
	python -c "import agri_edge; print('agri_edge import OK', getattr(agri_edge,'__version__','?'))"

docker-up:
	docker compose -f ground_iot/docker-compose.yml up -d

docker-down:
	docker compose -f ground_iot/docker-compose.yml down
