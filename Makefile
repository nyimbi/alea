# ALEA. Everything runs locally; CI calls the same targets.
#
# `make check` is the gate. It runs the same groups in the same order as CI,
# because CI calls this runner rather than reimplementing it.

.DEFAULT_GOAL := help
.PHONY: help setup build check check-quick test types lint fmt-fix \
        canaries determinism rust clean logs \
        workflow workflow-dry dvc-repro dvc-status fetch

PY := uv run python
RUNNER := $(PY) scripts/check.py

# `snakemake` and `dvc` are installed as uv tools, not as project dependencies:
# neither is importable from `alea` (AD-5 forbids the workflow layer reaching
# into the package) and a lockfile that carried them would put a scheduler in
# every deployment. `make setup` installs both.
SNAKEMAKE := uvx snakemake
DVC := uvx dvc

# The environment config the workflow targets. Kenya is the development target.
ENV ?= config/config.kenya.yaml

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install uv, the toolchain, and the project
	@command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
	uv sync --all-extras
	uv tool install maturin
	uv tool install snakemake
	uv tool install dvc
	$(MAKE) build

build: ## Build the Rust extension into the venv
	uv run maturin develop --release

check: ## Everything. This is the gate.
	$(RUNNER)

check-quick: ## Lint, types, tests. No Rust, no solve.
	$(RUNNER) lint types tests canaries

test: ## The CI test suite
	uv run pytest -q tests/ci

types: ## Type check
	uv run pyright

lint: ## Lint
	uv run ruff check src tests scripts

fmt-fix: ## Apply lint fixes (no formatter: the standard is tabs, ruff emits spaces)
	uv run ruff check --fix src tests scripts

canaries: ## Assert every gate fails on its planted defect
	uv run pytest -q tests/ci/canaries

determinism: ## Two processes, byte-identical output
	uv run python scripts/determinism.py

rust: ## Rust format, lints, unit tests
	cargo fmt --all --check
	cargo clippy --workspace --all-targets -- -D warnings
	cargo test -p alea-common -p alea-rasters -p alea-dedup \
		-p alea-series -p alea-losses -p alea-risk

workflow: ## Run the pipeline (Snakemake). ENV=config/config.kenya.yaml by default
	$(SNAKEMAKE) -c1 --config env=$(ENV)

workflow-dry: ## Parse the workflow and print what would run
	$(SNAKEMAKE) --dry-run -c1 --config env=$(ENV)

fetch: ## Retrieve every source the register can fetch. Needs the network.
	$(SNAKEMAKE) -c1 fetch_all --config env=$(ENV)

dvc-repro: ## Rebuild the tracked datasets with DVC
	$(DVC) repro

dvc-status: ## What DVC considers stale
	$(DVC) status

logs: ## Where the last run's output went
	@ls -la tmp/check-logs/ 2>/dev/null || echo "no logs yet; run 'make check'"

clean: ## Remove build and check artefacts
	rm -rf tmp/check-logs target/wheels
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
