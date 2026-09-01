PYTHON ?= python3
PYTHONPATHS := apps/profile_service:apps/knowledge_service:apps/interview_service:packages/platform_adapters
SERVICES := profile_service knowledge_service interview_service

.PHONY: spec-check lint unit acceptance migration-test contract-test mock-check

spec-check:
	$(PYTHON) tools/spec_check.py

lint:
	$(PYTHON) -m ruff check apps packages migrations tests

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

migration-test:
	@test "$${ALLOW_DESTRUCTIVE_MIGRATION_TEST:-}" = "1" || \
		(echo "ALLOW_DESTRUCTIVE_MIGRATION_TEST=1 is required" >&2; exit 2)
	@test -n "$${TEST_DATABASE_URL:-}" || \
		(echo "TEST_DATABASE_URL is required" >&2; exit 2)
	PYTHONPATH=. $(PYTHON) -m pytest -q tests/migrations/test_migration_contract.py

contract-test:
	PYTHONPATH=packages $(PYTHON) -m pytest -q packages/contracts/ports/tests

mock-check:
	PYTHONPATH=packages:packages/platform_adapters $(PYTHON) -m pytest -q \
		packages/platform_adapters/tests
