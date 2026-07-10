# Deployment Governor RFC — design

**Date**: 2026-07-09
**Status**: Design RFC (no behavior change)

## Bottom line

Full sizing-architecture redesign RFC per operator mandate (2026-07-09): replace
bottom-up multiplicative sizing (no deployment owner, 65% idle cash) with a
four-layer top-down design — dynamic regime-bounded deployment algorithm (aggregate
shrunk-Kelly, NOT a fixed number), concentrated conviction-weighted allocation,
integer-aware execution, staged long-short extension.

## Key evidence feeding the design

1. [VERIFIED] No component owns deployment — the only target-deployment concepts in
   the codebase are in the disabled QP and the passive benchmark sleeve
2. [VERIFIED] QP root cause: hard L1 turnover cap + 2% min-Δw floor interaction pins
   all new buys at ≈1.5% → dropped; both mitigations OFF in prod. Judgment: replace
   as primary sizer (keep as optional constraints-only projection), not repair —
   the replacement (`hybrid_option_f_allocator`, `fractional_kelly_top_k`) already
   exists in-repo with a replay harness and live shadow telemetry
3. [VERIFIED] conviction × sigma multipliers double-count μ/σ² on top of Kelly;
   `min_mult=0` zeroes at-floor names (cliff)
4. [VERIFIED] `panel_buy_top_n` is not in the active path — live initiation cap is
   `open_slots = max_concurrent_positions − held` (kills a recurring misattribution)
5. Config drift (ops note): umbrella-tree strategy_config.json copy is stale
   (fractional 0.5) vs pinned runtime config (0.3) — "merged ≠ deployed" again

## Changes

- `doc/design/2026-07-09-deployment-governor-rfc.md` — the RFC: architecture (L1–L4),
  deployment algorithm, evaluation protocol (end-of-chain preregistered replay with
  DeMiguel naive-diversification baseline arms), staged rollout (S0–S3), deliverable
  split across pipeline/strategy-104/orchestrator (D1–D8)

## Context

Supersedes knob-level Lane A framing (strategy-104 PRs #47/#48 closed; #49 one-share
floor stays as interim L3 measure). Evidence memo PR #442 reworked to
working-diagnosis status per Codex review and feeds this RFC.

## r4 update (2026-07-10)

Codex's r4 review (post cap-grid exploratory tuning run) raised four blockers, all
addressed in this round without touching the design's actual mechanics (the L2
allocator's down-only safety property was never broken — only the RFC's written
justification needed correcting):

1. **L1 candidate independence**: §2.1 now defines all three L1 candidates
   (regime-ceiling `E*_ceil`, `E*_kelly`, `E*_voltarget`) as fully independent
   formulas and states explicitly which one (`E*_kelly` only) is bounded by
   `E_raw` by construction. §2.2's feasibility claim was corrected — it had
   silently assumed the `E*_kelly` bound applies to all three candidates.
2. **Arm-specific gate contract**: the 12%-vs-20% cap contradiction is resolved
   by splitting the single-name-weight gate into a construction invariant
   (≤ the arm's own cap) and a separate operator-policy ceiling (12% to ENABLE
   without extra sign-off). Concentration-event and turnover-tax gates now have
   explicit formulas and frozen thresholds (D6 §2/§4).
3. **Fold construction**: D6 §2 now specifies deterministic contiguous 60-day
   blocks, walk-forward tuning/evaluation assignment with a 30-day embargo, and
   per-block HAC + inverse-variance-weighted pooling across blocks.
4. **Breadth-lever protocol**: cross-referenced to `renquant-strategy-104#52`,
   which was independently found to satisfy configurations/estimands/stop-rules/
   window/promotion-rule — with one flagged gap (no run-bundle fingerprint
   stamped per shadow session) noted as a follow-up to that PR, not fixed here.

## r4-correction update (2026-07-10, same day)

Codex then reviewed `strategy-104#52` DIRECTLY and found the r4 cross-reference
above premature: the within-shadow marginal-entrant decomposition + prod-XGB
counterfactual in #52 cannot identify the floor's causal effect once QP/sizing
interactions change portfolio weights, and the cross-repo protocol belongs in
orchestrator, approved BEFORE any strategy config is armed — not bundled into
a strategy-104 PR. `strategy-104#52` is now DRAFT pending this correction.

D6 §2a (new) replaces the #52 cross-reference with the actual protocol:
**two simultaneous isolated shadow arms** (S-0.5 = existing `shadow.json`;
S-1.0 = new `shadow_b.json`, identical except `buy_floor_std_mult`) instead of
one shadow arm decomposed after the fact — this makes the floor-effect
estimand (A) a true paired comparison with no hypothetical portfolio (both
arms actually execute, so real cost/tax applies automatically), and separates
it from a residual-environment diagnostic estimand (B: S-1.0 vs production)
that Codex's review showed the superseded design had conflated with the causal
claim. Also worked out, with the reasoning shown: the original ≥10-session HAC
test on 20d/60d overlapping returns is not adequately powered (effective
independent blocks `N_eff ≈ N/h` is ~0.5 at N=10,h=20 — far below the ~5-10
block reliability floor for HAC inference); replaced with a two-tier scheme
(directional-only kill-check at N=10, confirmatory HAC verdict gated on
`N_eff ≥ 8` matured observations, ~160 sessions for 20d / ~480 for 60d) plus a
predeclared 50bps/period non-inferiority margin. Infrastructure this requires
(new `alpaca_shadow_b` broker tag, parameterized `ReadOnlyBrokerWrapper`, a
new CLI surface, a `daily_104.sh` step, and strategy-104's `shadow_b.json`) is
specified concretely but NOT built in this doc-only PR — tracked as follow-up.
`strategy-104#52` will be resubmitted as a config-only treatment PR (just the
`shadow_b.json` + pin test) once §2a itself is reviewed and merged.

## r5 update (2026-07-10, same day)

Codex's r5 review accepted the r4-correction's two-arm causal structure but
raised four new blockers against §2a's implementation/inference contracts —
all addressed, with two honest capacity limits surfaced rather than papered
over:

1. **Repo boundary**: researched (not assumed) where broker/state abstractions
   actually live. Found: `state_paths.py`'s `ALLOWED_BROKERS` is already
   generic (adding a tag is a one-line pipeline change); `--strategy-config-name`
   already lets the CLI pick S-1.0's config with zero new umbrella code; but
   `ReadOnlyBrokerWrapper.broker_name` is a hardcoded class attribute in BOTH
   the umbrella's local copy AND an already execution-repo-resident,
   currently-unwired port (`renquant_execution.readonly_broker`) — no existing
   interface supports a second broker tag without a code change. Minimal fix:
   parameterize `broker_name` in the execution-repo copy (zero umbrella touch),
   and treat cutting `live/runner.py` over to import it (the actual umbrella
   change) as its OWN separately-gated follow-up PR — same shape as
   `RenQuant#454`→`renquant-execution#25` — not this protocol's decision to
   make. Added a caveat to the main RFC doc's repo-boundary table noting this
   explicitly, since the RFC's own "touches nothing in the umbrella" claim
   needed the same caveat.
2. **Self-containment**: inlined #52 §4's P2 definition, §6's gate table (now
   §2a's own dedicated table, not a cross-reference), and §9's decision-rule
   structure directly into D6 §2a, so a later strategy-104 config-only PR
   cannot alter the experiment contract by drifting. Added the fingerprint
   missingness rule: a mismatch invalidates the SESSION-PAIR in both arms (not
   just one), a block voids if >2 of its sessions are excluded, and the whole
   experiment voids (restart under a new protocol version) if cumulative
   exclusions exceed 20% of attempted pairs.
3. **Statistical redesign (the substantial fix)**: the r4 draft's "60-day
   calendar block + per-block Newey-West + inverse-variance pooling" was wrong
   on two counts — forward windows spill past block boundaries, and a block of
   daily 60d-forward-labeled observations contains only ~1 independent outcome
   regardless. Replaced with non-overlapping `h`-day OUTCOME blocks (one
   independent observation per block, ordinary t-test/permutation inference,
   no HAC needed) as a general method in §1.2, applied to both the general
   Phase-2 replay and §2a. Recomputed honestly on the ~497-session frozen pool:
   20d gives `N_eff=10` (usable, low-power); **60d gives `N_eff=3` — not enough
   for ANY significance test on this historical pool**, reported as
   directional-only indefinitely rather than forcing a number. PBO explicitly
   does not apply to §2a's 2-arm design (no combinatorial structure for CSCV);
   DSR does, deflated for 2 arms.
4. **Tier 1 threshold**: froze the vague "grossly adverse" language to an exact
   number — REJECT early iff the N=10 point estimate (P2, net of cost) is worse
   than −50bps/period (same magnitude as the Tier-2 non-inferiority margin, for
   consistency), checked at a SINGLE predeclared N=10 look (not repeated
   monitoring) — with the reasoning stated for why a single fixed look avoids
   the optional-stopping problem Codex flagged.

## r5 reconciliation (2026-07-10, second pass — two parallel r5 fixes merged)

Two sessions produced r5 fixes concurrently; this pass merges them (the
non-overlapping-outcome-block statistics and the two-contiguous-range replay
scheme from the first pass are kept in full) and resolves the divergences:

1. **Point 1 goes further — zero umbrella change, not a deferred umbrella
   PR**: additional read-only verification found the Step-4 shadow invocation
   is ALREADY orchestrator-mediated (`renquant_orchestrator live-bridge`,
   `daily_104.sh:599-609`, default `RQ_DAILY_RUNNER=multirepo`) and that the
   bridge aliases `kernel.state_paths` to the pinned pipeline. §2a now runs
   the second arm through the bridge's established interception surface (an
   orchestrator-owned `--bridge-broker-tag` that overrides the wrapper's
   class-attribute tag pre-handoff) plus an orchestrator-owned scheduled
   invocation — the first pass's execution-repo wrapper parameterization is
   retained as an optional durable-ownership migration, explicitly NOT a
   dependency. Also closed a real arm-asymmetry bug both passes' review
   surfaced differently: `runner.py:461` keys non-strict preflight on the
   exact tag `"alpaca_shadow"`, so `shadow_b.json` carries
   `live.preflight.strict=false` (two-key config delta, not one) to keep
   preflight semantics identical across arms; label/ntfy asymmetries
   disclosed as cosmetic with an env-var (`RENQUANT_NTFY_TOPIC`) mitigation.
2. **Point 2**: added to the bundle the calibrator sha and the
   renquant-execution pin; made the inclusion rule exact (completion, bundle
   presence, frozen-fingerprint match, same-world model/calibrator/manifest
   shas across arms); added an immediate treatment-fingerprint-drift ⇒ VOID
   rule on top of the block-void (>2 excluded pairs) and 20%-cumulative
   bounds.
3. **Point 3**: froze the enable-grade minimum at 8 matured non-overlapping
   blocks globally (§1.2), capped the daily NW plug-in lag at 10, and demoted
   60d to descriptive-only EVERYWHERE (removed the "60d verdict at 480
   sessions" Tier-2 path and the decision rule's "60d if matured" clause).
   Replay 20d `N_eff=10` clears the 8-block floor; 60d `N_eff=3` is
   descriptive-only.
4. **Point 4**: the first pass's single N=10 look at the P2 point estimate
   was incoherent (at session 10 zero 20d forward windows have matured — no
   P2 estimate exists to inspect). Replaced with two frozen mechanical NET
   kill rules: P1-kill (treatment deployed fraction < control − 5pp absolute
   as a 5-consecutive-session mean, from session 10) and P2-kill
   (marginal-entrant net 20d matured mean < −300 bps with ≥ 3 matured
   blocks), plus an explicit symmetric no-early-ENABLE clause (equal-sized
   favorable reads authorize nothing; enable only at ≥ 8 matured blocks).
