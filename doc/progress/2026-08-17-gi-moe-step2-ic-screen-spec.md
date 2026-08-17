# G-I MoE step 2 — frozen IC-screen spec (doc only)

STATUS:    frozen experiment spec for review. Docs only — the scoring run happens ONLY
           after this merges (freeze-before-run).

WHAT:      Commit `doc/research/2026-08-17-gi-moe-step2-ic-screen-spec.md`: the kill-only
           cheap IC screen for the three step-1 emitters (model#227). Frozen: corpus
           (2019-01-14..2026-03-02, weekly, current watchlist with the survivorship
           caveat stated and its kill-validity argument), estimand (weekly cross-sectional
           Spearman IC of RAW scores vs h-day forward excess over SPY; 2h-lag placebo;
           differences only), effective sample counted BEFORE the rule (n_eff≈51 h=20 /
           ≈16 h=60; 89/29 non-overlapping blocks; block-t inference), the kill rule
           (Δ>0 AND block-t≥1.0 AND >50% positive blocks at h=20; one shot, no re-run,
           no horizon rescue), and the informational ρ matrix for the downstream |ρ|<0.7
           roster gate.

WHY/DIR:   Design #984 §5 step 2 (approved 08-17): candidates walk a cheap screen BEFORE
           any prereg cathedral; the screen kills, never admits. Spec frozen before any
           candidate score exists on the corpus — the #975/#976 lesson
           (effective-sample-before-decision-rule) applied prospectively.

EVIDENCE:
  artifact:      the spec + this doc. No code, no scoring run, no live change.
  prod or exp:   neither — spec only; the run is a later, separate results PR.
  existing data: [VERIFIED] corpus bounds/1,792 td from the #984 §3 measured window;
                 emitter floors from model#227's frozen params. [DERIVED, frozen]
                 n_eff (overlap ρ≈(h−5)/h → ≈51/≈16) and block counts (89/29).
  best-known?:   yes — kill-only semantics make the screen's known weaknesses safe:
                 survivorship inflates ICs → kills stay valid, passes stay
                 non-confirmatory; low n_eff at h=60 → h=60 demoted to informational;
                 lenient t≥1.0 is the kill-only asymmetry (no multiplicity needed
                 because nothing is admitted here — the confirmatory Holm family lives
                 in #984 §5b). Regime-blind by design pending #985 plane consolidation.
  scope:         "freezes the step-2 screen. Authorizes the ONE scoring run after merge
                 (read-only inputs, isolated worktree, results as a separate PR) and
                 nothing else: no admission, no scheduling, no deploy, no regime cells."

TESTS:     none — doc-only PR.

NEXT:      codex review → merge → the one screen run → results PR with verdicts →
           survivors proceed to the #984 §5b manifest freeze (which itself waits on the
           serving-plane power-map re-derivation per #985).
