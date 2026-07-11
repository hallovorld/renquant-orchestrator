# Design (F4): Regime-scoped consequences for freshness-override promotions

STATUS: **design for review — operator decision required at merge.** This document
AMENDS the operator's recorded 2026-06-30 model-freshness directive ("freshness >
strict gate; if a fresh retrain fails its gate, use the best model from the last
10 days" — RFC #210 lineage, `doc/design/2026-06-30-model-freshness-governance.md`).
It does NOT relitigate that directive: overrides stay. It adds one missing clause —
**when an override promotes a gate-FAILING model, the regimes that model FAILED in
carry consequences.** No implementation in this PR; per-repo implementation PRs
follow only after the operator signs off on this amendment.

## 1. Problem — the override is regime-blind, and it just cost us

Evidence base (PR #476, H4 — independently re-verified 2026-07-11 directly from the
live artifact's `wf_gate_metadata`, sealed in hallovorld/renquant-artifacts#19):

- The live XGB primary's OWN gate metadata records, at promotion time:
  - `wf_reason` **FAIL**,
  - sanity **FAIL**, specifically `sanity_regime_ic` **FAIL in BULL_CALM**,
  - `trade_monotonicity` **FAIL** — the BULL_CALM top-vs-bottom entry-rank spread
    was **inverted: −13.7pp** (top-ranked entries UNDERPERFORMED bottom-ranked),
  - `manual_override = true`, promoted **2026-07-06**.
- Four days later (2026-07-10) the META misread — the model held a top-decile-fading
  score on META through a +12% week — happened **exactly in BULL_CALM**, the one
  regime its own gate metadata had flagged as failing on BOTH the regime-IC and
  monotonicity axes (PR #475/#476 forensics).

The gate did its job: it named the failing regimes before promotion. The 06-30
policy, as written, then promoted the model **for all regimes uniformly** — the
override discarded exactly the per-regime information the gate had produced. This
is not an argument against the override (staleness is still the more certain risk,
per RFC #210 §1); it is an argument that an override should not silently grant a
gate-FAILING model full authority in the regimes where it demonstrably failed.

## 2. Principle

> A freshness override buys the model's **freshness**, not its **regime record**.
> The failed-regime set is extracted mechanically from `wf_gate_metadata` at
> promotion time and travels with the artifact; sessions whose decision-time
> regime is in that set apply a configured consequence.

Two hard invariants, inherited from adjacent designs and NOT negotiable here:

1. **Exits are never touched.** Consequences apply to buy-side scoring/admission/
   sizing only — the same "risk exits always run" choke-point discipline Codex
   enforced on `DataAvailabilityGateTask` (pipeline #187 P1 fix).
2. **Fail-open to disclosure.** If the consequence machinery itself errors, the
   session proceeds as today (override fully honored) and the error is disclosed —
   a consequence bug must never dark the run it governs.

## 3. Mechanics

### 3.1 Failed-regime extraction (stamp at promotion; owner: promotion tooling)

At override-promotion time the promotion path (wf_promote / stamping script — the
same tooling that already writes `manual_override`) derives and stamps:

```json
"override_consequences": {
  "schema": "override_consequences.v1",
  "manual_override": true,
  "degraded_regimes": ["BULL_CALM"],
  "failed_checks": {
    "BULL_CALM": ["sanity_regime_ic", "trade_monotonicity"]
  },
  "source": "wf_gate_metadata",
  "stamped_at": "2026-07-06T..."
}
```

- `degraded_regimes` = every regime label (taxonomy: `BULL_CALM`, `BULL_VOLATILE`,
  `CHOPPY`, `BEAR` — `renquant_common.hmm_regime_labels`) with ≥1 per-regime gate
  FAIL (`sanity_regime_ic`, per-regime `trade_monotonicity`; extensible as the
  gate grows per-regime checks).
- Regime-blind failures (e.g. global `wf_reason` FAIL with no per-regime
  breakdown) do NOT populate `degraded_regimes` — this amendment scopes
  consequences to regimes the gate specifically named; a fully-regime-blind FAIL
  is the 06-30 policy's existing territory (override + loud provenance).
- A gate-PASSING promotion stamps `degraded_regimes: []` — the block's presence
  is what lets consumers distinguish "no failures" from "pre-amendment artifact".
- Derivation is mechanical (read fields, no judgment); the stamp is immutable
  once written, same as the rest of `wf_gate_metadata`.

### 3.2 Where regime is known at decision time

`RegimeJob` stamps `ctx.regime` EARLY in `InferencePipeline` — before universe
admission, panel scoring, buy gates, and sizing. Every consequence below keys off
`ctx.regime` at its existing choke point; no new regime inference is introduced.
Precedent: `governor_sizing.e_ceil_by_regime` already applies per-regime policy
config at decision time.

### 3.3 The consequence options (the operator picks the terminal level)

| | Option | Behavior in a degraded regime | Behavioral risk | Complexity |
|---|---|---|---|---|
| **C** | **Hard disclosure** | Run bundle + ntfy carry `OVERRIDE-DEGRADED` markers; decisions unchanged | none | low |
| **B** | **Reduced buy budget** | Buy-side budget scaled by `budget_factor` (default 0.5) via the deployment governor's existing per-regime ceiling path | medium | low-medium |
| **A** | **Shadow-demote** | The override-promoted model does not serve buys; fallback serves them | high | high |

**Option C — hard disclosure (always on, the floor).**
- Session predicate: `ctx.regime ∈ degraded_regimes` of the serving artifact.
- Run bundle stamps a top-level block:
  ```json
  "override_degraded": {
    "schema": "override_degraded.v1",
    "active": true,
    "session_regime": "BULL_CALM",
    "degraded_regimes": ["BULL_CALM"],
    "failed_checks": {"BULL_CALM": ["sanity_regime_ic", "trade_monotonicity"]},
    "consequence_applied": "disclose",
    "model_artifact": "<artifact_path>",
    "promoted_at": "2026-07-06"
  }
  ```
- ntfy: the daily decision notification title gains an `OVERRIDE-DEGRADED` marker
  (same title-marker mechanic as the universe-collapse `UNIVERSE-OUTAGE` marker,
  umbrella #463 pattern); the orchestrator outage/session monitor (the
  `funnel_integrity.v1` consumer) renders the block whenever present.
- Disclosure is NOT a selectable level — it is the floor under B and A too:
  whatever consequence is configured, the block + marker are always emitted.

**Option B — reduced buy budget.**
- In a degraded regime, the buy-side deployment budget is multiplied by
  `budget_factor` (default **0.5**, range (0,1]) INSIDE the existing governor
  sizing step — i.e. effectively `e_ceil_by_regime[regime] × budget_factor` for
  the session. One multiplication at one existing choke point; no new gate.
- Exits, rotations of existing holdings, and sell-side logic unchanged.
- Rationale for a haircut rather than zero: the gate evidence is a FAILED
  validation, not a proven inversion (PR #476 is explicit that H2/H3 remain
  unvalidated hypotheses) — halving exposure bounds the damage of serving an
  unvalidated scorer in its worst regime while preserving the freshness
  directive's intent.

**Option A — shadow-demote.**
- In a degraded regime the override-promoted model is demoted to shadow for the
  session (scores logged, not acted on). Buys are served by, in configured order:
  - `previous_validated`: the most recent artifact whose gate PASSED in the
    session regime and is within the staleness ceiling; else
  - `panel_neutral`: no model-ranked buys this session (admission and exits run;
    the buy scan yields no candidates — equivalent to a disclosed, regime-scoped
    buy pause).
- Honest complexity accounting (why A is NOT the recommended first landing):
  previous-model availability is not guaranteed (the 07-06 override happened
  BECAUSE no fresh gate-passing model existed); dual-artifact serving re-opens
  the calibrator/scorer fingerprint parity class (the triple-impl bug — any A
  implementation MUST reuse the single shared fingerprint impl, never a fourth
  copy); rollback identity must be pinned per §5.4 of the parent RFC. A needs
  its own design PR with a point-in-time availability audit before it can be
  scheduled.

### 3.4 Config schema (owner: renquant-strategy-104)

```json
"freshness_override_consequences": {
  "schema": "freshness_override_consequences.v1",
  "enabled": true,
  "consequence": "disclose",        // "disclose" | "budget" | "demote"
  "budget_factor": 0.5,             // used when consequence="budget"
  "demote_fallback": ["previous_validated", "panel_neutral"]  // when "demote"
}
```

- `enabled=false` or absent section → exactly today's behavior (safe default;
  rollout is opt-in per the pinned strategy config, so nothing changes at pin-
  bump time without an explicit config PR).
- Malformed values fall back to `"disclose"` — a config typo can never escalate
  to a behavioral consequence, and can never silence disclosure.

### 3.5 Ownership map (per the multi-repo boundary)

| Repo | Owns |
|---|---|
| renquant-model / promotion tooling | §3.1 stamp derivation at promotion |
| renquant-pipeline | decision-time predicate (`ctx.regime` vs stamp), Option B budget multiply in governor sizing, Option A serving switch, `override_degraded` ctx block |
| renquant-strategy-104 | §3.4 config section |
| renquant-orchestrator | run-bundle persistence + ntfy rendering (`OVERRIDE-DEGRADED` marker) via the session/outage monitor; monitoring of consequence activations |

## 4. Staged rollout (shadow-first, reversible)

| Stage | Lands | Gate to advance |
|---|---|---|
| 0 | Stamp only (§3.1) — promotion tooling writes `override_consequences`; no consumer | stamp visible on next override; consistency check in CI |
| 1 | Option C disclosure (observe-only): pipeline ctx block + orchestrator bundle/ntfy rendering | ≥1 override soak; operator confirms marker fidelity (no false OVERRIDE-DEGRADED on gate-passing models) |
| 2 | Option B, shadow-first: governor logs the would-be budget haircut for ≥5 degraded-regime sessions without applying it; then live with `budget_factor=0.5` | operator sign-off on shadow log; pre-registered rollback trigger: revert to `disclose` if degraded-regime sessions show the haircut binding against subsequently-validated winners |
| 3 | Option A — separate design PR (availability audit + fingerprint-parity plan required) | operator decision; not scheduled by this document |

Each stage is independently revertible by config (`consequence` downgrade or
`enabled=false`); no stage touches exits at any point.

## 5. Non-goals

- Does not weaken or relitigate the 2026-06-30 override authority itself.
- No per-regime model ensembling / mixture-of-experts (scorer-lineup decision
  stands; PR #476 §7 already routes MoE behind a preregistered experiment).
- No change to the WF gate's checks; this consumes its per-regime output.
- No sell/exit-path change of any kind.

## 6. Open questions for the operator (decide at merge)

1. Terminal consequence level: is Stage 2 (budget haircut) the intended resting
   state, or is Stage 3 (demote) the goal once its design lands?
2. `budget_factor` default 0.5 — acceptable, or prefer a deeper cut (e.g. 0.25)
   in a regime with an INVERTED monotonicity spread specifically?
3. Should a degraded-regime session ALSO tighten the buy-admission bar (e.g.
   require gate-passing per-ticker tournament models only), or is sizing the
   only behavioral lever for v1? (This document proposes: sizing only — one
   lever, auditable.)
