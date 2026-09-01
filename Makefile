.PHONY: check test probe init-db

check:
	python -m compileall -q src

test:
	pytest

init-db:
	cross-asset init-db

probe:
	cross-asset probe-data

