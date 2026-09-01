PYTHON ?= python3
PYTHONPATHS := apps/profile_service:apps/knowledge_service:apps/interview_service:packages/platform_adapters
SERVICES := profile_service knowledge_service interview_service

.PHONY: spec-check lint unit acceptance

spec-check:
	$(PYTHON) tools/spec_check.py

lint:
	$(PYTHON) -m ruff check apps packages

unit:
	PYTHONPATH="$(PYTHONPATHS)" $(PYTHON) -m pytest -q --import-mode=importlib \
		apps/profile_service/tests \
		apps/knowledge_service/tests \
		apps/interview_service/tests

acceptance:
	@set -eu; \
	for service in $(SERVICES); do \
		PYTHONPATH="apps/$$service" $(PYTHON) -m pytest -q \
			"apps/$$service/tests/test_foundation_acceptance.py"; \
	done
