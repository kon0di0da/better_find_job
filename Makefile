PYTHON ?= python3

.PHONY: spec-check
spec-check:
	$(PYTHON) tools/spec_check.py
