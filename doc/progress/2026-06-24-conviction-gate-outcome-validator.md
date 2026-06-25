# Conviction-gate outcome validator — the postmortem's data-backed-enable engine

STATUS:   PR. New read-only analysis tool; no runtime/production change.
WHAT:     `scripts/validate_conviction_gate.py` — joins the accumulating decision ledger
          (`candidate_scores`: per-run per-name calibrated mu) to the panel dataset's REALIZED
          `fwd_60d_excess`, and compares what RAW (mu>=floor) vs DEMEAN (mu-full_xs_mean>=floor,
          pipeline #147) WOULD admit and how those names actually performed, per regime. Emits
          `demean_minus_raw_mean_fwd` + `dropped_by_demean_mean_fwd` (the causal number) + a
          DEMEAN_BETTER / NOT_BETTER verdict.
AGE GATE: a ledger date counts as aged only if `date <= as_of - horizon_days` (real elapsed
          time), enforced via `--as-of` (default today). Dataset `fwd_60d_excess` being present
          is NOT proof the horizon closed — a regenerated label column can carry look-ahead, so
          counting it would validate on un-realized returns (codex #190 catch).
GUARDRAIL: the `verdict` is DIRECTIONAL ONLY (a sign over `aged_dates` dates), NOT a significance
          test. The payload carries a `caveat` saying so — this enable engine must not flip
          production config without a bootstrap CI + per-regime consistency.
WHY-DIR:  Phase 4 of the model-fixes-cant-reach-production postmortem (#189): a gate change is
          only "done" with a ledger accruing the evidence to make it live. This is that engine —
          it turns "enable on faith" into "enable on data".
HONESTY:  run against live data today → INSUFFICIENT_AGED_LEDGER (45 ledger dates, 0 with
          realized 60d returns — the mu column only populates since the calibration feature
          shipped, all <60d old). It reports that plainly instead of a misleading number, and
          AUTO-CLOSES as the ledger ages (~60d). This is the chicken-and-egg the postmortem
          named, now on the clock.
EVIDENCE: 3 unit tests (synthetic): INSUFFICIENT path; DEMEAN_BETTER case where demean drops a
          realized loser (asserts the causal dropped<0 + caveat); not-yet-aged rows with fwd
          present still INSUFFICIENT (age-cutoff regression). `[VERIFIED — pytest + live dry-run]`
NEXT:     demean (#147) is justified to enable now on ADMISSION-behaviour validation (20 live
          runs, 0/20 zero-buy days, drops intercept buys) + first principles; this validator is
          the OUTCOME check that closes once the ledger has >=30 dates of realized 60d returns.
          Reusable for the #51 momentum guard and any future gate.
