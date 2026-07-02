# Design review: 104/105 RFC amendments — label-horizon freshness key, intraday regulatory envelope, governance convergence

STATUS: design / RFC for review (docs only — no code, config, broker, risk-cap, or sizing change).
DATE: 2026-07-01
REVISION: r2 (2026-07-02) — addresses the Codex review (CHANGES_REQUESTED). (1) **A2 rewritten on a
verified premise**: the legacy PDT framing is superseded — FINRA's Intraday Margin Standards
(effective 2026-06-04) replaced the four-trades/$25k PDT designation, and a read-only query of the
actual live Alpaca account confirms the new regime; the unsafe "day-trade budget = 0 blocks
same-session exits" control is **withdrawn** and replaced by intraday-margin / buying-power
semantics with an explicit **exits-always-allowed** safety precedence. (2) **A7 corrected**: the
proposed active-day carve-out was post-hoc, outcome-dependent relaxation of a pre-registered
criterion — withdrawn; the original criterion stands, and the BEAR risk-switch becomes a **new
hypothesis in a separate frozen prereg**. (3) **A1 re-scoped**: the shipped #213 monitor is already
horizon-aware (`label_observation_cutoff` freshness key + expected-lag threshold widening +
`max_feature_anchor_date` as provenance-only, per umbrella #423 round-3); the amendment is to align
the merged **RFC text** with that implementation and require per-recipe axis semantics — not to
imply no implementation exists. r3 (2026-07-02) — addresses Codex's r2 review: (1) the **progress
record** rewritten to the current conclusions in the control schema (literal `STATUS:` / `WHAT:` /
`WHY/DIR:` / `EVIDENCE:` / `NEXT:` fields) so the durable record no longer preserves the withdrawn
r1 claims; amendment-order item 7 renamed to the separate frozen BEAR-risk-switch preregistration.
(2) **A5.4/A5.5 reworded as sensitivity SCENARIOS** with explicit formula + assumptions (never
settled probabilities), plus a §9.4 power-prereg requirements list (pilot paired-residual
variance/correlation, cluster unit, target effect, α/power, attrition, blinded sample-size
re-estimation) and the explicit rule that an underpowered design routes expansion through §9.3a as
**recorded risk acceptance, never evidence**. Response maps in the appendix.
SCOPE: an independent deep review of the four merged design documents —
**#208** (`2026-06-30-renquant105-intraday-decisioning-architecture.md`, r12),
**#210** (`2026-06-30-model-freshness-governance.md`, R6),
**#212** (`2026-06-30-shadow-scorer-freshness.md`, r2), and the 105 direction decision
(`2026-06-28-renquant105-direction-decision.md`) — plus the umbrella `doc/arch/strategy-104.md`.
This PR proposes **amendments**; it does not re-litigate the settled convergences (the #208 r11
statistics split-out and the #210 §7 narrowing both stand). Per the freeze-PRs-under-review rule,
amendments to merged designs arrive as this new PR, not as pushes to the merged branches.

Verdict summary (severity-ordered):

| # | Finding | Docs hit | Class |
|---|---------|----------|-------|
| A1 | The merged RFC **text** defines the fast-axis ceiling (21–45d grid; 35d shadow tier) in raw-age terms that are structurally unsatisfiable for `fwd_60d`-label models; the shipped #213 monitor is **already horizon-aware** — the amendment aligns the RFC text with the implementation and requires per-recipe axis semantics | #210, #212 | **text/impl divergence** |
| A2 | The Stage-1 intraday design carries **no broker-regulatory / settlement envelope**. Verified (read-only account query, 2026-07-02): a margin account governed by FINRA's Intraday Margin Standards (effective 2026-06-04; PDT designation deprecated) — the envelope must bind on real-time intraday margin / buying-power semantics with **exits-always-allowed** precedence, not legacy PDT counting | #208 | **blocking gap** |
| A3 | #210's Final phase has an **experiment-only authorization path** that will, with high probability, never complete — inconsistent with the two-path authorization #208 §9.3a already adopted; Fix-3 (placebo floor) is mis-classified as bypassable infra | #210 | governance |
| A4 | Stage 1–2 framing ("catch the entry as it forms") does not match the frozen-signal mechanics; Stage-2's estimand is not reconciled with the already-measured phase −1 intraday-alpha NO-GO | #208 | framing / estimand |
| A5 | Engineering pins needed before pilot data is trustworthy: gate-input census, order-type pre-declaration, SIP-vs-IEX quote quality, loss-budget noise **sensitivity scenario**, §9.4 **power-prereg requirements** (pilot variance, cluster unit, blinded re-estimation; underpowered ⇒ operator path = explicit risk acceptance), batch-rotation churn diagnostic, active-path verification | #208 | measurement integrity |
| A6 | `strategy-104.md`'s hand-written production snapshot is stale (pre-dates the 06-23 XGB re-promotion) — the same premise rot that invalidated #210 R1 | umbrella | doc integrity |
| A7 | The direction-decision's regeneration PR is the evidence base for the whole 105 direction, not merely Track A's first step; the known BEAR-only skill slice makes GO criterion (d) near-certain to fail — the criterion **stands as registered**, and the BEAR risk-switch becomes a **new hypothesis in a separate frozen prereg** (never a retroactive carve-out) | direction decision | evidence / prereg |

---

## A1. Label-horizon contradiction: align the RFC text with the (already horizon-aware) implementation (amends #210 §2/§3/§5.1 and #212 §3.2 text)

**The contradiction.** #210 §2 correctly keys freshness on the **data cutoff, never `trained_date`**,
and its fast axis includes the "retrain-data cutoff". The §5.1 pre-registered grid for the fast-axis
ceiling is {21, 28, 35, 45} days; #212's shadow breach tier is 35d on the same axis. But the panel
models train on `fwd_60d_excess`: **the newest labelable training row is always ≥ 60 trading days
(~88 calendar days) behind today** — a structural floor set by the label horizon, not by any
pipeline defect. #212's own evidence shows it: the shadow PatchTST trained 2026-05-22 has
`effective_selection_cutoff_date = 2026-02-10` (~101 calendar days behind at train time). A perfect
point-in-time panel refresh followed by a same-day retrain still yields a cutoff ~88+ days old.

Consequences as written:

- **Every value in the §5.1 grid — including 45d — is unsatisfiable** if "retrain-data cutoff" means
  the last date of labeled training data. The §5 replay would simulate a family of policies that
  breach at every epoch by construction.
- **#212's monitor would report `breach` forever, even after a perfect remediation**: a fresh retrain
  on a fully refreshed panel lands at ~88d, far past the 35d tier. The remediation the RFC specifies
  cannot ever return the monitor to `healthy` as the tiers are defined.
- This is the **same failure family as the fund-freshness serving-axis clip bug** (base-data #26 /
  pipeline #151): a label-truncated axis was treated as a freshness axis, producing a structurally
  unsatisfiable gate (P-FUND-FRESHNESS 45d vs an ~88d-clipped feed) and a long silent no-buy state.
  #210/#212 as written rebuild that bug on paper.

**Implementation status (r2 correction — the divergence is in the TEXT, not the code).** The shipped
#213 monitor (`src/renquant_orchestrator/model_freshness_monitor.py`, per umbrella #423 round-3)
already implements the correct semantics: freshness keys on **`label_observation_cutoff`** (the
fwd_60d-clipped max fully-labeled training row — the latest information that actually affected
fitting), the tiering thresholds are **widened by the expected label-horizon lag** (so a genuinely
fresh retrain reads HEALTHY, not born-BREACH), and **`max_feature_anchor_date`** (the raw feature
frontier, ~60 business days ahead by construction) is captured as **data-pipeline-health provenance
only, never a freshness axis** — keying on it would let fresh unlabeled rows make a frozen model
read fresh. So the operational hole is closed. What remains open is that the merged **RFC text** of
#210/#212 still specifies the raw-age semantics the implementation had to reject: a reader
implementing from the RFCs (or pre-registering the §5.1 grid from them) would rebuild the
contradiction. The amendment below is therefore a **text-alignment + generalization** amendment.

**Proposed amendment — two distinct freshness quantities in the RFC text, never one number:**

1. **Serving-feature-axis freshness** — the end date of the feature panel the model *scores* at
   inference. This axis has no label dependence and can and should be current (T-1). The operator's
   28d directive is meaningful here, and a 21–45d grid is feasible here.
2. **Training-label lag budget** — the training cutoff judged against the **achievable frontier**,
   not against today: `today − effective_selection_cutoff ≤ label_horizon + ingest_slack + X`.
   The monitored quantity is `X` (distance from the frontier), with a structural floor stated
   explicitly per model family (fwd_60d ⇒ frontier ≈ today − ~88 calendar days). A model is
   training-stale when it lags **what was trainable**, not when it lags today.

Concretely: rewrite #210 §2's fast-axis definition to name both quantities (adopting #213's
`label_observation_cutoff` / `max_feature_anchor_date` vocabulary); restate the §5.1 grid as a grid
over frontier-distance `X` (plus the serving-axis ceiling as its own dimension); restate the
Pillar-1 tier table and #212 §3.2's tier table in frontier-distance terms. Additionally require
**per-recipe axis semantics**: each model family declares its label horizon in its recipe so the
expected-lag widening is derived per recipe (fwd_60d panel ≠ per-ticker tournament ≠ any future
short-horizon model), not hardcoded to one constant. `trained_date` re-enters only as the
conjunction the operator's directive actually wants: **trained recently AND on data at the
achievable frontier** — either alone is gameable (a fresh retrain on a stale panel, which #212 r2
already blocks; or an old artifact whose cutoff was once at-frontier).

**#212 corollary.** §3.1/§4-step-1 say "refresh the panel to the current point-in-time" — for a
labeled training panel this is impossible; the correct target is the frontier. Additionally the RFC
delegates the panel refresh ("base-data / model-owned work") in one line without diagnosing **why**
`transformer_v4_wl200_clean.parquet` stopped at 2026-02-10 — whether the builder simply never re-ran,
or a label-join `dropna` clips the axis (the #26 family). The amendment asks for that diagnosis to be
a named deliverable of #212 Phase 3, because the remediation differs (schedule the builder vs fix the
join) and the failure family has already bitten once.

---

## A2. Broker-regulatory / settlement envelope for intraday decisioning (blocking; amends #208 §7/§10/§11/§11b) — r2 REWRITE on a verified premise

**r1 of this review framed A2 as legacy PDT counting; that premise is superseded and the r1
"day-trade budget = 0 blocks same-session exits" control was unsafe. Both are withdrawn.** What
stands is the underlying gap: #208 designs an intraday order loop with **no broker-regulatory /
settlement envelope at all** — and the envelope must be designed against the rules that actually
govern the account **today**, verified, not remembered.

**Verified account regime (read-only `GET /v2/account`, 2026-07-02):** the live Alpaca account is a
**margin account**, `status=ACTIVE`, `pattern_day_trader=false` with `daytrade_count=0` (fields
retained but **deprecated** per Alpaca's account docs), `daytrading_buying_power ≈ $37.5k` on
~$10.8k equity (≈3.5× — impossible under the legacy sub-$25k PDT regime, confirming the account is
governed by the new rules), with live `initial_margin` / `maintenance_margin` /
`intraday_adjustments` fields. FINRA's **Intraday Margin Standards** (effective **2026-06-04**)
replaced the four-trades-in-five-days PDT designation and the $25k minimum with risk-based intraday
margin (refs: Alpaca account-plans + intraday-margin-rule docs; FINRA weekly archive 2026-01-07).
Note the pinned strategy config already sizes against `non_marginable_buying_power` (~$8.3k)
via `execution.buying_power_mode` — the intraday envelope must stay consistent with that choice.

**Proposed amendments:**

1. **§11 Stage-1 BLOCKER (new): verified broker-rule regime, recorded per session.** Before the
   first canary session, query and **record in the run bundle** the account's broker-effective rule
   regime and the fields that bind (margin vs cash; which buying-power figure governs; the
   intraday-margin fields the broker enforces). The envelope is designed against **those recorded
   fields**, and a session aborts (no entries) if the recorded regime differs from the one the
   envelope was designed for — rule regimes change (2026-06-04 proved it), so the contract is
   *verify-then-bind*, never *hardcode*.
2. **§10 envelope (new rows): real-time intraday margin / buying-power headroom.** Entries bind on
   the broker's **live margin/buying-power semantics**: a new buy child must fit within a
   pre-declared fraction of `non_marginable_buying_power` (consistent with the existing
   `buying_power_mode`), an open/pending buy consumes headroom (consistent with §7
   `reserved_cash`), and any broker-reported **intraday margin deficit / adjustment** is a Tier-1
   condition (halt new entries, reconcile). No legacy day-trade counting.
3. **Exits-always-allowed safety precedence (§10 interaction rule, new).** **No envelope,
   regulatory, or budget constraint may ever block a protective exit.** Constraints bind
   **entries only**: if a contemplated entry would create a position whose protective exit could
   later be constrained (by margin, settlement, or halt rules), the **entry** is refused — the exit
   side is unconditional. This inverts r1's unsafe proposal: same-session round trips are
   permitted whenever the risk rules demand them; their cost/churn is a **ledger diagnostic**
   (count + realized cost of same-session round trips), not a hard counter.
4. **§7 settlement accounting (conditional).** The verified account is margin, so T+1
   settled-funds gating does not bind today; the contract still states the cash-account variant
   (same-day sale proceeds excluded from `available` until settled) so a future account-regime
   change is a recorded config flip, not a redesign.

---

## A3. Governance convergence for #210: two-path authorization; Fix-3 fail-closed (amends #210 §4.3.1/§5/§6-Final)

**A3.1 The Final phase is hostage to an experiment that will likely never run.** #210's §5 machinery
(R3 selection/confirmation split → R4 feasibility audit → R5 availability timestamps → R6 common
decision calendar) is methodologically correct — and its own §5.0 audit will, with high probability,
fail closed on the historical registry (immutable `artifact_created_at` / gate `observed_at` were not
recorded at creation), routing to §5.6 prospective logging, which under 60d-label overlap needs
**years** to accrue the §5.0-iii floor. Meanwhile the Final phase ("flip `model_staleness_days`
60 → 28 only after §5 authorizes") keeps the operator's recorded 2026-06-30 freshness directive
deferred indefinitely.

#208 already solved this shape of problem: §9.3a authorizes expansion via **either** the deferred
experiment **or** an explicit, separately-recorded operator risk acceptance. #210 should adopt the
same two-path structure, with the roles honestly divided:

- The **ceiling** (28d serving-axis / frontier-distance per A1) is a **risk-policy constant** — the
  same epistemic class as "no entries in the last 30 minutes": set by judgment, guarded by the
  observe-only monitor, reversible. It may be adopted by a recorded operator decision without §5.
- The **best-of-recent fallback (Pillar 3)** — software auto-promoting a gate-failed artifact —
  keeps the full §5 treatment (or its §5.6 prospective-logging successor). That is where the causal
  claim ("a fresh rejected model is safer than a stale validated one") actually lives.

Proposed amendment: rewrite the §6 Final row as two-path (§5 authorization **or** recorded operator
decision, monitor-guarded, with a pre-registered rollback trigger); leave Pillar 3 experiment-gated
and DEFERRED exactly as it stands.

**A3.2 Fix-3 (structural placebo floor) must be fail-closed until the difference test ships.**
§4.3.1 enumerates the placebo floor as bypassable infra "*only while it remains an embargo artifact,
not a real leakage signal*" — but distinguishing the structural floor from real leakage **is exactly
what the not-yet-implemented Fix-3 difference test** (`real_ic − placebo_ic > margin`) does. Until
that test exists, an unattended fallback has no operational predicate to apply the parenthetical
with; a genuinely leaky candidate fails the placebo ceiling the same way. Amendment: move placebo
failures to the **quality / fail-closed** class until the difference test is implemented and
validated; only then does the *structural-floor* sub-case re-enter the infra list, with the
difference test as its predicate.

**A3.3 Name the expected terminal state up front.** Given the chronic-June evidence (structural
placebo floor + sub-SPY substance across candidates), the likely outcome of repairing Fixes 1–3 is
that the gate finally speaks and says the live 05-18 primary — and its recent siblings — have **no
demonstrated edge** (Fix-4). Best-of-recent among substance-failing candidates is still
substance-failing. Every path in this governance framework then terminates at a **recorded operator
decision** (trade by directive, or stop). §8 Q5 treats this as an open edge case; it is the
document's expected end state and belongs in §1, so the operator reads the framework knowing the
decision it is converging toward.

---

## A4. #208 framing and the Stage-2 estimand (amends #208 §1/§12)

**A4.1 Stage 1–2 does not "catch the entry as it forms."** With class A frozen at T-1 close, the
batch counterfactual filling at **session-T open** (§9.2), and no new model information intraday, the
intraday path's fill is always **later than** the baseline within the same session and contains no
information the T-open fill lacked. Nothing is caught earlier; the fill is **repositioned within the
session**. That repositioning is a defensible economic thesis on the existing evidence — momentum /
conviction returns accrue overwhelmingly overnight while intraday drift is ~0, and the next-day open
auction is a systematically expensive print — so delaying from the open into the session plausibly
cuts entry cost while sacrificing ~nothing in expectation. The RFC should say exactly that.
"Catch the trend as it forms" is true only of Stage 3 (intraday re-scoring). Amendment: rewrite the
§1 target framing for Stages 1–2 as **execution-timing repositioning of the fill on a frozen
signal**, reserving trend-catching language for Stage 3.

**A4.2 Stage 2 must be reconciled with the phase −1 NO-GO.** §12 calls Stage 2 the place "where the
alpha question is first legitimately asked." That question was already asked and answered: the
phase −1 measurement (PR #199) found intraday open→close **directional alpha** clears no realistic
cost bar at this account scale (net-edge negative at IC 0.03–0.05; soft NO-GO; pivot to
execution-timing residual). Without citing it, Stage 2 invites re-litigating a settled NULL.
Amendment: Stage 2's estimand is pinned as the **conditional timing residual** — *given an entry the
frozen signal has already decided, does the intraday trigger obtain a better fill than the open?* —
explicitly **not** the directional intraday-alpha estimand phase −1 closed.

---

## A5. Measurement-integrity pins for Stage-1 pilot data (amends #208 §6/§9/§10/§8)

The r11 convergence made Stage-1's deliverable *a clean corpus of paired execution data*. These pins
are what "clean" requires; each is cheap now and expensive to retrofit:

1. **Gate-input census (closed world for the §6 replay).** The four-class no-leak proof can only
   check inputs someone classified. The gate-stack has non-obvious temporal inputs: the regime
   detector (daily-bar state — class A or B?), the earnings-blackout calendar, wash-sale
   `last_sell_dates` (which an intraday *sell* mutates mid-session — the STATE-EXT-SELL bug's home).
   Amendment: §8's pipeline slice delivers a **census artifact** mapping every gate's every input to
   a class; the replay test asserts against the census, and an input absent from the census is a
   test failure. Without this, the hard-fail on partial-bar-into-A/B has no enforcement surface.
2. **Pre-declare the order type.** Entry order type (market vs marketable-limit at NBBO±x bps)
   dominates IS more than any envelope parameter; left free, the pilot corpus is a mixture across
   order types and the deferred experiment inherits heterogeneous data. One sentence in §10 fixes it.
3. **Quote-feed quality is a named blocker, not an entitlement checkbox.** On Alpaca's free IEX-only
   feed, "NBBO" is IEX-local (single-venue, ~2–3% of volume) — arrival mids are systematically wider
   / staler than SIP, and the primary-listing **opening auction print** required by §9.2c is not in
   the IEX feed at all. Amendment: §11's data-plane blocker becomes "SIP/consolidated feed
   subscription, **or** a recorded acceptance of quantified IEX bias for both the arrival quote and
   the synthetic batch reference."
4. **Loss-budget noise sensitivity — a SCENARIO with stated assumptions, not a settled
   probability (r3 rewording).** 1.5% of equity ≈ **$157**. Illustrative scenario: one or two
   names at the §10 deployment cap (~$1.5k notional), i.i.d. daily returns at σ_daily ≈ 2%, no
   beta adjustment, 20 sessions → cumulative one-sigma ≈ σ_daily × notional × √20 ≈ **$134** —
   the same order as the budget, so a noise-driven halt is a **material** outcome under these
   assumptions. The actual probability depends on cross-name/day clustering, market beta, and the
   entry-trigger's conditioning, and is **not** computable before pilot data; the design point
   survives every scenario: §9.3a should state that the loss budget is reachable by market noise
   alone at this scale, and **pre-commit the response** (halt → re-authorizing a fresh window is
   itself a recorded §9.3a decision), so a noise-halt is never misread as an economic verdict on
   the timing policy.
5. **Identifiability — pre-register the power machinery; name the honest fallback (r3
   rewording).** Illustrative **upper-bound scenario**, formula and assumptions stated: with
   independent pairs and the paired-difference σ bounded above by the measured σ(open→close) ≈
   150bps, detecting a 10bps effect at two-sided α=0.05 / 80% power needs
   N ≈ ((1.96+0.84)·150/10)² ≈ **1,800 pairs** — years at 1–2 names/day. This is a **scenario,
   not a conclusion**: pairing, covariate adjustment, and trigger conditioning can cut the
   residual σ substantially (that is what matched pairs are for), while cross-name/day
   clustering and repeated names cut the **effective** N — the true requirement is unknowable
   before pilot data, which is exactly why §9.4 defers it. The amendment is therefore a
   **requirements list for §9.4's future prereg**, stated now: it must include (i) a pilot
   variance/correlation estimate of the **actual paired timing residual** (not σ_oc), (ii) the
   **cluster unit** (session / name / name×session), (iii) the target effect, (iv) α/power,
   (v) an attrition/censoring allowance, and (vi) a **blinded sample-size re-estimation rule**.
   And the honest fallback, stated now: **if the re-estimated design remains underpowered at this
   account scale, the §9.3a operator path is explicitly RISK ACCEPTANCE — a recorded decision to
   proceed without evidence of economic benefit — never re-labeled as evidence.**
6. **Track the batch-rotation churn channel.** A name entered intraday on the T-1 signal faces the
   same evening's batch re-rank; the QP or the σ-blind panel-exit can rotate it out at T+1, and
   anti-churn then locks re-entry for 5 days — a systematic whipsaw-cost channel unique to the
   intraday path. Amendment: add to the §9 diagnostics *"fraction of intraday entries exited by
   batch rotation within N sessions"*.
7. **Verify the active live path consumes the pinned subrepo code.** The fractional-shares episode
   (closed 2026-06-30) shipped subrepo capability while the live path ran umbrella-local adapter
   code — deployed-but-dark. §8 asserts the three-repo decomposition but never verifies that
   `com.renquant.intraday`'s runner actually routes through the pinned execution/pipeline code on
   the touched path. Amendment: acceptance test #0 of the §8 orchestrator slice is an **active-path
   audit** (prove the live intraday loop imports the pinned modules being changed), before any
   default-OFF flag is even added.

---

## A6. Documentation integrity: machine-generate the 104 production snapshot (umbrella follow-up)

Umbrella `doc/arch/strategy-104.md` still states "HF PatchTST primary since 2026-06-05"; the operator
re-promoted XGB on 2026-06-23 (#210 §0). #210's R1 was materially wrong **because** it trusted this
class of hand-written snapshot, and one full review round was spent correcting the premise. A
hand-maintained "production snapshot" section cannot stay truthful at this change frequency.

Proposal (umbrella-repo follow-up PR, referenced here for the record): the snapshot section of
`strategy-104.md` becomes **generated** — a small script renders `panel_scoring.kind`, active/shadow
artifact ids, `trained_date` / data cutoffs, and promote provenance from the pinned subrepo config +
artifact metadata into the doc (or a sibling `strategy-104-snapshot.md`), refreshed by the existing
weekly jobs; hand-written prose keeps the stable architecture only. A CI check that the rendered
snapshot is not stale (> N days older than the pinned config's last change) closes the loop.

Secondary convention note: #208 carries a ~1,000-word revision paragraph and #210 six stacked
response-map sections before the design begins. For "single durable record" docs, current design
belongs up front; review history belongs in an appendix or the PR thread. Proposed convention going
forward: response maps live in an appendix section; the STATUS header states the current revision in
≤3 lines.

---

## A7. Direction-decision follow-ups (amends the Track-A prereg's standing)

1. **Elevate the regeneration PR.** The A1 audit (genuine IC CI spanning 0; BULL_CALM ≈ −0.003) is
   `/tmp` scratch — yet it is the load-bearing premise for the two-track decision **and** for #208's
   engineering-not-alpha framing. The durable OOS pick table
   (`scripts/regen_oos_pick_table.py` → `data/exp/oos_pick_table_recipe_v2.parquet`) is therefore not
   merely Track A's first step; it is the evidence base of the 105 direction itself, and should be
   prioritized as such. If the durable regeneration materially changes A1, the direction is
   re-opened — that is what falsifiable means.
2. **GO criterion (d) is near-certain to fail as written — and it must stand anyway (r2
   correction).** The only skill slice A1 found is BEAR (~10% of live time); any regime-keyed
   conditioning therefore cannot reach (d)'s ≥25% active-day floor. r1 of this review proposed a
   carve-out for low-frequency risk-switch filters; that proposal is **withdrawn as post-hoc,
   outcome-dependent relaxation** — loosening a pre-registered criterion after inspecting the
   evidence that makes it fail is exactly what pre-registration exists to forbid. The amendment is
   instead: (a) the Track-A verdict is rendered under the **original (a)–(e), untouched** — if no
   conditioner clears them, Track A is NULL and is recorded as such; (b) the **BEAR risk-switch is
   registered as a NEW hypothesis in a separate, frozen pre-registration** with its own estimand
   (contribution during the active slice), its own capital-weighted utility threshold, and its own
   untouched confirmation span — it competes on fresh terms and can never retroactively amend the
   current GO rule; (c) the predictable-failure observation stays, as a *statement of expected
   outcome* (so nobody is surprised by the NULL), not as grounds to move the bar.

---

## Proposed amendment order

| Order | Amendment | Doc(s) | Why first |
|---|---|---|---|
| 1 | A1 RFC-text alignment with the #213 implemented key (label-observation frontier + per-recipe axis semantics) | #210 §2/§3/§5.1, #212 §3.2 | the §5.1 grid and any future pre-registration read the RFC text; align it before anything is registered from it |
| 2 | A2 regulatory envelope (verified-regime blocker, intraday-margin/buying-power headroom, exits-always-allowed precedence) | #208 §7/§10/§11 | hard blocker for any live canary session |
| 3 | A5.1–A5.3 measurement pins (census, order type, quote feed) | #208 §6/§8/§10/§11 | must precede pilot data collection or the corpus is retroactively dirty |
| 4 | A3 governance convergence (two-path Final; Fix-3 fail-closed) | #210 §4/§6 | unblocks the operator's directive without reviving the stats loop |
| 5 | A4 framing/estimand + A5.4–A5.7 | #208 §1/§9/§12 | honesty and diagnostics; no ordering pressure |
| 6 | A6 snapshot generation | umbrella | separate repo, separate PR |
| 7 | A7 regeneration PR + the separate frozen BEAR-risk-switch preregistration | direction decision | evidence base for everything above |

## Open questions for the operator / Codex

1. **A1:** confirm the RFC-text alignment to #213's implemented key (`label_observation_cutoff`
   frontier + expected-lag widening; `max_feature_anchor_date` provenance-only) — and what frontier
   slack `X` to pre-register **per model family** (per-recipe label horizon).
2. **A2:** confirm the verify-then-bind contract (recorded broker-rule regime per session), the
   intraday-margin/buying-power headroom rows, and the **exits-always-allowed** precedence rule as
   the Stage-1 envelope amendment.
3. **A3:** adopt the #208-style two-path authorization for #210's Final (ceiling as risk-policy
   constant by recorded decision), keeping Pillar 3 experiment-gated?
4. **A5.3:** subscribe to the consolidated/SIP feed for the pilot, or record accepted IEX bias?
5. **A5.5:** confirm the §9.4 power-prereg requirements list (pilot paired-residual
   variance/correlation, cluster unit, target effect, α/power, attrition allowance, blinded
   sample-size re-estimation) — and the explicit labeling rule that an underpowered design routes
   any expansion through §9.3a as **recorded risk acceptance**, never as evidence.
6. **A7:** should the separate frozen BEAR-risk-switch pre-registration be authored now (in
   parallel) or only after the Track-A verdict is rendered under the original criteria?

---

## Appendix — response map: Codex review r1 (CHANGES_REQUESTED, 2026-07-02)

| # | Codex point | Disposition | Where |
|---|---|---|---|
| 1 | **A2 rests on a superseded broker/regulatory premise** (FINRA Intraday Margin Standards effective 2026-06-04 replaced PDT designation/$25k; Alpaca deprecated PDT fields) **and the day-trade-budget-0 control is unsafe** (must never block a required protective exit). Design against the actual account's current regime/fields, intraday margin deficit / buying-power semantics, T+1 cash settlement where applicable, exits-always-allowed precedence | **Accepted** — A2 rewritten: verified the live account read-only (margin, new-regime fields, `daytrading_buying_power` ≈ 3.5× equity), verify-then-bind blocker (regime recorded per session), envelope binds entries on live margin/buying-power headroom consistent with `non_marginable_buying_power`, **exits unconditionally allowed** (constraints bind entries only; same-session round trips become a ledger diagnostic), cash-settlement variant stated conditionally. r1 control withdrawn | A2 |
| 2 | **A7's carve-out is post-hoc, outcome-dependent relaxation of a pre-registered criterion.** Keep the original (a)–(e); a BEAR risk-switch is a new hypothesis needing its own frozen prereg (estimand, threshold, capital-weighted utility, untouched confirmation span) | **Accepted** — carve-out withdrawn; Track-A verdict renders under the original criteria; BEAR risk-switch re-scoped as a separate frozen pre-registration; the predictable-failure note retained only as expected-outcome statement | A7.2 |
| 3 | **A1 must acknowledge the existing implementation** — #213 already has horizon-aware `label_observation_cutoff` compensation and `max_feature_anchor_date` provenance; the amendment is text alignment + per-recipe axis semantics, not a claim that nothing exists | **Accepted** — verified in `model_freshness_monitor.py` (umbrella #423 round-3 semantics: label-observation key, expected-lag threshold widening, feature-anchor provenance-only); A1 re-scoped to RFC-text alignment + per-recipe label-horizon declaration | A1 |
| 4 | Required CI must be green before merge | **Acknowledged** — docs-only PR; CI status checked on this revision | — |

## Appendix — response map: Codex review r2 (CHANGES_REQUESTED, 2026-07-02)

Codex r2 **accepted** the r2 design fixes (superseded-PDT premise corrected; exits-always-allowed
restored; Track-A prereg preserved; #213 horizon-aware monitor acknowledged) and raised two
remaining blockers.

| # | Codex point | Disposition | Where |
|---|---|---|---|
| 1 | **The committed progress record contradicts the revised design and does not satisfy the control schema** — its "Key findings" still carried the withdrawn r1 claims (A1 as unimplemented blocking split; A2 as legacy PDT / day-trade-budget-0; A7 carve-out); the amendment-order table still said "prereg carve-out"; the literal `STATUS:` / `WHAT:` / `WHY/DIR:` / `EVIDENCE:` / `NEXT:` fields were missing | **Accepted** — progress doc rewritten from scratch in the control schema with the CURRENT (r3) conclusions only; the r1 claims appear solely as withdrawn-history inside `REVISION:`; amendment-order item 7 renamed to "the separate frozen BEAR-risk-switch preregistration" | progress doc; amendment-order table |
| 2 | **A5.4/A5.5 overstated assumption-only arithmetic as operational probability and identifiability** — the "coin-flip" halt claim and the ~1,800-pair figure rest on unstated independence/normality and on σ(open→close), not the actual paired timing residual; clustering, beta, trigger conditioning, and repeated names change effective N; pairing/covariates may reduce variance. Require a preregistered pilot variance/correlation estimate, cluster unit, target effect, α/power, attrition/censoring allowance, and a blinded sample-size re-estimation rule; if underpowered, label the operator path explicitly as risk acceptance | **Accepted** — A5.4 restated as a sensitivity scenario (formula + assumptions; "material outcome", no probability claim; pre-committed response to a noise-halt). A5.5 restated as an upper-bound scenario plus the required §9.4 prereg machinery (i–vi), with the explicit rule: underpowered ⇒ §9.3a expansion is **recorded RISK ACCEPTANCE, never evidence of economic benefit** | A5.4, A5.5, open question 5 |
