# 2026-07-05 — scheduled_health.py test coverage

Added 75 unit tests for `scheduled_health.py` (141 lines, previously zero test coverage).
Covers all 5 functions: `_load_status_source`, `_status_by_job`, `_last_log_excerpt`,
`_classify` (parametrized over all 11 REJECT_MARKERS), and `build_scheduled_health`
(integration tests with mocked `inventory_payload`).
