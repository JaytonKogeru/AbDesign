.PHONY: test selftest

test:
	pytest

selftest:
	python scripts/selftest.py
