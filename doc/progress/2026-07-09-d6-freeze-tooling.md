# Progress — D6 freeze-record tooling (2026-07-09)

**What**: `scripts/d6_freeze_record.py` — generator + verifier for the D6
preregistered-replay freeze record required by protocol §1
(`doc/design/2026-07-09-governor-prereg-replay-protocol.md`, RFC PR #443).
The freeze COMMIT for a valid run must be pushed BEFORE any arm runs; this
tool generates that artifact and re-checks it for drift at run time.

**Mechanics** (all read-only; DB opened `file:...?mode=ro`):

1. Enumerates replay sessions per forward horizon with the same rule as the
   pipeline WF-cut loader (`wf_replay_loader.load_replay_bars_from_sim_db`):
   a session is a date whose `score_distribution` (mu/sigma non-NULL) ⋈
   `ticker_forward_returns` (fwd column non-NULL) join has ≥ 2 rows.
2. Excludes the hypothesis-generation window (default
   `2026-06-23:2026-07-09`, endpoints inclusive) plus any
   `--exclude-session` (the §1 evidence-memo rule).
3. Splits tuning/evaluation deterministically by seeded hash: dates ranked
   by `sha256("<seed>|<date>")` over the UNION of horizon session dates;
   first `floor(tuning_frac × N)` = tuning. Ranking on the union makes the
   assignment per-date and identical across horizons (nested selection —
   tuning at one horizon can never touch another horizon's evaluation set).
4. Emits the freeze-record JSON: exact session IDs per subset, DB sha256 +
   size + mtime, per-horizon data cutoff, as-of artifact stats
   (path/mtime/sha256 for the live panel-LTR model, global calibrator, and
   NGBoost head under the umbrella strategy dir), generator version + args.
5. `--verify RECORD.json` recomputes from the record's stored args and
   diffs everything except the generation timestamp; exit 1 on drift
   (0 clean, 2 unevaluable). `--db`/`--artifacts-root` overrides exempt
   only path/copy-mtime fields — sha256 still guards content.

**Validation**: 18 new tests on a synthetic fixture DB (no production-DB
dependency): loader-faithful enumeration incl. min-rows and NULL handling,
window + manual exclusion, deterministic/exact/nested split, seed
sensitivity, DB-not-written proof, verify clean/DB-drift/artifact-drift/
tampered-record/path-override cases. Full suite: 3289 passed, 3 skipped.
Read-only smoke run against the real DB reproduced the exploratory
inventory exactly (497 fwd_1d / 483 fwd_60d sessions, db sha `82084a6d…`)
and verify round-tripped clean; no repo or live-tree writes.

**Boundaries honored**: orchestration/eval tooling only; no pipeline
internals re-implemented (session rule mirrors the loader's documented SQL
contract); production DB and umbrella artifacts touched read-only.

**Next**: after RFC #443 approval — run the generator with an agreed seed,
commit + push the record (the freeze commit), then `--verify` immediately
before Phase-1 arm execution.

## Addendum 2026-07-10 — loader-parity gate (codex review)

Codex flagged that the tool's session-enumeration SQL duplicates the pipeline
loader's logic, so semantic drift could freeze inputs the replay never
consumes. Closed by making the loader the mechanically-enforced ground truth:

- `test_session_parity_with_pipeline_loader` imports the ACTUAL loader
  (`renquant_pipeline.kernel.portfolio_qp.wf_replay_loader.
  load_replay_bars_from_sim_db`, on PYTHONPATH in the make-test env;
  `importorskip` elsewhere) and asserts identical session lists per horizon
  on a synthetic fixture covering: exactly 1 vs >= 2 joined rows (boundary),
  NULL mu, NULL sigma, missing fwd rows entirely, fwd column NULL at one
  horizon, and one ticker under two run_ids (the loader counts ROWS, not
  distinct tickers — bar carries the ticker twice; the tool agrees).
- No discrepancy existed; no SQL change was needed. The tool's
  `enumerate_sessions` docstring now marks the parity gate so future loader
  changes route back here.
- Real-data parity (byte-identical scratch copy of `sim_runs.db`, primary
  never touched): loader vs tool identical at both horizons — 497 fwd_1d
  (2024-01-02 → 2026-03-27), 483 fwd_60d (2024-01-02 → 2026-03-09).
- Status: the tool remains DRAFT until RFC #443 merges (design-first
  ruling); this addendum only closes the parity gap.
