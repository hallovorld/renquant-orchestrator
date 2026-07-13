## G3 V-004: Remove hardcoded paths from scheduled_jobs.py

Replaced all 12 hardcoded `/Users/renhao/git/github/RenQuant` path occurrences
in `scheduled_jobs.py` job definitions with paths constructed from
`default_repo_root()` at call time. Removed the `CANONICAL_REPO_ROOT` constant
and the `_localize_repo_root()` rewrite function (both now unnecessary). The
module-level `_JOBS` tuple became a `_build_jobs()` function so that
`RENQUANT_REPO_ROOT` environment overrides are respected lazily at the point of
use rather than baked in at import time. `to_jsonable()` simplified to a plain
`asdict()` projection. All 18 `test_scheduled_jobs.py` tests pass including the
`test_inventory_localizes_repo_root_paths` localization contract test.
