PYTHON ?= python3
PYTHONPATHS := apps/profile_service:apps/knowledge_service:apps/interview_service:packages/platform_adapters
SERVICES := profile_service knowledge_service interview_service
REPORT_ROOT ?=
EGRESS_REPORT ?= $(if $(REPORT_ROOT),$(REPORT_ROOT)/results/egress-findings.json,$(or $(TMPDIR),/tmp)/better-find-job-egress-report.json)

.PHONY: spec-check lint unit acceptance migration-test contract-test mock-check fixture-test fixture-check ci-test egress-scan ci \
	_spec-check _lint _unit _migration-test _contract-test _mock-check _fixture-test _ci-test _egress-scan

# When REPORT_ROOT is set, every public gate records logs, JSON and JUnit without
# complicating the default local command. Internal targets hold the real checks.
define run-gate
	$(if $(REPORT_ROOT),$(PYTHON) .ci/run_gate.py --gate $(1) --report-root "$(REPORT_ROOT)" -- $(MAKE) --no-print-directory _$(1),@$(MAKE) --no-print-directory _$(1))
endef

spec-check:
	$(call run-gate,spec-check)

_spec-check:
	$(PYTHON) tools/spec_check.py

lint:
	$(call run-gate,lint)

_lint:
	$(PYTHON) -m ruff check apps packages migrations tests .ci

unit:
	$(call run-gate,unit)

_unit:
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
	$(call run-gate,migration-test)

_migration-test:
	@test "$${ALLOW_DESTRUCTIVE_MIGRATION_TEST:-}" = "1" || \
		(echo "ALLOW_DESTRUCTIVE_MIGRATION_TEST=1 is required" >&2; exit 2)
	@test -n "$${TEST_DATABASE_URL:-}" || \
		(echo "TEST_DATABASE_URL is required" >&2; exit 2)
	PYTHONPATH=. $(PYTHON) -m pytest -q tests/migrations/test_migration_contract.py

contract-test:
	$(call run-gate,contract-test)

_contract-test:
	PYTHONPATH=packages $(PYTHON) -m pytest -q packages/contracts/ports/tests

mock-check:
	$(call run-gate,mock-check)

_mock-check:
	PYTHONPATH=packages:packages/platform_adapters $(PYTHON) -m pytest -q \
		packages/platform_adapters/tests

fixture-test:
	$(call run-gate,fixture-test)

_fixture-test:
	PYTHONPATH=. $(PYTHON) -m pytest -q tests/fixtures

fixture-check: fixture-test

ci-test:
	$(call run-gate,ci-test)

_ci-test:
	PYTHONPATH=tests/ci $(PYTHON) -m pytest -q tests/ci

egress-scan:
	$(call run-gate,egress-scan)

_egress-scan:
	$(PYTHON) .ci/egress_scan.py --report "$(EGRESS_REPORT)"

ci: lint unit spec-check mock-check contract-test fixture-test migration-test egress-scan
