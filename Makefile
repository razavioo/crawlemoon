.PHONY: install dev-install test lint format clean run-mcp run-cli build publish test-publish

install:
	pip install -r requirements.txt
	playwright install chromium

dev-install:
	pip install -r requirements.txt
	pip install -e ".[dev]"
	playwright install chromium

test:
	pytest tests/ -v

lint:
	ruff check src/
	mypy src/

format:
	black src/
	ruff check --fix src/

clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info

build:
	python3 -m build

publish:
	@if [ ! -f .pypi_token ]; then \
		echo "Error: .pypi_token file not found. Please create it with your PyPI token."; \
		exit 1; \
	fi
	PYPI_TOKEN=$$(cat .pypi_token) && \
	python3 -m twine upload --username __token__ --password "$$PYPI_TOKEN" dist/*

test-publish:
	@if [ ! -f .pypi_token ]; then \
		echo "Error: .pypi_token file not found. Please create it with your PyPI token."; \
		exit 1; \
	fi
	PYPI_TOKEN=$$(cat .pypi_token) && \
	python3 -m twine upload --repository testpypi --username __token__ --password "$$PYPI_TOKEN" dist/*

run-mcp:
	python -m src.mcp.server

run-cli:
	python -m src.cli.main

.DEFAULT_GOAL: install


