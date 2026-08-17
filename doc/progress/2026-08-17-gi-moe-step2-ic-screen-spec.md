# G-I MoE step 2 — exploratory IC-screen spec (doc only)

STATUS:    exploratory triage spec for review. Docs only. **The screen cannot kill a
           candidate**, and the scoring run happens only after this merges AND after the
           runner is committed and reviewed (§7 of the spec). Revised 2026-08-17 from a
           "frozen kill-only" claim after codex review — see WHAT.

WHAT:      `doc/research/2026-08-17-gi-moe-step2-ic-screen-spec.md`: the cheap IC screen
           for the three step-1 emitters (model#227). Fixed before any candidate score
           exists: corpus (2019-01-14..2026-03-02, weekly, current watchlist), estimand
           (weekly cross-sectional Spearman IC of RAW scores vs h-day forward excess over
           SPY; 2h-lag placebo; differences only), effective sample counted BEFORE the
           rule (n_eff≈51 h=20 / ≈16 h=60; 89/29 non-overlapping blocks; block-t
           inference), the triage rule (Δ>0 AND block-t≥1.0 AND >50% positive blocks at
           h=20; one shot, no re-run, no horizon rescue), and the informational ρ matrix
           for the downstream |ρ|<0.7 roster gate.

           **Two claims were WITHDRAWN, not patched, after codex review:**

           1. *(MED)* The survivorship argument. The first draft asserted that a
              current-survivor universe INFLATES measured ICs, so kills computed on it
              were "safely valid". That is not true: survivorship does not monotonically
              inflate every factor's IC or every genuine-minus-placebo Δ, and the
              plausible mechanisms run the WRONG way for two of these three candidates —
              `lowbeta` (survivors over-represent names that carried and survived high
              beta, compressing or inverting the low-beta edge) and `quality_gp`
              (survival is partly quality-selected, so the surviving cross-section has
              less quality dispersion, depressing a rank IC). A low Δ here can therefore
              be an artifact of the universe. Since the entire kill-validity argument
              rested on that monotonicity, the kill semantics went with it: the screen
              now FLAGS (deprioritises), and a kill requires a point-in-time rerun.

           2. *(HIGH)* The deferred runner. The first draft let the derivation script
              arrive with the results, which left block assignment, missing-data
              handling, the common genuine/placebo date set, minimum names per
              cross-section and per block, tie behaviour, and the exact ρ aggregation
              mutable AFTER the spec was visible — the precise freedom a frozen spec
              exists to remove. The spec now requires the runner committed and reviewed
              BEFORE any scoring run, and the emitter identity pinned to a MERGED
              renquant-model commit, never a branch. model#227 was open — hence
              mutable — while this spec was under review; it merged at
              2026-08-17T22:31:52Z, so the spec now carries the commit
              (74c22647a788...) instead of only the requirement.

WHY/DIR:   Design #984 §5 step 2 (approved 08-17, MERGED): candidates walk a cheap screen
           BEFORE any prereg cathedral. The screen's job is to order the queue, not to
           end an inquiry. Fixing the estimand before any candidate score exists is the
           #975/#976 lesson (effective-sample-before-decision-rule) applied prospectively;
           the withdrawal above is the OTHER half of the same lesson — a decision rule is
           only as strong as the corpus argument under it, and this corpus does not
           support a final kill.

EVIDENCE:
  artifact:      the spec + this doc. No code, no scoring run, no live change.
  prod or exp:   neither — spec only; the run is a later, separate PR, and is now gated
                 on a committed runner rather than on this merge alone.
  existing data: [VERIFIED] corpus bounds / 1,792 td from the #984 §3 measured window;
                 emitter floors from model#227's frozen params. [DERIVED, frozen]
                 n_eff (overlap ρ≈(h−5)/h → ≈51/≈16) and block counts (89/29).
  best-known?:   yes, at the reduced claim. The screen's weaknesses are now handled by
                 SCOPE rather than by an argument that they are harmless:
                 survivorship direction is unknown → the screen cannot kill, only flag;
                 low n_eff at h=60 → h=60 is informational, never decisive;
                 lenient t≥1.0 → no multiplicity correction is needed because nothing is
                 admitted OR killed here, and the confirmatory Holm family lives in
                 #984 §5b. Regime-blind by design pending #985 plane consolidation.
                 The earlier "kill-only semantics make the weaknesses safe" reasoning is
                 withdrawn; it was the defect, not the mitigation.
  scope:         "fixes the step-2 screen's corpus, estimand and thresholds. Authorizes
                 NOTHING to run on its own: the scoring run additionally requires the
                 committed, reviewed runner and a merged-commit emitter pin. No kill, no
                 admission, no scheduling, no deploy, no regime cells."

TESTS:     none — doc-only PR.

NEXT:      codex re-review → merge → **runner PR (committed guards + merged-commit pin)**
           → the one screen run → results PR with triage verdicts → not-flagged
           candidates proceed to the #984 §5b manifest freeze (which itself waits on the
           serving-plane power-map re-derivation per #985); flagged candidates proceed
           only after a point-in-time rerun.

HANDOVER:  this PR was opened by a concurrent Claude session that has since ended (its
           socket is gone and it no longer lists). I picked it up rather than let a
           CHANGES_REQUESTED PR sit unowned; the review response is mine.
