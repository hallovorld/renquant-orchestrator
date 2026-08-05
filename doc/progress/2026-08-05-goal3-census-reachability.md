# 2026-08-05 — GOAL-3: the 42-candidate work list is really a 5-candidate work list

## What the census left open

orch#814 landed a duplicate-definition census: 42 names in
`renquant_orchestrator` defined in more than one file, none exported, and its own
output insisted a duplicate is **a candidate, not a verdict**. Its NEXT said:
read down the list, retrain Tasks first.

Reading four of them (in review) found **zero** twins — each Task is instantiated
only by its own module-local job. That is a result about four names. This
measures the property behind it, for all 42.

## The measurement `[VERIFIED — this session, corrected in review]`

For each duplicate name, how many modules import it **by name**, scanning
`src/`, `tests/`, `scripts/` and `ops/`:

| reachability | count | what it means |
|---|---|---|
| no import site found | **17** | no `from X import NAME` anywhere this scan can see |
| exactly one source module | **10** | unambiguous at every import site |
| **MULTI-SOURCE** | **15** | a reader could expect one implementation and get another |

The fifteen: `AdmittedName`, `IllegalTransition`, `append_records`,
`build_report`, `collect`, `connect`, `default_pilot_path`,
`default_shadow_log_path`, `default_tick_feed_path`, `emit_alert`,
`evaluate_session`, `main`, `render_markdown`, `session_date`, `summarize`.

### The correction that produced these numbers

My first version scanned **only `src/renquant_orchestrator`** and reported
**29 / 8 / 5**, with the 29 labelled *"module-local; cannot be confused"*. Codex
produced counterexamples from this very repo `[codex on orch#821]`:
`tests/test_entry_timing_shadow.py` imports `AdmittedName`, `append_records`,
`collect`, `evaluate_session`, `existing_keys`, `record_key` and `summarize`;
`tests/test_execution_reconciler.py` imports `IllegalTransition`;
`tests/test_expkit_prereg.py` imports `sha256_file`.

A reachability figure computed over the package alone is not a reachability
figure. Scanning the repository **triples the multi-source count, 5 → 15**, and
my headline — *"the work list is 4 names, not 42"* — was wrong. It is **14**
(excluding `main`), which is still a two-thirds reduction, but it is not the
number I published.

## What this does NOT say

- **Multi-source is not a defect.** `from a import J` and `from b import J` are
  each unambiguous; the risk is a *reader* assuming the wrong one, not the
  interpreter resolving wrongly. None of these five is a twin in the pipeline
  sense (one implementation shadowing another behind a shared export) — the
  orchestrator exports 3 names and none of the 42 is among them.
- **"No import site found" is NOT "unreachable".** The scan sees
  `from X import NAME` under `src/tests/scripts/ops`. It does **not** see
  `import X` + `X.NAME` attribute access, star imports, `importlib`, lazy
  `__getattr__` re-exports, or callers in **other repositories** — and this
  project is seven repositories. The bucket is named `no-import-site-found`
  rather than anything stronger, and the renderer says so on the same line.
- Nothing here judges whether any duplicate should be de-duplicated. Two
  implementations of `emit_alert` may be perfectly reasonable.

## Why it belongs in the tool rather than a comment

The census already prints a work list. A work list that does not say which items
a caller can actually confuse invites the next reader to do all 42 — which is how
the four already-read ones got read in review rather than by design.

Suites: 25 tests in this file, incl. one that PINS the exact 17/10/15 split
and the 15-name multi-source set — the first version asserted only `>=30` and
would have passed straight through the drift that tripled the count
`[codex on orch#821]`.
