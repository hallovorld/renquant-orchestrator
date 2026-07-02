# C3 regime-conditioned residual momentum — exploratory measurement (UNADJUDICATED)

STATUS:   EXPLORATORY/SENSITIVITY research evidence (read-only measurement; one committed
          script + committed JSON evidence + memo). Was submitted as C3, the first
          formally-voting M-SIG candidate under the merged frozen spec (#243) — Codex round-2
          review found this run's regime-label + universe substrate carries future
          contamination, disqualifying it from casting a formal confirmatory vote.
          VERDICT: UNADJUDICATED (substrate/provenance limitation), NOT MISS. C3 remains OPEN.
REVISION: r2.
WHAT:     `scripts/c3_residual_momentum.py` + `doc/research/evidence/2026-07-02-c3/*.json` +
          `doc/research/2026-07-02-c3-residual-momentum.md`. Measures spec section 1.3:
          mom_12_1 rank-z'd, per-date OLS-residualized to sector dummies + trailing-252d
          market beta, scored ONLY in the pooled BULL_CALM+BULL_VOLATILE cell, placebo-clean
          (label shifted +horizon) per-date Spearman IC vs fwd_60d excess-SPY, moving-block
          bootstrap (block=60, n_boot=2000, seeds 42/43/44), one-sided 98.33% Bonferroni CI.
          Regime labels: the PRODUCTION task chain (pinned pipeline + pinned strategy config +
          prod GMM artifact) replayed sequentially per the build_regime_series reference.
WHY/DIR:  spec section 2a ordering — C3 is the cheapest/soonest-ready voting candidate (data
          exists now); its verdict is one of the >=2 GO votes G106 needs by 2027-Q4. The
          conditioned residual×regime cell had not been computed by an identical prior script
          (2026-06-23-residual-audit residualized the LABEL, regimemom used raw momentum on
          non-production regime labels) — but per round-2 review, that novelty check alone
          does not establish genuine prospectivity/preregistration (memo section 8, corrected).

EVIDENCE:
```
artifact:      scripts/c3_residual_momentum.py (one-command reproduce, umbrella venv) +
               doc/research/evidence/2026-07-02-c3/{c3_results,c3_per_date_ic_fwd60,
               c3_regime_series}.json (committed outputs, input SHA-256 manifest inside)
prod or exp:   experiment — read-only research measurement, no config/order/gate change
existing data: umbrella data/ohlcv/<T>/1d.parquet (142 transformer-panel tickers + SPY,
               2016-01-04..2026-07-01, split-adjusted, verified no split seams), pinned
               strategy_config.json sector_map/benchmark, prod spy-gmm-regime.json
               (trained 2026-05-22), pinned renquant-pipeline regime task chain
best-known?:   best-available EXPLORATORY substrate — the spec's S5/S8 pick-table/ledger has
               no multi-year history yet; deviation stated in memo section 7. NOT best-known
               for a CONFIRMATORY vote: two forms of future contamination disqualify it
               (regime labels reconstructed with today's GMM+config replayed backward to
               2016; universe fixed at today's 142-name panel applied retrospectively).
               Searched this codebase for a point-in-time alternative (historical
               production-emitted regime labels, point-in-time universe/delisting data) —
               neither exists; genuine point-in-time reconstruction is out of this fix's
               scope (see memo section 6 for the investigation).
scope:         C3 ONLY (one candidate PR at a time, design rule 5); C4/C2 unaffected. Does
               NOT close C3 — see NEXT.
result (exploratory, not confirmatory):
               conditioned placebo-clean IC -0.0040 (n=1833 daily dates, bar +0.015;
               98.33% one-sided LB ~-0.05 to -0.06 across seeds after the round-2 bootstrap
               fix) — leg (a) fails the bar on this exploratory run; conditioned-minus-
               unconditioned +0.0086 but every CI (95% and 98.33%) includes 0 — leg (b) also
               fails. KILL triggers do not fire (cond > uncond point-wise; UB ~+0.047 not
               < 0.015). Raw real IC in the cell +0.0253 is fully explained by placebo
               +0.0275 — apparent bull-regime momentum IC is label-persistence structure,
               not alpha, in this run. Sensitivities (dispatch bundle, block13, beta120) all
               agree in direction. None of this is eligible to cast C3's formal vote given
               the substrate contamination above.
```

Round-2 fixes applied (full detail in memo sections 6-11): (1) VERDICT changed MISS ->
UNADJUDICATED, "C3 is CLOSED" language fully withdrawn — a substrate-contaminated run cannot
close a candidate under design rule 5, which presumes a valid confirmatory test; (2) removed
the unsupported "survivorship makes the result conservative" claim — bias direction is not
identified; (3) weakened the prospectivity claim — "no identical prior script" does not
establish genuine preregistration, especially with 2 acknowledged prior momentum-family
audits and same-day spec+result dating; (4) fixed the conditioned-cell bootstrap
(`block_bootstrap_conditional_mean` replaces pre-filtered `block_bootstrap_means` — the old
version could splice regime episodes separated by a calendar gap into one artificial
60-day block; new `tests/test_c3_residual_momentum.py`, 4 tests, proves the fix at the
single-block level). Point estimates unchanged by the bootstrap fix; CIs shift slightly.

[VERIFIED — searched `/Users/renhao/git/github/RenQuant` (including `.subrepo_runtime`
sources and the `runs.alpaca.db` schema) directly for historical production-emitted regime
labels and point-in-time universe/delisting data; both searches returned zero results,
confirming the substrate contamination has no in-scope fix. Re-ran
`scripts/c3_residual_momentum.py` end-to-end against real read-only production stores after
the bootstrap fix (~4 min, umbrella venv); output numbers above are read directly from the
regenerated `doc/research/evidence/2026-07-02-c3/c3_results.json`, not from memory.
`tests/test_c3_residual_momentum.py` (4 tests) run and passing.]

Interpretations resolved (full list stamped in c3_results.json + memo section 5): block=60
NOT 13 (merged spec r3 section 4 Q2 explicitly resolved the "A1 convention block=13"
question; block=13 reported as sensitivity, same verdict); beta window 252d spec-frozen
(dispatch's 120d = sensitivity); DAILY decision dates (stride-21 cannot meet the n>=600
floor — it yields 89 conditioned dates); verdict on fwd_60d (strategy horizon), fwd_20d
supporting; difference CI is PAIRED (blocks over the full series, mean(cell)-mean(all) per
resample). No frozen threshold altered anywhere.

NEXT:     C3 remains OPEN — this run does not close it. Either (a) build genuinely
          point-in-time regime labels + universe membership and rerun (materially larger
          effort, not attempted here), or (b) an explicit operator/design decision to accept
          this substrate as a permanent limitation and re-adjudicate C3 under an amended,
          honestly-scoped protocol. The M-SIG stack's dependency on C3 (spec section 2a,
          alongside C4/C2, G106 needs 2 of 3 GO) is UNRESOLVED, not satisfied. Codex
          re-review of this round's fixes; do not treat the exploratory statistics above as
          having settled the underlying hypothesis.

## Round 3 (Codex review: evidence-surface blockers)

**Finding.** Round 2's substantive fixes (UNADJUDICATED reclassification, bootstrap fix)
were confirmed correct, but two evidence-integrity gaps remained: (1) the input
`sha256` manifest hashed config/GMM-artifact/regime-code/ticker-list but NOT the 142
ticker OHLCV parquets or SPY parquet — the actual dominant numeric inputs feeding every
signal/label/beta/regime feature — so the same commit+manifest could silently produce
different evidence after a bar correction or data refresh; (2) the CLI's final printed
output still led with `{"VERDICT": v["verdict"]}` (emitting the raw mechanical rule's
`MISS`), a split surface from the doc's authoritative `UNADJUDICATED` status that could let
an operator or downstream automation mistake this exploratory run for a formal vote.

**Fix.**
- New `canonical_panel_sha256()`: hashes the EXACT aligned `close`/`spy_close` panel
  actually consumed by the computation (sorted columns, fixed 10-decimal float precision,
  NaN-safe) rather than re-reading 143 files separately — records `close_panel_sha256`,
  `spy_close_sha256`, shape, sorted column list, and date range in `manifest.inputs_sha256`.
  4 new tests prove: a single mutated price in one ticker changes `close_panel_sha256` but
  not `spy_close_sha256` (and vice versa for a mutated SPY price); identical panels hash
  identically across independent calls.
- CLI's final print now leads with `ADJUDICATION_STATUS` (mirroring
  `results["adjudication_status"]`) as the headline; the old `VERDICT` key is renamed
  `MECHANICAL_RULE_OUTPUT` and explicitly carries `"voting": false` plus a
  `non_voting_reason` pointing back to the authoritative status. Searched the full doc,
  progress doc, and committed evidence JSON for any remaining unqualified
  `VERDICT=MISS`/`CLOSED` language — none found; every existing occurrence is already
  qualified from round 2 (e.g. "VERDICT: UNADJUDICATED ... NOT MISS").
- `worktree_head` resolution replaced: was a raw `.git/HEAD` file read (fragile in a linked
  worktree, where `.git` is a file pointing at the main repo's git-dir, not a directory —
  can fail or return a ref name instead of a commit SHA) with `git rev-parse HEAD` via
  subprocess. New test asserts the resolved value is a genuine 40-char hex commit SHA in
  THIS actual linked worktree (the exact environment class the old approach could break in).
- 8/8 tests pass (4 from round 2 + 4 new this round).

**Re-verified (2026-07-02, real read-only production stores, corrected provenance):**
point estimates unchanged from round 2 (conditioned_mean_clean -0.00399, unconditional_mean
-0.01262, difference +0.00863) — this round only strengthens evidence provenance and the
CLI's authoritative-status surface, not the statistical methodology (already fixed round 2).
Manifest now records `close_panel_sha256`/`spy_close_sha256` over the real 142x2638 panel
(2016-01-04 to 2026-07-01) plus a properly-resolved `worktree_head`.

[VERIFIED — re-ran `scripts/c3_residual_momentum.py` end-to-end against real read-only
production stores after this round's fix; the printed CLI output was captured directly and
confirmed `ADJUDICATION_STATUS: "UNADJUDICATED"` leads the JSON with `MECHANICAL_RULE_OUTPUT`
carrying `voting: false`; the regenerated `doc/research/evidence/2026-07-02-c3/c3_results.json`
was inspected directly for the new `inputs_sha256` fields, not read from memory.
`tests/test_c3_residual_momentum.py` (8 tests) run and passing.]
