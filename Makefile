.PHONY: help bootstrap lint test test-unit test-ops build docker-up docker-down

help:
	@echo "bootstrap lint test test-unit test-ops build docker-up docker-down"

bootstrap:
	python -m pip install -U pip
	pip install -e ".[dev]" || pip install -e .
	@echo "bootstrap done (install Docker Desktop separately for ground_iot)"

lint:
	@command -v ruff >/dev/null 2>&1 && ruff check src tests || echo "ruff not installed — skip"

# Full suite (CI parity with .github/workflows/test.yml)
test:
	pytest -q

test-unit:
	pytest tests/test_sensing_p1.py tests/test_mqtt_topics.py tests/test_ops_*.py \
	  tests/test_detection_backends.py tests/test_model_registry.py tests/test_vehicle_adapter.py \
	  tests/test_export_yolox_stub.py tests/test_ops_db_detections.py tests/test_yolox_postprocess.py -q

test-ops:
	pytest tests/test_ops_*.py -q

build:
	python -c "import agri_edge; print('agri_edge import OK', getattr(agri_edge,'__version__','?'))"

docker-up:
	docker compose -f ground_iot/docker-compose.yml up -d

docker-down:
	docker compose -f ground_iot/docker-compose.yml down
