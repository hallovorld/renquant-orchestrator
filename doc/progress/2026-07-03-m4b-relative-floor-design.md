# M4-b relative conviction-floor re-derivation — design PR

STATUS:   design RFC (docs only, design-via-PR); prerequisite for ever enabling pipeline
          #162's `recenter_raw_per_bar` (M4/BL-1). No config, pipeline, or behavior change.
WHAT:     `doc/design/2026-07-03-m4b-relative-conviction-floor.md` — restates the
          conviction floor's purpose from evidence, tables four candidate re-derivations on
          the recentered μ scale, freezes a matched-admission-rate evaluation protocol
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
          drift-immune, fresh-entrant-safe, zero residual tuning freedom under matched
          breadth); (b) dispersion-scaled μ ≥ k·MAD (CHALLENGER — honest zero-admission
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
          by this doc); recorded winner/no-winner verdict; if winner — ONE combined
          strategy-104 config PR (recenter ON + new floor, active+golden lockstep, via
          promote_pin); if no winner — pre-registered NULL route (M4 stays dark, BL-4
          permanent).
