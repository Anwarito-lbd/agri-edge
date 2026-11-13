# Developer entry points. Spec section 10.
#
# One rule governs this file: a target that cannot do its job FAILS. It does not
# print a note and exit 0. Two of the three worst findings in the 19 Sept audit
# were checks that existed, appeared to pass, and were not running -- including
# this file's own `lint`, which was:
#
#     @command -v ruff >/dev/null 2>&1 && ruff check src tests || echo "skip"
#
# Exit code 0 whether it linted or not. Nothing distinguished "clean" from
# "never ran". The CI extras job already greps its own output to catch exactly
# that; the Makefile now holds itself to the same standard.

PYTHON ?= python
PYTEST ?= $(PYTHON) -m pytest

.PHONY: help bootstrap lint format typecheck test test-unit test-integration \
        test-ops build docker-up docker-down sitl hailo-smoke edge-run \
        simulate-physics web-install web-test web-build clean

help:
	@echo "bootstrap        install the package and dev tooling"
	@echo "lint             ruff check (fails if ruff is missing)"
	@echo "format           ruff format"
	@echo "typecheck        mypy over the runtime package"
	@echo "test             the whole suite"
	@echo "test-unit        fast units, no hardware or network"
	@echo "test-integration end-to-end paths, skipped without fixtures"
	@echo "test-ops         the ops station only"
	@echo "build            import check + wheel"
	@echo "docker-up/down   ground_iot stack (Mosquitto, Node-RED)"
	@echo "sitl             ArduPilot SITL (needs vendor/ardupilot + WSL2)"
	@echo "hailo-smoke      compile and probe the Hailo path (needs WSL2 + DFC)"
	@echo "edge-run         the edge pipeline against config/pi.yaml"

bootstrap:
	$(PYTHON) -m pip install -U pip
	pip install -e ".[dev]"
	pip install ruff mypy
	@echo "bootstrap done. Docker Desktop and WSL2 install separately -- see docs/HARDWARE_PLAN.md Stage 0."

lint:
	@command -v ruff >/dev/null 2>&1 || { \
	  echo "ruff is not installed. A lint target that skips is worse than no"; \
	  echo "lint target, because it reports success. Run: make bootstrap"; \
	  exit 1; }
	ruff check src tests training workstation mechanical scripts

format:
	@command -v ruff >/dev/null 2>&1 || { echo "ruff missing; run: make bootstrap"; exit 1; }
	ruff format src tests training workstation mechanical scripts

typecheck:
	@command -v mypy >/dev/null 2>&1 || { echo "mypy missing; run: make bootstrap"; exit 1; }
	mypy src/agri_edge --ignore-missing-imports

# Full suite, matching .github/workflows/test.yml.
test:
	$(PYTEST) -q

# Everything that needs neither a device nor a socket. This is the loop to run
# while editing.
test-unit:
	$(PYTEST) -q -m "not integration" \
	  --ignore=tests/test_integration.py \
	  --ignore=tests/test_mavlink_faults.py \
	  --ignore=tests/test_sitl.py

test-integration:
	$(PYTEST) -q tests/test_integration.py tests/test_mavlink_faults.py

# Reproduce CI's lean runner: a throwaway venv with the runtime core and
# nothing else. This machine has torch, Pillow and onnxruntime from the
# training work, so a test that quietly needs one of them passes here and fails
# there -- which is how CI stayed red for four commits without anyone noticing.
test-lean:
	$(PYTHON) scripts/lean_runner_check.py

test-ops:
	$(PYTEST) -q tests/test_ops_*.py

build:
	$(PYTHON) -c "import agri_edge; print('agri_edge import OK', getattr(agri_edge,'__version__','?'))"
	$(PYTHON) -m pip wheel . -w dist --no-deps

docker-up:
	docker compose -f ground_iot/docker-compose.yml up -d

docker-down:
	docker compose -f ground_iot/docker-compose.yml down

# Needs the vendored ArduPilot tree and a C++ toolchain, which on Windows means
# WSL2. The script says so rather than failing obscurely.
sitl:
	bash scripts/sitl.sh

# The Hailo Dataflow Compiler is x86_64 Linux only -- WSL2 on this machine.
hailo-smoke:
	bash scripts/hailo_compile.sh --arch hailo8

edge-run:
	$(PYTHON) -m agri_edge.cli -c config/pi.yaml fly --sitl --frames 20

simulate-physics:
	$(PYTHON) scripts/simulate_airframe_physics.py

web-install:
	cd apps/web && npm ci

web-test:
	cd apps/web && npm run typecheck && npm run lint && npm test

web-build:
	cd apps/web && OPS_API_URL=http://127.0.0.1:1 npm run build

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache .mypy_cache apps/web/.next apps/web/tsconfig.tsbuildinfo
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
