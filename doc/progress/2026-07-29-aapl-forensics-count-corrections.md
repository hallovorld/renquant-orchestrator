# Progress: AAPL forensics — count corrections + a reproducible extraction

STATUS:   delivered. Follow-up to PR #614, which merged at 2026-07-30T00:17Z
          while carrying four CHANGES_REQUESTED reviews. Docs + one new
          read-only script + tests. No config, artifact, pin or live surface
          touched.

WHAT:     1. `scripts/aapl_admission_forensics.py` (new) — re-derives every
             decision-driving number in the forensics note from the score DB and
             the daily logs. This is the "reproducible extraction tied to the
             resolved historical run configuration" asked for on #614.
          2. `tests/test_aapl_admission_forensics.py` (new, 9 tests) —
             behavioural tests of the extraction on synthetic fixtures.
          3. Corrections to `doc/research/2026-07-29-aapl-never-bought-forensics.md`
             (new §0a records them) and to
             `doc/progress/2026-07-29-aapl-forensics.md`.

WHY/DIR:  Clearing #614's review backlog. Three of the four objections were
          already addressed by the branch's last two commits; verifying the
          fourth against the artifacts surfaced two wrong counts in the merged
          text, one of which is the note's headline and was also in the PR title.

ROOT CAUSE OF THE WRONG COUNTS — a window mismatch, not a query bug:
          §0's aggregates were computed over sessions from 2026-07-06 onward,
          while §2's funnel table started at 2026-07-08. The only two sessions
          where AAPL scored BELOW the cross-sectional median — 07-06 (43rd pct)
          and 07-07 (42nd pct) — were therefore inside the denominator but
          absent from the table, so the ratio could not be checked against the
          evidence printed next to it. The note now declares the window once in
          §0 and the §2 table covers all of it (19 rows).

CORRECTIONS (all `[VERIFIED-now]` via the new script):

  | was | now | why |
  |---|---|---|
  | above median `12 of 13` | `11 of 13` | 07-06 and 07-07 are both below the median |
  | floor recompute `15/15` | `13/13` | only 13 sessions were scored; 15 counted table ROWS, 4 of which are non-scored sessions |
  | 07-24 percentile `79th` | `78th` | 56 of 72 candidates score below AAPL = 77.8% |
  | `runs.alpaca.db (4,774 rows)` | removed | matches no table in the DB; `candidate_scores` = 241,675, `pipeline_runs` = 39,728, `score_distribution` = 4,858 |
  | `0 rows with is_holding=1` over `64` rows | `0` of `84` rows with `role='holding'` | `is_holding` is not a column in this schema |
  | repeat rate `245/2,837 = 8.6%` | `254/2,768 = 9.2%` | dedup rule now stated; median 0.92 reproduces exactly, the pair count does not |

SURVIVED re-derivation (now stated precisely instead of as `~`):
          `~18%` -> mean **18.3%**, range 15.2-22.2%.
          `~6%`  -> mean **6.1%**, range 0.0-17.7%.
          Both need the full 13-session window: over only the 11 sessions the
          merged table printed, the floor-and-mu share is **4.8%**, not 6.1%
          `[VERIFIED-now]`. That sensitivity is why the missing rows mattered.

EVIDENCE: artifact: `RenQuant/data/runs.alpaca.db` (`immutable=1`) and
                    `RenQuant/logs/daily_104/*.log` (169 logs). READ-ONLY.
  independently confirmed the fix that #614's last commit made:
                    `mu_floor=0.03` appears on 13/13 scored sessions, and every
                    one of the 20 `ConvictionGateTask` gate lines across all 169
                    retained logs reads `mu_floor=0.03` — no other value has ever
                    been resolved on this surface `[VERIFIED-now]`. The
                    historical-policy objection is answered by the runtime
                    surface, not by today's config.
  run pinning:      the script derives the per-session run from runtime evidence
                    rather than by hand: the `VetoWeakBuysTask` line reports the
                    cross-section size `n` it gated on, so the run whose
                    candidate row count equals `n` is the one that gated. This
                    independently re-derives `2026-07-28-live-5b859fff` (n=78)
                    as the operative 07-28 run of three `[VERIFIED-now]`.
  floor parity:     recomputed `max(0.20, mean + 1.00*stdev)` from the DB matches
                    the logged floor to 3 decimals on **13/13** scored sessions
                    `[VERIFIED-now]`. The script parses `min=` and `mean+K*std`
                    out of the log line, so a floor-mode change surfaces as a
                    mismatch rather than silently validating wrong arithmetic.
  prod or exp:      PROD observation, read-only. No order, config, artifact or
                    pin touched.

TESTS:    `make test` (with sibling repo `src/` on PYTHONPATH):
          **4398 passed, 5 failed, 5 skipped**. The same 5 failures are present
          on unmodified `origin/main` (4389 passed / 5 failed there), so they are
          pre-existing and unrelated: `test_bridge_live_bundle`, `test_cli`
          (parking sleeve, FileNotFound), two `test_native_context_hydration`,
          `test_native_live_inference`. Net new: **9 passing tests**.

          The tests are behavioural, not textual. Two mutations were injected to
          confirm they bite: relaxing `above = rs > median` to `>=` fails
          `test_sitting_exactly_on_the_median_does_not_count_as_above_it`, and
          counting unscored sessions in the numerator fails
          `test_summarize_ignores_sessions_where_the_ticker_was_not_scored`.

SCOPE:    Orchestrator-owned only: two docs it already owns, one script under
          `scripts/`, one test file. `runtime_paths.default_data_root()` is used
          for the default data root rather than a hardcoded umbrella path — the
          defect Codex caught on PR #404.

WHAT DID NOT CHANGE: the conclusion. AAPL was above the model's own median on
          most scored sessions, was logged out by the rank floor every time, and
          would still have failed conviction by ~4.4x. Only the counts and their
          provenance moved.

NEXT:     Unchanged and still open (#610): is `mu_floor = 0.03` an ECONOMIC
          hurdle or a STATISTICAL one? If statistical, it is mis-set by
          construction, since it sits above the calibrator's own p90.
