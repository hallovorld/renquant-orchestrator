# Design review: 104/105 RFC amendments — label-horizon freshness key, intraday regulatory envelope, governance convergence

STATUS: design / RFC for review (docs only — no code, config, broker, risk-cap, or sizing change).
DATE: 2026-07-01
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
| A1 | The fast-axis freshness ceiling (21–45d grid; 35d shadow tier) is **structurally unsatisfiable** for models trained on `fwd_60d` labels — the freshness key must split the serving-feature axis from the training-label lag budget | #210, #212 | **blocking contradiction** |
| A2 | **PDT / account-type / same-session round-trip** constraints are absent from the Stage-1 intraday design; intraday entries + the existing intraday risk exits generate day trades on a sub-$25k account | #208 | **blocking gap** |
| A3 | #210's Final phase has an **experiment-only authorization path** that will, with high probability, never complete — inconsistent with the two-path authorization #208 §9.3a already adopted; Fix-3 (placebo floor) is mis-classified as bypassable infra | #210 | governance |
| A4 | Stage 1–2 framing ("catch the entry as it forms") does not match the frozen-signal mechanics; Stage-2's estimand is not reconciled with the already-measured phase −1 intraday-alpha NO-GO | #208 | framing / estimand |
| A5 | Engineering pins needed before pilot data is trustworthy: gate-input census, order-type pre-declaration, SIP-vs-IEX quote quality, loss-budget noise probability, identifiability back-of-envelope, batch-rotation churn diagnostic, active-path verification | #208 | measurement integrity |
| A6 | `strategy-104.md`'s hand-written production snapshot is stale (pre-dates the 06-23 XGB re-promotion) — the same premise rot that invalidated #210 R1 | umbrella | doc integrity |
| A7 | The direction-decision's regeneration PR is the evidence base for the whole 105 direction, not merely Track A's first step; GO criterion (d) is near-certain to fail given the known BEAR-only skill slice | direction decision | evidence / prereg |

---

## A1. Label-horizon contradiction: split the freshness key (blocking; amends #210 §2/§3/§5.1 and #212 §3.2)

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

**Proposed amendment — two distinct freshness quantities, never one number:**

1. **Serving-feature-axis freshness** — the end date of the feature panel the model *scores* at
   inference. This axis has no label dependence and can and should be current (T-1). The operator's
   28d directive is meaningful here, and a 21–45d grid is feasible here.
2. **Training-label lag budget** — the training cutoff judged against the **achievable frontier**,
   not against today: `today − effective_selection_cutoff ≤ label_horizon + ingest_slack + X`.
   The monitored quantity is `X` (distance from the frontier), with a structural floor stated
   explicitly per model family (fwd_60d ⇒ frontier ≈ today − ~88 calendar days). A model is
   training-stale when it lags **what was trainable**, not when it lags today.

Concretely: rewrite #210 §2's fast-axis definition to name both quantities; restate the §5.1 grid as
a grid over frontier-distance `X` (plus the serving-axis ceiling as its own dimension); restate the
Pillar-1 tier table and #212 §3.2's tier table in frontier-distance terms. `trained_date` re-enters
only as the conjunction the operator's directive actually wants: **trained recently AND on data at
the achievable frontier** — either alone is gameable (a fresh retrain on a stale panel, which #212 r2
already blocks; or an old artifact whose cutoff was once at-frontier).

**#212 corollary.** §3.1/§4-step-1 say "refresh the panel to the current point-in-time" — for a
labeled training panel this is impossible; the correct target is the frontier. Additionally the RFC
delegates the panel refresh ("base-data / model-owned work") in one line without diagnosing **why**
`transformer_v4_wl200_clean.parquet` stopped at 2026-02-10 — whether the builder simply never re-ran,
or a label-join `dropna` clips the axis (the #26 family). The amendment asks for that diagnosis to be
a named deliverable of #212 Phase 3, because the remediation differs (schedule the builder vs fix the
join) and the failure family has already bitten once.

---

## A2. Intraday regulatory envelope: PDT / account type / same-session round trips (blocking; amends #208 §10/§11/§11b)

#208 nowhere mentions the pattern-day-trader rule, the account type, or settlement mechanics. On the
current ~$10.5k account this is a hard, non-statistical constraint on Stage 1:

- **Intraday entry + same-session risk exit = one day trade.** Stage 1 adds intraday entries while
  the existing 12-min loop's risk exits keep running. In a **margin** account under $25k equity,
  4+ day trades in 5 business days flags PDT and the broker restricts the account. In a **cash**
  account, PDT does not apply but **good-faith-violation / settlement** rules do — and §7's
  `reserved_cash` models unsettled *buys* only, not the unavailability of same-day *sale proceeds*.
- The §10 envelope (3 entries/day) makes routine PDT breach entirely reachable in one bad week.

**Proposed amendments:**

1. **§11 Stage-1 BLOCKER (new):** confirm the account type (margin vs cash) and record which
   regulatory regime binds (PDT vs GFV/settlement). This is a fact to verify, not a design choice.
2. **§10 envelope (new rows):** a **day-trade counter + budget** maintained per rolling 5 business
   days. Proposed Stage-1 default: **routine day-trade budget = 0** — an intraday-entered name may
   not be exited the same session by the ordinary risk rules; only the Tier-1 HARD-halt /
   catastrophe path may close it same-session (and such an exit decrements the budget and alerts).
   This preserves the multi-day-hold mandate, costs nothing Stage 1 needs, and makes the PDT
   counter an invariant instead of a hope.
3. **§7 cash accounting:** if the account is cash, extend `reserved_cash` semantics so same-day sale
   proceeds are excluded from `available` until settled.

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
4. **State the loss-budget noise probability.** 1.5% of equity ≈ **$157**. One or two names at the
   §10 deployment cap (~$1.5k notional) over 20 sessions accumulate ~$130–150 of one-sigma noise —
   the canary halts on market beta with roughly coin-flip probability, independent of the timing
   policy. Fine as a safety bound, but §9.3a should say so and pre-commit the response (halt →
   re-authorize a fresh window is itself a §9.3a decision), so a noise-halt is not misread as an
   economic verdict.
5. **State the identifiability back-of-envelope now.** With σ(open→close) ≈ 150bps already measured,
   detecting a 10bps IS difference at conventional power needs on the order of **~1,800 pairs** —
   years at 1–2 names/day. §9.4 defers the design honestly, but the arithmetic is already knowable:
   the deferred experiment will almost surely return "unidentifiable at this scale," making the
   §9.3a **operator-decision path the realistic route** to any expansion. Saying this now sets the
   operator's expectations before 20 sessions are spent.
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
2. **GO criterion (d) is near-certain to fail as written.** The only skill slice A1 found is BEAR
   (~10% of live time); any regime-keyed conditioning therefore cannot reach (d)'s ≥25% active-day
   floor. If the intent is to force the search toward non-regime conditioners, say so explicitly;
   otherwise add a carve-out for **low-frequency, high-value risk-switch filters** (a BEAR-only
   filter judged on its contribution during its active slice, with the capital-weighted §4(a) gate
   still binding). A pre-registered threshold that the already-known evidence guarantees to fail is
   not a test; it is a foregone conclusion wearing a lab coat.

---

## Proposed amendment order

| Order | Amendment | Doc(s) | Why first |
|---|---|---|---|
| 1 | A1 freshness-key split (serving axis vs frontier distance) | #210 §2/§3/§5.1, #212 §3.2 | every monitor tier and the §5 grid are defined on it; #213's observe-only monitor should adopt the corrected key before its numbers calcify |
| 2 | A2 regulatory envelope (account-type blocker, day-trade budget, cash-settlement accounting) | #208 §7/§10/§11 | hard blocker for any live canary session |
| 3 | A5.1–A5.3 measurement pins (census, order type, quote feed) | #208 §6/§8/§10/§11 | must precede pilot data collection or the corpus is retroactively dirty |
| 4 | A3 governance convergence (two-path Final; Fix-3 fail-closed) | #210 §4/§6 | unblocks the operator's directive without reviving the stats loop |
| 5 | A4 framing/estimand + A5.4–A5.7 | #208 §1/§9/§12 | honesty and diagnostics; no ordering pressure |
| 6 | A6 snapshot generation | umbrella | separate repo, separate PR |
| 7 | A7 regeneration PR + prereg carve-out | direction decision | evidence base for everything above |

## Open questions for the operator / Codex

1. **A1:** confirm the two-quantity freshness key (serving-feature axis + frontier-distance training
   lag) as the amendment to #210 §2 — and what frontier slack `X` to pre-register per model family.
2. **A2:** which account regime binds (margin/PDT vs cash/GFV)? Is the proposed Stage-1
   **day-trade budget = 0** (no same-session exit of intraday entries except Tier-1 halt) acceptable?
3. **A3:** adopt the #208-style two-path authorization for #210's Final (ceiling as risk-policy
   constant by recorded decision), keeping Pillar 3 experiment-gated?
4. **A5.3:** subscribe to the consolidated/SIP feed for the pilot, or record accepted IEX bias?
5. **A5.5:** given the ~1,800-pair identifiability arithmetic, should §9.4 be re-scoped now to a
   diagnostics-plus-operator-decision design instead of a powered non-inferiority test?
6. **A7:** is the (d) active-day floor intentional pressure toward non-regime conditioners, or
   should the risk-switch carve-out be added before the Track-A test runs?
