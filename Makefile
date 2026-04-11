.PHONY: lint format typecheck test test-cov serve-mcp build-knowledge clean

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

typecheck:
	mypy src/

test:
	pytest

test-cov:
	pytest --cov=rpa_architect --cov-report=term-missing --cov-report=html

serve-mcp:
	python -m rpa_architect.mcp_server.server

build-knowledge:
	python -m rpa_architect.knowledge.builder

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
