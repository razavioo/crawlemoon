.PHONY: install dev-install test test-coverage lint lint-fix format audit clean clean-dist run-mcp run-cli build publish test-publish docs

install:
	pip install -e .
	playwright install chromium

dev-install:
	pip install -e ".[dev,captcha,ocr]"
	playwright install chromium
	pre-commit install || true

test:
	pytest tests/ -v

test-coverage:
	pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=xml --cov-fail-under=60

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/
	mypy src/ --ignore-missing-imports

lint-fix:
	ruff check --fix src/ tests/
	ruff format src/ tests/

format: lint-fix

audit:
	pip-audit --strict || true

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache build/ *.egg-info

clean-dist:
	rm -rf dist/
	mkdir -p dist

build: clean-dist
	python3 -m build

# Publish reads PYPI_TOKEN from the environment. Set it in your shell or via
# direnv / 1Password / keychain — never commit a token to the repo.
publish: build
	@if [ -z "$$PYPI_TOKEN" ]; then \
		echo "Error: PYPI_TOKEN is not set in the environment."; \
		echo "Hint: export PYPI_TOKEN=\$$(cat ~/.config/pypi/token) (or use a keychain helper)."; \
		exit 1; \
	fi
	python3 -m twine upload --username __token__ --password "$$PYPI_TOKEN" dist/*

test-publish: build
	@if [ -z "$$PYPI_TOKEN" ]; then \
		echo "Error: PYPI_TOKEN is not set in the environment."; \
		exit 1; \
	fi
	python3 -m twine upload --repository testpypi --username __token__ --password "$$PYPI_TOKEN" dist/*

docs:
	@echo "Docs target reserved. Add Sphinx/mkdocs build here."

run-mcp:
	python -m src.mcp.server

run-cli:
	python -m src.cli.main

.DEFAULT_GOAL := install
