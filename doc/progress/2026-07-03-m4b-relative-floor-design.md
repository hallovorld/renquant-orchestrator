# M4-b relative conviction-floor re-derivation — design PR

STATUS:   design RFC (docs only, design-via-PR); prerequisite for ever enabling pipeline
          #162's `recenter_raw_per_bar` (M4/BL-1). No config, pipeline, or behavior change.
          Round 2 (2026-07-03): tightened the promotion contract per Codex review — see
          ROUND 2 below.
WHAT:     `doc/design/2026-07-03-m4b-relative-conviction-floor.md` — restates the
          conviction floor's purpose from evidence, tables four candidate re-derivations on
          the recentered μ scale, freezes a TWO-STAGE (replay-nomination →
          prospective-shadow-confirmation) matched-admission-rate evaluation protocol
          (the fair comparison M3 lacked), and pins the interaction contracts (A-2/top_n,
          QP budget, Kelly sizing, demean stays OFF, BL-4 permanent) plus the one-combined-
          flip enable sequencing with M4.
WHY/DIR:  #162's own shadow replay shows the absolute `mu_floor=0.03` was gating the
          calibrator's +2–3% drift intercept, not conviction: post-recentering it admits
          ~0–1 names on the drifted June cross-sections (22→1, 17→1, 18→1, 18→0) — the same
          absolute-bar-on-relative-quantity algebra as the 2026-06-29 demean incident.
          Enabling M4 with today's floor is a known footgun (check-existing-contract
          lesson); the floor must be re-derived as a RELATIVE quantity first.
          Candidates: (a) cross-sectional quantile floor (PRIMARY — breadth-stable,
          drift-immune, fresh-entrant-safe, one parameter pinned by matched breadth, NOT
          "zero tuning freedom" — family selection remains, hence the two-stage gate);
          (b) dispersion-scaled μ ≥ k·MAD (CHALLENGER — honest zero-admission
          semantics, needs a consecutive-zero alarm); (c) re-anchored absolute ~cost-hurdle
          (fallback baseline — re-drifts by construction); (d) NGBoost σ-band μ − k·σ > 0
          (deferred — σ head trained+promoted but σ-wire OFF per the 2026-05-17 A/B
          all-NULL/negative record; reopening it is its own decision, cited honestly, not
          re-pitched as free).
EVIDENCE: pipeline #162 PR body + committed shadow-replay JSON (replay reproduces prod μ
          and the 44/45 laundered counters exactly); RS-2 descriptive 80–88% thin-margin
          pool; M3 AC-FAIL replay (margin ⊥ stability; haircut removed more winners than
          losers at 20d); OXY/GRMN fresh-entrant forensics; strategy-104
          2026-06-29-conviction-gate-demean-revert.md (the precedent incident); umbrella
          failed-experiments-log 2026-05-17 σ-wire A/B.
NEXT:     review; then a separate replay-implementation PR (read-only DB, parameters frozen
          by this doc); recorded Stage 1 candidate-for-shadow/no-winner verdict; if a
          Stage 1 nominee — shadow deployment over a prospective window, then a Stage 2
          confirmatory re-check; if Stage 2 confirms — ONE combined strategy-104 config PR
          (recenter ON + new floor, active+golden lockstep, via promote_pin); if no Stage 1
          nominee or Stage 2 fails — pre-registered NULL route (M4 stays dark, BL-4
          permanent).

ROUND 2 (2026-07-03) — Codex review response:
  1. "Zero tuning freedom" was overstated: matched breadth pins each candidate's ONE free
     parameter, but still selects AMONG rule families on the same window whose forward
     outcomes then judge the winner — in-sample family selection, not a frozen contract.
     Fixed by splitting promotion into two stages (§3, §4, §6 of the design doc): Stage 1
     (this replay) may only nominate a `candidate-for-shadow`; Stage 2 requires a
     prospective shadow window on untouched sessions, re-checked against the SAME frozen
     criteria (confirmatory, not exploratory), before a strategy-104 config PR is
     authorized. Reuses the identical nominate-then-confirm structure already applied to
     `renquant-backtesting` #61's WF-gate threshold this session.
  2. Mean-matched breadth alone doesn't protect the A-2/selection-budget contract: two
     rules can share a mean admitted count and differ sharply in top_n saturation
     frequency, p90/p95 admitted-count, QP spill pressure, and consecutive zero-admission
     streak length. Fixed by adding all four as pinned, pre-registered comparison metrics
     (§4) and a new Stage 1 win criterion (must match baseline within a pre-registered
     tolerance on all four, not just the mean).
  3. Section 6 (immediate strategy-104 config PR after a replay winner) contradicted
     Section 7's own admission that resolved outcomes are retired-era/BULL_CALM-dominated
     and any winner is provisional. Fixed by inserting the Stage 2 shadow-then-confirm step
     between "replay winner" and "live enable" in the rollout (§6), and updating the
     opening BLOCKING CONTRACT (§0) to require a Stage-2-CONFIRMED winner, not a Stage-1
     replay verdict alone.
  Verified: `python3 scripts/require_progress_doc.py` still finds this doc in the diff
  (only content within the existing files changed, no new/removed doc files).
