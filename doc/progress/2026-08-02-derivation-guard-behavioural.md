# The anti-derivation guard asserts the property, not the spelling

STATUS: complete. Test-only; no production code changes.

WHAT: `test_watched_lanes_is_UNCHANGED_by_what_the_config_declares` added beside
the existing AST guard in
`tests/test_config_declares_a_lane_nobody_watches.py`. It points the module at
configs declaring wildly different `shadow_models` sets — including none, and
including decorated variants of the real lanes — and asserts `watched_lanes()`
does not move. An unreadable config is covered too: *"could not read"* is not a
membership statement.

WHY/DIR: orch#702's decision — membership is **declared**, never derived,
because a lane REMOVED from the config would otherwise leave the watch list with
it and the sentinel would stop looking for exactly what orch#689 detects.
orch#761 reaffirmed that decision. The guard protecting it was weaker than the
decision itself.

## The measurement that motivated it

`test_the_watch_list_is_NOT_derived_from_the_config` enumerates the rejected
design's *shapes*:

```python
assert "config_declared_lanes" not in called          # a call by NAME
assert not any("shadow_models" in c for c in consts)  # constants in watched_lanes' OWN ast
```

On 2026-08-02 I wrote `goal1/sentinel-lanes-from-config` (PR #760, closed), which
derives the watch list from `ranking.panel_scoring.shadow_models` — precisely the
design the guard exists to reject. **It passed.** The helper was named
`lane_names_from_config` and the literal lived one function away, so both checks
inspected the wrong object. One rename and one extraction.

That is the `enumerated-allow-list` shape: listing bad forms instead of asserting
the invariant. A behavioural check cannot be renamed around.

| check | vs the violating sentinel | vs `main` |
|---|---|---|
| existing AST guard | **passes** — the violation is invisible to it | passes |
| new behavioural guard | **fails**, as it must | passes |

[VERIFIED — both guards run against
`origin/goal1/sentinel-lanes-from-config`'s sentinel and against `main`'s,
2026-08-02]

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| module tests | 15 passed, 1 skipped | [VERIFIED — `pytest -q tests/test_config_declares_a_lane_nobody_watches.py`] |
| the new guard is load-bearing | fails against the derivation sentinel, passes on `main` | [VERIFIED — direct substitution, both directions] |
| it is not vacuous | asserts the base patrol is non-empty first | in the test |

NEXT: none. The existing AST guard is kept — it is cheap and it catches the
careless case at parse time; the behavioural one catches the careful case.
