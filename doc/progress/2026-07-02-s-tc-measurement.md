# S-TC transfer-coefficient measurement — research PR

STATUS:   research evidence (read-only; docs + one committed script + JSON evidence) —
          revised twice after Codex CHANGES_REQUESTED (r2: 5 methodology findings; r3: r2's own
          admission/sizing classification was itself a bug — both addressed below).
REVISION: r3.
WHAT:     task S-TC of the unified plan (#231 §1 Term TC): `scripts/poc_transfer_coefficient.py`
          + `doc/research/evidence/2026-07-02-roadmap-pocs/poc_stc_transfer_coefficient.json`.
          Produces an EXPLORATORY diagnostic — not measured-tier TC — for the reasoned "≈0.4"
          number in the #231 §0 state vector.
WHY/DIR:  IR = TC·IC·√BR — TC was asserted ≈0.4. r1 reported full-book TC 0.438/0.481
          (Pearson/Spearman) and buy-side decision-TC ≈0.09 and called this "the strongest
          quantitative justification measured so far for lane A + R4." Codex correctly rejected
          that framing on 5 independent grounds; r2 fixed the methodology and REMOVED the lane-A/
          R4 justification claim, but r2's own admission/sizing split misclassified `blocked_by`
          and produced an UNSUPPORTED "100% blocked before sizing" finding — itself a bug, not a
          real result (see ROUND 3 below). r3 fixes the classification and reports the genuine,
          corrected result.

EVIDENCE:
```
artifact:      scripts/poc_transfer_coefficient.py (script) +
               doc/research/evidence/2026-07-02-roadmap-pocs/poc_stc_transfer_coefficient.json
               (committed output)
prod or exp:   experiment — read-only diagnostic script, no config/order/gate change
existing data: runs.alpaca.db candidate_scores/trades/pipeline_runs (10 canonical daily "full"
               live runs after dedup, 2026-06-04 to 2026-07-01); live Alpaca /v2/positions +
               /v2/account (read-only)
best-known?:   best-available diagnostic given no S5 per-run position-snapshot ledger exists yet
               (full-book pairing stays cross-day until that lands — see finding 1 below)
scope:         this is scripts/poc_transfer_coefficient.py, EXPERIMENT/diagnostic, vs no prior
               committed baseline (r1's 0.09/0.44 figures are superseded by this revision, not a
               comparison point — r1 conflated admission and sizing effects, see finding 2)
```

**Codex round-2 findings, all addressed:**

1. **Full-book pairing is cross-day, not same-day.** r1's own caveat text incorrectly called the
   comparison "a same-day pairing" — it compares TODAY's live broker positions against the
   LATEST recorded run's desired vector, which can be (and typically is) a different calendar
   day. Fixed: the caveat text is corrected, and a new `same_day_aligned: false` field is stamped
   explicitly. No point-in-time position-snapshot mechanism exists yet to make this genuinely
   same-day (tracked as future S5-ledger work, unchanged from r1) — until then this number is
   descriptive only, never a same-timestamp measurement.
2. **Buy-side eligibility conflated admission and sizing.** r1 filtered on `role=candidate AND
   mu>=0.03` and mapped every non-buy to a target of 0, correlating the WHOLE eligible set. This
   combines "was this name blocked by an upstream gate" (regime/QP-admission/rank-floor vetoes —
   recorded in `candidate_scores.blocked_by`) with "how much did SIZING shrink an already-admitted
   name's target." Fixed: `buy_side_decision_tc` now reports an admission-stage breakdown (counts
   by `blocked_by` reason) and computes the correlation ONLY over names with `blocked_by IS NULL`
   (survived every admission gate). **Result, re-measured on all 10 canonical daily runs: EVERY
   SINGLE ONE has `n_survived_admission = 0`** — i.e. in this dataset, admission gates
   (`broker_pending_submitted`, `candidate_not_selected`, `size_insufficient_cash`, `correlation`)
   block 100% of mu-floor-eligible candidates before any of them ever reach a clean sizing test.
   This is a MORE precise and arguably more actionable finding than r1's 0.09: it says the
   dominant constraint on capital deployment in this sample is ADMISSION, not the sizing/shrinkage
   stack r1's narrative blamed. The corrected script cannot currently report ANY genuine
   admission-clean sizing-stage correlation for lack of a surviving population — this itself
   should be investigated (why is `candidate_not_selected` blocking so much?) before any
   sizing-focused remediation (lane A / R4) is prioritized on the strength of this diagnostic.
3. **Undefined correlation was folded into the average as 0.0.** r1 substituted `tc_p=0.0` for
   both "zero buys" and "bought, but all at the same size" (Pearson correlation is mathematically
   undefined when either vector has zero variance) — two materially different, non-equivalent
   situations, both silently averaged into the reported 0.094 mean. Fixed: each run is now
   categorized `no_deployment` (zero buys), `zero_dispersion` (bought, but no size variation — a
   real, separately-interesting finding on its own), or `measured` (a genuine Pearson
   correlation) — only `measured` runs enter the series mean/SE. Given finding 2's result above,
   the corrected series currently has 0 runs with any sizing-stage population at all, so
   `buy_side_decision_tc_n_measured` is presently 0 (see NEXT).
4. **Seven observations were not independent — a duplicate day and an arbitrary "recent" slice.**
   r1 included TWO runs on 2026-06-09 and used an unweighted `series[-6:]` "recent" mean with no
   independence justification. Fixed: `_canonical_daily_runs` selects exactly one
   `pipeline_runs` row per `run_date` (the row with the latest `created_at` — the last completed
   run that day supersedes an earlier same-day attempt), and the mean/standard-error is now
   reported only over the genuinely `measured`-category subset of ALL eligible canonical days
   (not a fixed "last N"), with sample size and SE (or an explicit "undefined (n<2)" flag)
   reported alongside — never a bare point estimate.
5. **Pearson/Spearman correlation is scale-invariant — cannot see uniform deployment shrinkage.**
   r1's narrative attributed a "43% deployment shrinkage" to the same TC number that, being
   scale-invariant, cannot detect uniform-magnitude shrinkage (only relative-ordering changes).
   Fixed: added `exposure_transfer_ratio` — an UN-normalized regression-through-origin slope
   (`dot(w_actual, w_star) / dot(w_star, w_star)`) — which DOES scale linearly with deployed
   magnitude (a uniform k-fraction shrink of w_actual yields ratio ≈k, unlike Pearson/cosine which
   would both read ≈1.0 regardless). Reported alongside, never instead of, the correlation-based
   TC, for both full-book and buy-side-decision. This system tracks no external index benchmark
   (cash is the only "benchmark," 0% weight) — "active weight" is stated explicitly as the raw
   weight itself rather than assuming a benchmark that doesn't exist in this codebase.

**All numbers in the committed JSON are now explicitly labelled** (`"label"` field at the top of
the JSON) as an EXPLORATORY DIAGNOSTIC — not measured-tier TC, and NOT justification for any
lane/route decision. The r1 claim "the strongest quantitative justification measured so far for
lane A (de-throttle) + R4 (selection-budget refactor)" is REMOVED; #231's own state-vector update
line is softened to "EXPLORATORY diagnostic input candidate," not a validated replacement number.

**Tests:** `tests/test_poc_transfer_coefficient.py` — 9 new deterministic fixture tests
(in-memory SQLite, no dependency on real `runs.alpaca.db`), covering: admission-vs-sizing split
(blocked names excluded from sizing population; all-blocked → `insufficient_sizing_population`),
undefined-correlation categorization (no-buy → `no_deployment`; uniform-size buys →
`zero_dispersion`; genuine variation → `measured`; series mean excludes non-`measured` runs),
canonical daily-run selection (same-day duplicate resolved to the later `created_at`; sub-threshold
runs excluded), and full-book same-day-alignment flagging (mocked Alpaca API, no live network
call in the test). `python3 -m pytest tests/test_poc_transfer_coefficient.py -q` → 9 passed.
Re-ran the corrected script against the real `runs.alpaca.db` + live (read-only) Alpaca API —
output matches the analysis above (10 canonical daily runs, 0 with a sizing-clean population,
full-book Pearson/Spearman/exposure-ratio unchanged in magnitude, now correctly flagged
`same_day_aligned: false`).

## ROUND 3 (Codex CHANGES_REQUESTED — r2's admission/sizing split misclassified blocked_by)

**Finding.** r2's "100% blocked before sizing" result (finding 2 above) was itself a
classification bug, not a real discovery. r2 treated `blocked_by IS NULL` as "survived
admission" — but `blocked_by` is not exclusively an admission-stage field. In this ledger,
`broker_pending_submitted` (RenQuant `adapters/runner_trace.py::live_trace_selection_maps()`:
"Trace filled buys as selected and pending submissions as blocked") marks a name that WAS
selected and submitted to the broker — a terminal outcome, not an upstream rejection — and gets
swept into the same field only because its fill wasn't confirmed at trace-snapshot time.
Treating every non-null `blocked_by` as a pre-selection failure classified every actual
buy-in-flight as "blocked," which is why `n_survived_admission` came out to 0 on every single
canonical run — an artifact of the bug, not a property of the data.

**Fix.** Built an explicit taxonomy (`_classify_reason` / the `_PRE_SELECTION_BLOCKERS` /
`_SIZING_FAILURES` / `_SELECTED_SUBMITTED` / `_BROKER_OUTCOME_PREFIX` constants in
`scripts/poc_transfer_coefficient.py`), derived directly from the ACTUAL writer code, not
guessed from the string values:
- `renquant-pipeline/src/renquant_pipeline/kernel/selection.py::run_selection_loop()` — the
  true pre-selection greedy slot-filling loop that runs BEFORE sizing; its own docstring names
  its exhaustive reason set: `wash_sale`, `sector`, `correlation`, `tier`, `defensive_non_bear`.
  `candidate_not_selected` (persistence.py's generic no-reason-recorded fallback) joins this
  bucket — it means the name was never picked by ranking, a pre-selection non-event.
- `renquant-pipeline/src/renquant_pipeline/kernel/pipeline/task_selection.py::SizeAndEmitTask`
  — `_block()` only runs on names already in `ctx._selected` (post-selection), so every reason
  it stamps (`buy_blocked`, `skip_buys`, `size_bad_price`, `size_insufficient_cash`,
  `size_cash_invariant`, `kelly_zero:capped_zero`, `bear_defensive_slot_cap`,
  `bear_defensive_insufficient_cash`) is a genuine SIZING-stage failure, not an admission one.
- `RenQuant/backtesting/renquant_104/adapters/runner_trace.py::live_trace_selection_maps()` —
  pending (submitted, fill-unconfirmed) broker orders are swept into the same blocked-map via
  `out_blocked.setdefault(ticker, "broker_pending_submitted")` — SELECTED+SUBMITTED, not blocked.
  `live_execution_attempt_events()` — `broker_skip:{reason}` is a distinct post-selection
  broker-stage outcome.
- Anything not matching one of the above is reported as its own `unclassified` bucket and
  excluded from BOTH `n_survived_admission` and the blocked count — never force-fit (per the
  review's explicit ask). Verified against the real 10-run dataset: `n_unclassified == 0` on
  every run — the taxonomy is complete for what actually appears in this ledger today.

`n_survived_admission` (the sizing population) is now everyone EXCEPT true
`pre_selection_blocked` and `unclassified` names. A further, smaller fix: `broker_pending_
submitted` names with NO matching row in `trades` (fill genuinely unconfirmed at trace time)
have an UNKNOWN delivered weight, not a zero — folding that into `w_actual=0` would repeat
exactly the "undefined treated as a known value" error r2 already fixed for
`no_deployment`/`zero_dispersion` (finding 3). These are now counted in the sizing population
(`n_survived_admission`) but excluded from the correlation itself, reported separately as
`n_pending_unconfirmed` / `n_corr_population`. In the real dataset this count was 0 on every
run — every `broker_pending_submitted` name in this sample DID have a confirmed trade by the
time the trace was queried — so this caveat is currently inert but is load-bearing going
forward (a run queried shortly after submission, before fills settle, would hit it).

**Genuinely re-measured result (10 canonical daily runs, 2026-06-04 to 2026-07-01):**
- `measured`: 4 runs — buy_side_decision_tc = 0.588, 0.566, 0.0, 0.0 → mean 0.288, SE 0.167 (n=4)
- `insufficient_sizing_population`: 2 runs (the most recent two: 2026-06-30 and 2026-07-01),
  where `pre_selection_blocked` genuinely dominates (13/14 and 12/14 eligible names respectively)
  — a REAL result now, not a classification artifact, though still only 2 observations and not
  independently investigated here (see NEXT).
- The remaining 4 of the 10 canonical runs never reached `buy_side_decision_tc` at all
  (`n_eligible_by_mu < 4`, filtered before classification — unchanged mechanism from r1/r2).
- `n_pending_unconfirmed` is 0 on every run in this sample (see above).

This is a materially different, more mixed, and more honest picture than either r1's single
point estimate (0.09) or r2's uniform-100%-blocked artifact: most canonical days in this window
DO have a real sizing-stage TC to measure (mean 0.288, wide SE, n=4 — still far too small to
treat as a stable estimate), and the two most recent days show real, heavy pre-selection
blocking worth its own investigation, not a universal pattern across the whole sample.

**Tests:** `tests/test_poc_transfer_coefficient.py` — 3 new regression tests: a
`broker_pending_submitted` fixture proving it now reaches the sizing population (not the
pre-selection-blocked bucket) and is excluded from the correlation when unconfirmed; a
`size_insufficient_cash` fixture proving a real sizing failure counts as a genuine zero (unlike
a pending-unconfirmed name); an unrecognized reason-string fixture proving it lands in
`unclassified`, excluded from both sides. 12/12 tests pass (was 9).

**PR title corrected** (was headlined with the retracted r1 0.09/0.44 figures) via
`gh pr edit 234 --title`.

NEXT:     the two most-recent-day `insufficient_sizing_population` runs (heavy real
          `pre_selection_blocked`) are worth their own follow-up — which specific gate
          (`candidate_not_selected` vs `correlation` vs `tier`) is actually binding on those two
          dates, and is this a real recent shift or ordinary day-to-day variance given n=2. The
          `measured`-category mean (0.288, SE 0.167, n=4) is far too small a sample to treat as a
          stable TC estimate — do not cite it as a settled number. Full-book TC becomes a genuine
          same-day measurement once the S5 ledger persists per-run position values (unchanged
          from r1/r2). Codex review; #231's state vector (frozen under review, not touched by
          this PR) should pick up the corrected framing at its next revision.
