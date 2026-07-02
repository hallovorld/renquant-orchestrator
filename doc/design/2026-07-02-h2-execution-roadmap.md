# Design: 2026-H2 execution roadmap — NOW / SHORT / MID / LONG, per-item guidance + acceptance criteria

STATUS: design / RFC for review (docs only — no code, config, broker, risk-cap, or sizing change in
this PR). This is the TIME-PHASED execution companion to the thematic capability program (PR #228):
#228 says WHAT and WHY; this document says WHEN, HOW, and DONE-WHEN. Item IDs reference #228
(P0-x/P1-x/P2-x/P3-x, lanes A/B/C, refactors R1–R7) — rationale is not re-derived here.
DATE: 2026-07-02
OPERATOR DIRECTIVES (2026-07-02): (1) a concrete, executable short/mid/long-term plan with
per-item guidance and acceptance criteria; (2) **DATA SPEND IS AUTHORIZED** — data-acquisition
items are execute-now, not pending-approval; (3) the remaining open decisions are **delegated to
the author as owned RESEARCH assignments** (§6) — each must produce a researched recommendation
with evidence, not a menu; the operator retains recorded sign-off ONLY where the capital-risk
profile changes (§9).

---

## 1. Horizon map, decision gates, KPIs

```
NOW (≤72h)      : N1a collectors built+tested (N1b live activation BLOCKED on #224/#227) ·
                  N2 PIT accrual starts · N3 FMP subscribed (SPEND OK)
SHORT (July)    : gate repair → FIRST VERDICT (D1) · ledger wiring · cash-drag lanes A/B ·
                  Track A table+test · open-auction IS prize · hotfix PRs · shadow freshness
MID (Aug–Sep)   : 105 Stage-1 build → readonly → frozen canary · conviction haircut · BL-1 ·
                  R1 shadow migration · R2 fingerprints · down-cap screen · cluster wave-1 ·
                  thesis review #1
LONG (Q4–H1'27) : Track B structural decision (D3) · 105 §9.4 prereg → Stage-2 (D4) ·
                  Stage-3 (conditional) · freshness Final · book-scaling decision · thesis #2
```

**Decision gates** (each = a dated, recorded artifact):
- **D1 — first WF-gate verdict on the live primary** (S4). Branches: PASS → lane C opens for
  study; FAIL(substance) → escalation memo; the model trades on directive only, thesis review #1
  takes it as primary input.
- **D2 — down-cap screen go/no-go** (M7 output; screen itself is pre-authorized as read-only
  research — no operator gate to START it, only to ACT on it).
- **D3 — Track B structural decision** (L1): down-cap expansion / new-data-only / hold.
- **D4 — 105 canary economic authorization** (#208 §9.3a): experiment-PASS or recorded operator
  risk acceptance. Never implied by operational cleanliness.

**Dependency DAG (hard gates — these block START, not just scheduling order).** Codex review,
2026-07-02: a horizon label (NOW/SHORT/MID/LONG) states WHEN an item is planned; it does not by
itself say an item MAY start before its inputs exist. The following are hard gates — the
downstream item literally cannot start (not merely "should wait") until the upstream one lands:

| Upstream (must land first) | Downstream (blocked until then) | Why |
|---|---|---|
| `RenQuant#431` IC-method reconciliation (protocol PROPOSED/INCOMPLETE as of 2026-07-02 — Codex: Algorithm B's estimand, the shift values, and the untouched adjudication slice are not yet fixed; not yet executed) | S9 (Track A conditional pick-quality test) and any Track A/Track B alpha-route commitment (D3, L1) | S8/S9's own AC below still cites the ORIGINALLY-committed `genuine_ic` (0.0417) as the faithfulness bar; #431 found the leak-controlled-IC reproduction against the durable table does not agree in sign with the direction-decision doc's cited BULL_CALM figure. The gate here is stricter than "protocol executed": no alpha-route decision (Track A GO/STOP, D3, L1) may cite either figure as ground truth until #431's protocol is BOTH (a) actually frozen (every choice above pinned, no discretion left) AND (b) executed. |
| `RenQuant#430` durable generator/manifest (evidence-base prerequisite) | S9 (Track A test itself needs the durable table to run against) | already implied by S8→S9 ordering; stated here as an explicit hard gate, not just sequencing, because S9 has no valid input without S8's committed artifact. |
| `renquant-orchestrator#224` (broker-regulatory envelope) AND `#227` (Stage-1 measurement pins), both folded into RFC #208 | N1 (105 collector deployment) and M1/M2 (105 Stage-1 build, canary) | #208 §11's verify-then-bind blocker and the gate-input census / order-type / quote-feed-quality pins are prerequisites for pilot data to be trustworthy at all — deploying collectors or starting Stage-1 build before these land risks a retroactively-dirty corpus. |
| S1–S3 (WF-gate repair, Fixes 1–3) | S4 (first gate verdict, D1) and anything citing a primary-model verdict (thesis review M10) | the gate cannot render a verdict on the live primary until the mechanical/infra bugs blocking it are fixed; no verdict exists to cite before then. |

**Weekly KPI dashboard** (added to the existing daily report; each KPI names its source):
deployed fraction (live_state), gate-verdict age (wf_gate_metadata), ledger coverage %
(decision_outcomes), PIT accrual days (#205 store), collector liveness (log mtimes),
`calibrator_sign_laundered` count (run counters), canary envelope status (when live).

---

## 2. NOW — execute within 72 hours

### N1. 105 collectors scheduled + liveness (P1-5) — SPLIT: N1a unblocked now, N1b BLOCKED
**Codex (2026-07-02):** the Dependency DAG above states #224+#227 as a hard gate on N1, but the
original text below scheduled the WHOLE of N1 as a NOW/72h item and `renquant-orchestrator#232`
already attempts that deployment while both prerequisites are open — a hard gate that does not
change the schedule is not actually enforced. N1 is now split so the schedule matches the gate.

**N1a (preparatory — unblocked, execute now; this is `renquant-orchestrator#232`'s actual scope).**
Build and test the collector-scheduling MECHANISM itself: launchd job definitions, wrapper
scripts, liveness checks, and plist configuration for the merged collectors (#215 paired-IS
harness, #216 quote logger, #220 entry-timing shadow evaluator, #221 data plane), following the
existing `com.renquant.*` plist pattern; each job gets a cadence-lapse ntfy alert per the #212
rule (liveness ≠ freshness). Dry-run/staging validation of the mechanism (does launchd fire on
the intended exchange-session schedule, does the liveness check correctly detect a simulated
lapse) is fine now — none of this activates live collection or appends real session data to the
pilot corpus.
**N1a AC:** launchd plists installed and validated (bootstrap/kickstart succeed; schedule verified
against an exchange-session calendar, not a naive weekday check); a simulated lapse is correctly
flagged in a dry run; log directories created at install; no live collection activated.

**N1b (BLOCKED — do not activate live collection).** Actually enabling the scheduled jobs against
the LIVE machine — the point where they start appending real session data that would count toward
the pilot corpus — is the hard-gated action per the Dependency DAG above:
`renquant-orchestrator#224` (broker-regulatory envelope) AND `#227` (Stage-1 measurement pins)
must both be merged to `main` first. Activating collection before then risks a retroactively-dirty
corpus once the envelope/census requirements land — data collected under an unvetted contract
cannot be retroactively certified clean. **N1b unlocks when #224 AND #227 are both merged.**
**N1b AC (the original N1 AC below, now explicitly gated on the above):** once unlocked, 3
consecutive LIVE sessions with (a) quote-log rows for ≥90% of the watchlist, (b) a paired-IS row
for every live buy, (c) entry-timing shadow rows present; one test-fired lapse alert received.

### N2. PIT estimate-revision accrual starts (P0-1 — time-irreversible)
**Guidance:** unblock #205: assign the snapshotter to base-data; schedule a daily post-close
snapshot job; store as append-only parquet keyed `(symbol, metric, value, available_at)` — the
`available_at` stamp at WRITE time is the whole point; never backfill.
**AC:** ≥3 consecutive daily snapshots appended with write-time `available_at`; missed-day alert
wired; a README in the store documenting the no-backfill invariant.

### N3. FMP Starter subscription + harvest upgrade (P0-2 — SPEND AUTHORIZED)
**Guidance:** subscribe ($29/mo), wire the key, re-run the harvest (`data/fmp_harvest`, PR #409
pattern) across estimates / key-metrics / growth / income endpoints; extend to the 5y history the
tier unlocks.
**AC:** coverage report ≥95% of watchlist on estimates + key-metrics; harvest job green on
schedule; 402-plan-locked error count = 0.
**Cost cap / exit criteria (Codex, 2026-07-02):** ceiling $29/mo — any tier upgrade beyond Starter
requires a fresh recorded spend decision, not implied by this authorization. Exit: cancel if, after
2 full harvest cycles, the coverage AC above is not met (plan-locked / stale data despite the paid
tier) or if RS-3's broader vendor-stack recommendation supersedes this subscription.

---

## 3. SHORT TERM — July 2026 (~22 sessions)

### S1–S3. WF-gate repair, Fix-1/2/3 (P0-3) — the critical path
**Guidance:** three separate PRs in backtesting/model, in order: **Fix-1** unify the sim per-bar
scorer path to `walkforward_gbdt_prod_recipe_v2` (the FileNotFoundError at `sim.py:851 →
panel_scorer.py:201`); **Fix-2** derive the WF-eval config from the ACTIVE primary
(`kind="xgb"` + matching `panel-ltr.json`), re-confirming the current mismatch direction from a
fresh run first; **Fix-3** replace the absolute placebo ceiling with the pre-registered
difference test `real_ic − placebo_ic > margin` — freeze the margin BEFORE implementation
(proposed 0.02, justified against the measured ~+0.04 embargo floor; recorded in the PR).
**AC:** S1: 3 consecutive weekly gate runs with no artifact-path failure. S2: parity guard passes;
the gate reaches its verdict stage. S3: fixture proof — the difference test PASSES a known-clean
synthetic model and FAILS a deliberately leaked one; shuffled-label control reads ≈0 difference.

### S4. First gate verdict on the live primary (decision gate D1)
**Guidance:** run the repaired weekly gate against the live 05-18 XGB; record
`wf_gate_metadata.passed` + failure class in the run bundle; if FAIL(substance), write the
escalation memo the same day (the model is live by directive only).
**AC:** a verdict exists (either way) — the first since 05-18; escalation memo if Fix-4 recurs;
thesis review #1 cites it.

### S5. Decision-ledger wiring (P0-4 / R5)
**Guidance:** pipeline PR extending the live path to persist per-(date,name) raw / panel_score /
mu / er / sigma / every gate-drop reason / selection outcome; orchestrator PR materializing
`decision_outcomes` (join fwd realized returns at 20/60d); backfill from the existing
`runs.alpaca.db` where reconstructable.
**AC:** 100% of live runs write candidate rows; outcomes join covers ≥95% of decisions older than
the horizon; the 2026-07-01 OXY decision is queryable end-to-end (score → gates → size → fill →
fwd outcome) as the canonical fixture.

### S6. Cash-drag lane A (P1-1) — three config experiments, gates unchanged
**Guidance:** **A-1** recover the `qp_cash_drag_lambda=0` rationale from git blame; shadow-replay
10 sessions at λ ∈ {0, 0.02, 0.05} (the #195 harness pattern); pick by deployed-fraction gain vs
turnover cost. **A-2** after A-1 lands, config PR `panel_buy_top_n` 3→5 (within
`max_positions_per_sector=6` + correlation gate). **A-3** pipeline PR extending the existing QP
`min_share_floor` to INITIATION: allow one share when `price > target_notional` and one share ≤
min(max_position_pct × PV, headroom).
**AC:** deployed fraction ≥60% within 15 sessions of full enable; ZERO buys bypass
conviction/veto/correlation (ledger-verified); every A-3 one-share buy logged with reason; drop
reasons for the window/floor now first-class ledger fields.

### S7. Cash-drag lane B — parking sleeve (P1-2; recommendation via research item RS-1, §6)
**Guidance:** implement behind a config flag once RS-1's recommendation is recorded: sweep idle
cash above reserve (5% PV + open-order headroom) into the recommended vehicle; sleeve sold first
to fund admitted buys; excluded from QP/exits/correlation; BEAR sweeps to cash. 10-session shadow
of sweep/fund plumbing before enable.
**AC:** shadow: 10 sessions, sweep and fund legs both exercised, reserve never breached; live:
idle cash ≤ reserve + 1% at every close; a BEAR-regime sim test shows the sleeve exits.

### S8. Track A regeneration PR (P1-3a) — IN FLIGHT, `RenQuant#430`/`#431`
**Guidance:** commit `scripts/regen_oos_pick_table.py` (read-only re-score of the prod manifest
`walkforward_manifest_gbdt_prod_recipe_v2.json` over the 508 OOS dates) → durable evidence
(manifest + regeneratable table, never a raw parquet committed to git — the protected-path gate
rejects `data/*.parquet`) with `{date,name,score,decile_rank,fwd_60d_excess,regime}`.
**AC (status, Codex 2026-07-02): row/date/window reproduction succeeded (147,066 rows / 508 dates,
exact match), but the `genuine_ic` faithfulness bar as originally stated (±0.001 vs the committed
0.0417) did NOT clean-reproduce — `RenQuant#431`'s leak-controlled-IC rerun found +0.076
(overall) / +0.044 (BULL_CALM, leak-adjusted), disagreeing with the cited figures including SIGN
for BULL_CALM. This AC is therefore UNRESOLVED, not met — see the Dependency DAG above and S9.**

### S9. Track A conditional pick-quality test (P1-3b) — BLOCKED on `RenQuant#431`
**Guidance:** run the FROZEN spec (direction-decision §4) on the S8 table — conditioning variables
1–3 verified, 4–5 only after their PIT checks; chronological 60/40 split, 60d embargo; original
GO/STOP criteria (a)–(e) untouched. **Hard gate (Codex, 2026-07-02): do NOT start this item until
`RenQuant#431`'s reconciliation protocol is BOTH actually frozen — as of 2026-07-02 it is still
PROPOSED/INCOMPLETE: Algorithm B's exact estimand, the shift values, and the untouched
adjudication slice remain open choices, not yet pinned — AND THEN executed, producing a single
trusted genuine-IC methodology.** Running S9 against a disputed, still-mutable input metric would
produce a verdict that inherits the dispute (and, worse, the input could still be tuned after the
fact if the protocol isn't genuinely frozen first).
**AC:** a recorded verdict — GO (build the meta-label filter) or NULL (recorded, Track B becomes
the only directional path); all five metrics with bootstrap CIs; zero post-hoc criterion edits.

### S10. Retrospective open-auction IS measurement (P1-4 — sizes the 105 prize)
**Guidance:** read-only study over all historical live buys in `runs.alpaca.db`: realized open
fill vs same-day VWAP / close / next-close references (minute data where available); report
bps/trade with CI, split by name liquidity.
**AC:** memo in doc/research with the bps estimate + CI over the full live-buy history; explicitly
feeds the 105 §9.4 prereg and the L2 item; states whether the Stage-1/2 prize is material at
current order sizes.

### S11. Durable hotfix PRs (R7)
**Guidance:** inventory live-tree dirt (`git status` across umbrella + subrepo checkouts); commit
the adapter-save NameError fix and the live_state freshness fix to origin/main; ticket or discard
every other dirt item; document the recovery-checkout drill (what to do INSTEAD of reset --hard).
**AC:** origin/main ships the fixes; live tree diff vs pinned refs = empty or fully ticketed; the
drill doc merged.

### S12. Shadow-scorer freshness implementation (#212 phases 2–4)
**Guidance:** per the merged design: panel-refresh-prerequisite diagnosis FIRST (why does
`transformer_v4_wl200_clean.parquet` end 2026-02-10 — builder-not-run vs label-dropna clip; memo),
then scheduled retrain + validated-promote gate.
**AC:** diagnosis memo names the root cause; served shadow pin advances through a validated
promote; monitor `healthy` under the #213 semantics.

---

## 4. MID TERM — August–September 2026

### M1. 105 Stage-1 three-repo build → readonly (P3-3a)
**Guidance:** strict #208 §8 order — execution (order-lifecycle state machine, §7 invariants) →
pipeline (gates on live state, sim-parity) → orchestrator (scheduling, default-OFF flag, canary
allowlist, per-tick bundles, four-class replay). Each repo's acceptance tests are enumerated in
#208 §8; add #223's amendments: gate-input census artifact, pre-declared order type, day-trade-free
envelope per the verified intraday-margin regime, exits-always-allowed.
**AC:** per-repo acceptance tests green; flag default-OFF until both upstream repos pinned;
**readonly K=5 sessions**: decisions logged, nothing placed, four-class replay green every tick,
census complete (any un-classified gate input = test failure).

### M2. 105 frozen canary — operational/safety validation ONLY, never economic authorization
**Scope note (Codex, 2026-07-02):** running the frozen canary requires ONLY #208 §9.3's operational
acceptance (no-leak / idempotency / reconciliation / Tier-1 clean) + the pre-declared envelope
below — it does NOT require D4. Completing the 20-session canary cleanly proves the order-emission
plumbing is safe; it proves NOTHING about whether moving entries intraday is economically
beneficial, and must never be read as implying that. D4 (experiment-PASS or recorded operator risk
acceptance) is required ONLY to EXPAND beyond this frozen envelope (more names, higher cap, more
sessions) or to go live generally — never to run the frozen canary itself.
**Guidance:** 1–2 pre-declared names, pre-declared notional cap, ≤20 sessions, 1.5% loss budget,
HARD-halt stop conditions (#208 §9.3a); paired data accrues to the ledger; the noise-halt response
is pre-committed (halt → re-authorization is itself a recorded decision).
**AC:** #208 §9.3 operational acceptance (no-leak / idempotency / reconciliation / Tier-1 clean)
every session; envelope never exceeded; on exhaustion, HARD halt honored (reversion to 盘后 batch)
— demonstrated, not assumed.

### M3. Conviction uncertainty haircut (P2-1 — needs S5 data)
**Guidance:** ledger replay comparing admit rule `mu > floor` vs `mu − k·SE(mu) > floor` (k ∈
{0.5, 1.0}); SE from the calibrator band or bootstrap over the S8 table; config PR only if the
replay shows the haircut removes more losers than winners (net expectancy gain).
**AC:** replay report with per-regime cuts; config PR cites it; post-enable, thin-margin buys
(margin < 25% of floor) drop to ~0 in the ledger.

### M4. BL-1 calibration recentering (P2-2)
**Guidance:** model+pipeline PR recentering the raw-score distribution feeding the calibrator
(cross-sectional center per bar) so bearish raw ⇒ non-positive ER; keep the BL-4
signal-direction gate as the interim guard; shadow replay before cutover.
**AC:** `calibrator_sign_laundered` falls from ~44/90 to single digits; admission set unchanged
except sign-laundered names (ledger diff); no new fail-closed events in 30 days.

### M5. R1 — tournament retirement shadow migration
**Guidance:** implement panel-based admission (name admissible iff features fresh + panel scores
it) as a parallel LOGGED set; run ≥20 sessions side-by-side; produce the delta report (names
admitted/dropped by each rule + their fwd outcomes); then a cutover PR with the tournament kept
read-only for one quarter as rollback.
**AC:** delta report shows panel-admission is a superset-or-equal on names with valid data and
drops only data-stale names; cutover merged; the entire per-ticker freshness surface (#210 §1A)
retired from monitoring after the rollback quarter.

### M6. R2 — fingerprint unification
**Guidance:** extract one `model_content_sha256` into renquant-common; migrate the three call
sites (runtime/pipeline, calibrator-fit/model, umbrella-local) with a fixture asserting identical
hashes on identical inputs; re-stamp scripts become wrappers.
**AC:** fixture green across all three import paths; zero `panel_scorer_config_mismatch` /
calibrator-mismatch fail-closes for 30 days post-deploy.

### M7. Down-cap MVP screen (P3-2; read-only research — pre-authorized; ACTING on it = D2/D3)
**Guidance:** build a liquid small/mid panel (~300–500 names, ADV ≥ $5M, price ≥ $5, 8y history
where available; survivorship handled by point-in-time membership from the index vendor or
best-effort with the bias documented); re-run the EXISTING scan suite (sighunt / robustness /
regimemom / fundamentals_scan) + placebo injection at REALISTIC small-cap costs (pre-register
25–40bps round-trip, not 11bps); thresholds frozen BEFORE running (net L/S Sharpe, IC ≥ 1.25× the
placebo floor, regime robustness).
**AC:** a go/no-go evidence memo with pre-registered thresholds, net-of-cost results, and the
survivorship caveat stated; NO production change from this item.

### M8. Cluster-wave 1 breadth expansion (P3-1)
**Guidance:** per E34's resume condition — cluster-based admission (top-IC tickers per sector
bucket), +~100 names, paired WF vs baseline BEFORE any production use; halt waves on degradation.
**AC:** wave-1 paired IC ≥ baseline within the noise band (pre-registered); else the wave is
recorded NO-GO and waves stop.

### M9. Freshness text alignment + snapshot generation (#223 A1/A6 follow-ups)
**Guidance:** amendment PRs restating #210 §2/§5.1 and #212 §3.2 in `label_observation_cutoff` /
frontier-distance semantics with per-recipe label horizons; umbrella PR generating the
`strategy-104.md` production snapshot from pinned config + artifact metadata with a staleness CI
check.
**AC:** RFC text matches the #213 implementation; generated snapshot present; CI fails on
snapshot older than the pinned config's last change + N days.

### M10. Thesis review #1 (the macro-falsifiability artifact)
**Guidance:** a doc/research review with PRE-REGISTERED kill/pivot criteria, written BEFORE
reading the quarter's evidence, then judged against D1 (gate verdict), S9 (Track A), S10 (prize),
M7 (down-cap). The criteria must include the honest terminal branch: no validated edge + Track A
NULL + down-cap null ⇒ default posture becomes benchmark-sleeve mode (lane B absorbs the book)
while PIT data accrues — active single-name risk requires a recorded operator override.
**AC:** review exists with criteria frozen before evidence; operator sign-off; next review dated.

---

## 5. LONG TERM — Q4 2026 → H1 2027

### L1. Track B structural decision (D3)
**Guidance:** decision doc synthesizing S9 + M7 + M8 + ≥120 days of PIT accrual; options: down-cap
expansion (structural universe change), new-data-only enrichment of the current universe, or hold.
**AC:** recorded decision with evidence citations; if down-cap: a staged migration RFC follows,
never a big-bang universe swap.

### L2. 105 §9.4 simplified experiment prereg (needs M2 pilot data + S10 prize)
**Guidance:** per #223 A5.5's requirements list — pilot paired-residual variance/correlation,
cluster unit, target effect, α/power, attrition allowance, blinded sample-size re-estimation;
frozen before analysis.
**AC:** prereg PR merged; if the re-estimate says underpowered at this scale, the doc SAYS SO and
routes expansion through §9.3a as recorded risk acceptance — never re-labeled as evidence.

### L3. 105 Stage-2 entry-timing intelligence (needs D4)
**Guidance:** pre-register timing policies (VWAP-relative, prior-high break, pullback) as SHADOW
policies in the #220 evaluator first; estimand = conditional timing residual (#223 A4.2 — the
phase −1 directional NO-GO is not re-litigated); live flip only for policies with shadow
outperformance CIs over ≥60 sessions.
**AC:** each candidate policy has a shadow track record before any capital; the live flip PR
cites it.

### L4. 105 Stage-3 / model rework — CONDITIONAL on D3
**Guidance:** only if D3 lands on a new information set (intraday features are only worth
real-time re-scoring if the model has inputs with edge); design RFC first (PIT feature contract
per #208 §6 Stage-3 note).
**AC:** the RFC exists before any build; explicitly deferred if D3 = hold.

### L5. Freshness governance Final (#210 phases, as amended)
**Guidance:** two-path authorization for the ceiling flip (per #223 A3, adopted); Pillar 3 stays
prospective-logging-gated.
**AC:** the ceiling flip is a recorded decision (either path); Pillar 3 unchanged until its
evidence exists.

### L6. Book-scaling decision
**Guidance:** if the capability milestones are green (D1 verdict flowing weekly, deployed
fraction ≥60%, 105 canary operationally clean, thesis review #1 not in terminal branch), put the
scaling question to the operator with the honest 105 economics (per-trade gains scale with order
size; the whole intraday program only pays at larger book size).
**AC:** recorded decision with the capability scorecard attached.

### L7. Thesis review #2
**Guidance:** same pre-registered discipline as M10; judges the full year.
**AC:** review + operator sign-off + next cycle's criteria.

---

## 6. Research assignments — OWNED BY THE AUTHOR (operator delegation, 2026-07-02)

Each produces a **recommendation memo with evidence** (deep-research where external, measured
where internal), filed in doc/research and linked from the relevant roadmap item. The operator
receives a recommendation, not a menu.

| ID | Question (was #228 §5 open question) | Method | Deliverable + AC | Due |
|---|---|---|---|---|
| RS-1 | **Parking-sleeve vehicle** (SPY β≈1 vs T-bill ETF carry vs split) | measure the book's realized benchmark shortfall attributable to idle cash from the ledger; compare sleeve variants' risk contribution at this book's drawdown tolerance; survey settlement/liquidity mechanics (SGOV/BIL spreads, T+1) | memo with ONE recommended vehicle + reserve size + the beta-risk statement the operator signs; AC: S7 implements the recommendation verbatim | before S7 enable (mid-July) |
| RS-2 | **Lane-A timing** (run de-throttle before or after D1's first verdict) | quantify worst-case exposure delta of λ/top_n/one-share at current gates from ledger replay; compare against the D1 timeline | memo recommending enable order + any interim caps; AC: S6 sequencing follows it | with S6 (early July) |
| RS-3 | **Data-vendor stack** (SPEND AUTHORIZED — what exactly to buy) | deep-research: FMP tier vs Polygon vs Alpaca SIP add-on vs Sharadar/Norgate for (a) full-fundamentals+estimates PIT, (b) consolidated tape for 105 IS, (c) small/mid-cap history WITH survivorship-free membership for M7; price the full stack monthly | memo with the exact subscription list + monthly total + which roadmap item each feeds; AC: N3/M7/105-pilot procurement follows it; every dataset has an `available_at`-stamped ingest plan. **Cost cap (Codex, 2026-07-02): the memo must state an explicit monthly total ceiling before any subscription beyond N3's $29/mo is purchased — spend above that ceiling requires a fresh operator sign-off, "SPEND IS AUTHORIZED" (line 9) covers the vendors this memo recommends AT the priced total, not an open-ended budget.** Each recommended vendor gets a stated exit criterion (e.g. coverage/quality bar unmet after N cycles, or superseded by a cheaper/better source) so a subscription is never indefinite by default. | 1 week |
| RS-4 | **R1 migration safety** (tournament retirement) | the M5 shadow delta report IS the research; additionally quantify what (if anything) the tournament uniquely contributes via ledger attribution | the M5 delta report doubles as the recommendation; AC: cutover PR cites it | with M5 |
| RS-5 | **Down-cap panel construction** (survivorship-clean membership source, cost model 25–40bps validation, borrow/liquidity constraints at our size) | deep-research + vendor eval (feeds from RS-3); validate the cost assumption against published small-cap spread studies + our own broker fills where any exist | M7's panel spec + frozen thresholds; AC: M7 runs on it | before M7 (early Aug) |
| RS-6 | **Benchmark + KPI definitions** (what the weekly scorecard measures — deployed fraction, drag decomposition, expectancy per admitted name) | define each KPI's exact query against the S5 ledger; document in the dashboard PR | KPI spec merged with the dashboard; AC: §1 dashboard ships to the daily report | with S5 |

## 7. Explicitly OUT of plan (settled — not re-pitched)

Architecture bake-offs (E27/E33: linear ≥ transformer at this scale); fractional shares
(operator-closed 2026-06-30); multi-horizon sleeves (#149); label neutralization (#171);
regime-split panel-exit (ledger-refuted); intraday directional alpha (phase −1 NO-GO); blind
universe expansion (E34); new factor scans on the current panel (four NULLs this cycle).

## 8. Cadence and re-baseline rules

- **Weekly:** ops review against the §1 KPI dashboard; any red KPI gets a dated note in the
  roadmap addendum.
- **Monthly:** roadmap re-baseline — a dated addendum section to THIS doc (never silent edits);
  items may move horizons only with a stated reason. **Scope limit (Codex, 2026-07-02): a
  re-baseline may update FORECASTS/ESTIMATES only** (expected dates, expected KPI values,
  sequencing horizons). It may **never**, under any addendum, silently revise: a pre-registered
  estimand (e.g. S9/Track A's conditional-pick-quality definition, #431's reconciliation protocol
  — PROPOSED/INCOMPLETE as of 2026-07-02, not yet frozen — once it IS frozen, only via a fresh
  #431-equivalent review round, never a monthly re-baseline addendum, L2's #223 A5.5 power-prereg
  requirements), a GO/STOP threshold (S9's (a)–(e) criteria,
  M7's frozen thresholds, M8's wave pre-registered noise band), what counts as confirmation data
  (S9's held-out test window, #431's untouched adjudication slice), or a stop rule (M2's HARD-halt
  envelope, L2's underpowered-routes-to-§9.3a rule). Any of those may only change via a fresh,
  explicitly-labeled amendment PR to the document that originally froze them — never via this
  roadmap's own monthly addendum.
- **Quarterly:** thesis review (M10 / L7) — the only forum that may change the program's
  DIRECTION (everything else is sequencing).
- Every item lands via the normal control plane: design-via-PR where behavior changes, progress
  doc per PR, Codex review, no live-tree edits, no branch-protection bypass.

## 9. The short list that still needs operator sign-off (capital-risk changes only)

1. **RS-1's sleeve recommendation** — signing the beta-risk statement (lane B enable).
2. **M2 canary start** — confirming the pre-declared envelope (names, cap, 20 sessions, 1.5%).
3. **D3 / L6** — Track B structural direction and book scaling.
4. **Thesis-review sign-offs** (M10 / L7).

Everything else in this document is delegated: research (§6) is the author's responsibility;
implementation items proceed through the normal review control plane without a separate
operator ask.
