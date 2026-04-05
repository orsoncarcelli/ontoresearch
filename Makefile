.PHONY: test lint typecheck dryrun install

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -x -q

lint:
	ruff check src/ tests/

typecheck:
	mypy src/

dryrun: test typecheck lint
	@echo "All checks passed."
