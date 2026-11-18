.PHONY: dev check test build

dev:
	.venv/bin/python scripts/dev.py --seed

check:
	.venv/bin/python scripts/dev.py --check

test:
	.venv/bin/python -m pytest

build:
	cd frontend && npm run build
