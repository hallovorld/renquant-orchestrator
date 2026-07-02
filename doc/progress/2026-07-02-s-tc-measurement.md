# S-TC transfer-coefficient measurement — research PR

STATUS:   research evidence (read-only; docs + one committed script + JSON evidence) —
          revised after Codex CHANGES_REQUESTED (5 methodology findings, all addressed below).
REVISION: r2.
WHAT:     task S-TC of the unified plan (#231 §1 Term TC): `scripts/poc_transfer_coefficient.py`
          + `doc/research/evidence/2026-07-02-roadmap-pocs/poc_stc_transfer_coefficient.json`.
          Produces an EXPLORATORY diagnostic — not measured-tier TC — for the reasoned "≈0.4"
          number in the #231 §0 state vector.
WHY/DIR:  IR = TC·IC·√BR — TC was asserted ≈0.4. r1 reported full-book TC 0.438/0.481
          (Pearson/Spearman) and buy-side decision-TC ≈0.09 and called this "the strongest
          quantitative justification measured so far for lane A + R4." Codex correctly rejected
          that framing on 5 independent grounds (below); r2 fixes the methodology and REMOVES
          the lane-A/R4 justification claim. The corrected buy-side measurement surfaces a more
          precise and arguably more important finding than r1's: see EVIDENCE.

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

NEXT:     the corrected diagnostic currently cannot report ANY sizing-stage buy-side TC — every
          canonical daily run's admission-surviving population is empty. Before this diagnostic
          can inform lane A / R4 at all, the `candidate_not_selected` / `broker_pending_submitted`
          / `size_insufficient_cash` / `correlation` admission-blocking rates themselves need
          their own investigation (a natural S-something follow-up: which gate is actually
          binding, and why does essentially no mu-floor-eligible candidate ever survive to
          sizing in this sample?) — that is a DIFFERENT, upstream question from "does sizing
          preserve conviction ordering," which this script cannot currently answer for lack of
          data. Full-book TC becomes a genuine same-day measurement once the S5 ledger persists
          per-run position values (unchanged from r1). Codex review; #231's state vector (frozen
          under review, not touched by this PR) should pick up the corrected framing at its next
          revision.
