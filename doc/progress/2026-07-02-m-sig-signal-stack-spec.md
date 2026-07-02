# M-SIG signal-stack spec — design PR

STATUS:   design / pre-registration scaffold (docs only; each candidate's build lands as its
          own PR citing this table's frozen threshold).
REVISION: r1.
WHAT:     `doc/design/2026-07-02-m-sig-signal-stack-spec.md` — the MID-term IC core (#231
          Term IC): four candidates with estimand, substrate, prior-evidence tier, FROZEN
          individual threshold, earliest test date, and kill condition. C1 estimate-revision
          drift (needs ≥6mo N2 accrual → 2027-Q1); C2 quality composite (re-test justified
          ONLY by the FMP coverage delta ≥20%, else the measured NULL stands); C3
          regime-conditioned RESIDUAL momentum (only the untested residual×regime cell —
          raw momentum NULL not re-litigated); C4 trend-scanning label (#176's
          promote-to-proper-gate result, unlocked by the S1–S3 gate repair). Design rules:
          S5/S8 substrate only, placebo-clean differences only, per-regime cuts mandatory,
          orthogonality measured per pair (extends POC-D), one candidate PR at a time,
          misses recorded-and-dropped.
WHY/DIR:  G106 (≥2 signals ≥0.015, combined ≥0.02) is the plan's central coin flip; freezing
          the thresholds BEFORE any measurement is the prereg discipline (#230 §1), and the
          sequencing note protects against a premature kill: the branch cannot fire before
          C1's accrual window (the strongest, truly-orthogonal leg) has run — killing the
          stack before its best leg is measurable would be a sequencing artifact.
EVIDENCE: #176 trendscan evidence doc (3/3 seeds +0.0149 BULL_CALM placebo-clean, absolute
          ICs embargo-floored); fundamentals_scan + regimemom measured NULLs (scope of what
          is NOT re-tested); POC-D ρ=0.217 stacking math; revision-drift literature (cited
          tier, pre-halved per McLean–Pontiff).
NEXT:     Codex review; C3/C4 build PRs may start Q3 (C4 waits on the S3 placebo-difference
          margin being frozen in the gate-repair PR); C2 waits on the N3 coverage verdict;
          C1 waits on N2 accrual — one more reason the collector/snapshotter installs are the
          binding step.

## R2 (2026-07-02, Codex review): closed every open researcher degree of freedom

**Finding.** r1 claimed thresholds were "frozen" but every candidate left substantial
parameters unspecified: C1's 1m/3m window, FY1/FY2 blend, and update handling were all
open; the 0.015/0.010 go-kill bars had no stated power/CI rule despite C1's 6-9mo accrual
window plausibly yielding only 6-9 independent monthly observations; C2's composite
construction and "beats thin-panel by a stated margin" were unfrozen; C3's regime pooling,
residualization fit window, beta/sector definitions, and CI/block method were all open; C4
explicitly deferred its placebo margin to a later PR while the document claimed frozen
status — a direct contradiction. There was also no multiplicity control across 4 candidates
× windows × regimes × seeds × composite variants, no distinction between prior-inspected
and genuinely prospective evidence, and the "wait for strongest leg" sequencing rule
permitted optional stopping with no defined end state if nothing ever clearly won.

**Fix.** Rewrote §1 from a summary table into full per-candidate specifications (feature
formula, as-of lag, universe/missingness, forward-return horizon, IC estimator/aggregation,
CI methodology, minimum effective sample size, deterministic go/kill/inconclusive rule) for
all four candidates:
- **C1**: closed to 1m/FY1-only (3m and FY2 blending dropped from the frozen gate). The
  power problem is real — an illustrative calc shows monthly cadence would need ~274 months
  to reach conventional power at a plausible σ, which is not a number to build a decision on
  (the real σ doesn't exist yet). Resolved by explicitly DOWNGRADING C1 to informative-only:
  it never independently gates GO/KILL; it is read (not decided) at 6mo and 9mo checkpoints
  and the G106 stack vote (§3) is computed over C2/C3/C4 only unless C1 someday reaches a
  genuinely powered read.
- **C2**: composite frozen as an equal-weight z-score blend (no PCA/IC-weighted search);
  clarified it CAN use the shared block-bootstrap default (daily cross-sectional IC over the
  full historical panel), unlike C1, since the quarterly refresh cadence of the underlying
  fundamentals doesn't limit a daily IC test the way N2's real-time-only accrual limits C1.
- **C3**: regime pooling frozen (BULL_CALM+BULL_VOLATILE pooled, not separately gated);
  residualization fit window frozen (rolling 252-day OLS); beta/sector definitions pinned to
  this repo's existing production series (cite exact source in the build PR); CI/block
  method resolved to block=60 (the shared default, matching fwd_60d) — the "block=13"
  question in r1's open items was based on a convention that was never actually adopted
  anywhere in this repo; the only extant block-bootstrap implementation
  (`research_panel_exit_predictiveness.py`) always sets block to the label horizon. Added an
  explicit prospectivity-affirmation requirement for the build PR (must state no prior
  script computed this exact residual×regime combination before this freeze date).
- **C4**: placebo-difference margin frozen at 0.02 NOW (was deferred to the S3 PR in r1 —
  justified against the measured ~+0.04 shared embargo-leakage floor); non-inferiority
  defined concretely (sim Sharpe does not fall >0.1 vs raw); explicitly labeled #176's
  +0.0149 as retrospective/exploratory — it justifies promoting to a proper-gate test but
  is NOT itself C4's confirmatory result.
- **Multiplicity (new §2a)**: a fixed hierarchical testing order (C3 → C4 → C2 → C1-
  informative-only) rather than a formal correction, since Bonferroni would compound C1's
  power problem onto every candidate.
- **Sequencing (rewritten §3)**: a genuine deterministic stack decision rule replacing "wait
  for strongest leg" — a hard 2027-Q4 deadline, an explicit INCONCLUSIVE (not KILL) outcome
  for underpowered candidates, a precise ≥2-of-N_resolved GO rule, and an "early GO but no
  early KILL" asymmetry preserving r1's original correct concern (don't kill before the
  strongest legs are measurable) while adding the missing hard stop at the other end.

**Honest freeze status** (stated explicitly in the doc's own header, not just this progress
doc): C2, C3, C4 are genuinely frozen — every parameter fixed. C1 is frozen on methodology
but its go/kill bar's statistical power is honestly unresolved pending real data; it may not
gate the stack until that's checked, which is itself a frozen (not tunable) rule.

Commit: see PR history. Files: `doc/design/2026-07-02-m-sig-signal-stack-spec.md` (full
rewrite of §1, new §2a, rewritten §3, §4 items marked resolved), this progress doc.
