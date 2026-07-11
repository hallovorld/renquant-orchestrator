# Enablement evidence packet — one-share floor, software stops, fractional (strategy-104 #55/#56)

STATUS: evidence packet → Codex re-review + operator decision
DATE: 2026-07-11
CONTEXT: Codex CHANGES_REQUESTED on strategy-104 #55 (one-share floor + software_stops
enable) and #56 (fractional enable). This packet assembles the demanded evidence from
read-only sources only: the production decision ledger (a scratchpad COPY of
`data/runs.alpaca.db` / `data/runs.alpaca_shadow.db`), the pinned runtime checkouts,
umbrella OHLCV, launchd state, and operational tests run entirely in the scratchpad.
No production path was written; no order was placed; no config was changed.
Raw method + outputs: `doc/research/evidence/2026-07-11-enablement/`.

## Bottom line

| Feature | Verdict | One number |
|---|---|---|
| One-share floor (#55) | **Evidence SUBSTANTIAL, prereg gate not literally met** — offline prod-ledger replay quantifies the enable delta and bounds; the armed shadow instrument is structurally unable to satisfy RS-2 §A-3 as written (scorer mismatch), so the operator must either accept the replay as the gate instrument (recorded deviation) or order a prod-mirror shadow arm | +$392–$1,356/session recaptured deployment (mean $917 ≈ 8.5% PV) on 7 of 28 sessions, zero admission distortion |
| software_stops (#55) | **Machinery VERIFIED, stage-3 operational evidence MISSING** — 12/12 operational tests pass against the pinned runtime code incl. the registry-freshness watchdog; but the pager is not scheduled anywhere, page-on-missed-pass never fired, 0 armed-shadow sessions, machine-death sign-off absent | pager launchd entries: **0** |
| Fractional (#56) | **NOT READY — mechanically premature, would fail-close ALL buys** — the live runner's broker adapter lacks the `broker_fractional_contract` methods the capability gate requires, and the stop layer is unarmed; enabling today halts every buy (fail-closed by design), which is *worse* than status quo | prereg fractional shadow sessions: **0** |

Recommendation [my judgment]: keep every enablement bit in #55/#56 OFF, exactly as
Codex ruled. The floor is one recorded decision away from enablement; stops need two
operator ops-acts (pager + signature); fractional needs a wiring PR before its gate can
even pass.

## 0. What Codex demanded (verbatim anchors)

From the #55 review: "(1) one-share-floor enablement needs the pre-registered RS-2
shadow/replay gate and decision evidence, not a single historic $1,355 deployment
estimate; (2) software_stops enablement still lacks the required stage-3 shadow packet,
pager/SLA proof, registry freshness operational test, and explicit machine-death risk
acceptance". From the #56 review: "the pre-registered validation, broker
capability/guard proof, operational stop evidence, and explicit signed-off risk
decision".

## 1. Why these enablements matter now (D6 / cash-drag framing)

- Live account 2026-07-10: equity $10,750.94, settled cash $9,129 — **~85% cash**
  [VERIFIED: `logs/intraday_104/2026-07-10.log` broker-connect line].
- The sanctioned cash-drag route after the D6-round rejections is **parking sleeve +
  Deployment Governor L1**; fractional was re-scoped (D7, orchestrator #444) to
  **sizing fidelity** and the one-share floor (A-3) to **selection-artifact removal** —
  neither claims the deployment mandate, but both stop already-admitted conviction
  from being zeroed by whole-share rounding
  [VERIFIED: `doc/research/2026-07-09-d7-fractional-reopen-analysis.md`;
  `doc/research/2026-07-09-cash-drag-binding-constraints-update.md` — whole-share
  quantization killed 2 of the top-3 slots on 07-02].
- The replay below shows the floor alone re-deploys ~$900/session (~8.5% of PV) of
  conviction the model already voted for, on a quarter of sessions, without touching
  admission.

## 2. One-share floor (A-3)

### 2.1 Prereg-style claim

Under the pinned prod config (strategy-104, BULL_CALM `max_position_pct=0.12`,
`cash_reserve_pct=0`), enabling `sizing.one_share_floor_enabled` changes ONLY the
sizing of candidates that (i) passed every admission gate and (ii) rounded to 0 shares
purely because share price > Kelly target notional; each such candidate is rounded up
to exactly 1 share iff it fits the regime cap and leftover cash, in a deferred pass
that cannot displace a normally-sized candidate.

### 2.2 The RS-2 §A-3 gate — what exists, what cannot exist as written

The prereg protocol (`doc/research/2026-07-02-rs2-lane-a-timing.md` §A-3) requires a
frozen ≥10-session list against a baseline of **current production behavior, same
session set, same admission universe**.

- **Armed shadow instrument cannot satisfy this** [VERIFIED]: the ops shadow config
  (floor=ON since pin 8b2a592, 2026-07-09) runs scorer `hf_patchtst`; prod runs `xgb`.
  The two-arm §2a configs (`shadow_a`/`shadow_b`) also run `hf_patchtst` and both carry
  floor=ON (it is not their treatment variable). No armed instrument holds the prod
  admission universe while varying only the floor.
- **Shadow yield since arming is zero anyway** [VERIFIED: `runs.alpaca_shadow.db`]:
  22 shadow runs over 07-09..07-11, `n_buys=0` in all; every candidate blocked at
  rank/QP-admission stages; `one_share_floor_roundups` appears **0** times in the
  entire shadow DB. The floor has had zero opportunities to express in shadow.
- **Two-arm A/B: 0 valid sessions** [VERIFIED: `/Users/renhao/renquant-shadow-ab/`]:
  3 attempted pairs, all invalidated (07-10 artifact-resolution precheck failure;
  07-11 `renquant-strategy-104: working tree DIRTY ('?? logs/')` — see §5 blocker).

### 2.3 The replay (this packet's instrument)

Offline single-delta replay over the production ledger — same sessions, same admission,
same config, floor the only change — implementing the exact rescue semantics of
`task_selection.py` (eligibility → regime cap → deferred leftover-cash pass). Method +
full output: `evidence/2026-07-11-enablement/floor_replay.py` / `floor_replay_result.json`.
Price source is the run-date daily close (intent-time quotes unavailable offline —
recorded caveat; same-day cross-validation below bounds the error).

**Results (window 2026-06-01 → 2026-07-10, 28 prod session dates)** [VERIFIED]:

| Date | Rescued (1 share) | Not rescued | Deployment Δ | Cash % before → after | Max rescue as %PV |
|---|---|---|---|---|---|
| 06-22 | AVGO | ASML (cap) | $392 | 83.5 → 79.8 | 3.7% |
| 06-23 | — | ASML (cap) | $0 | 78.9 → 78.9 | — |
| 06-24 | CAT | — | $994 | 76.0 → 66.7 | 9.3% |
| 06-29 | BLK | — | $950 | 76.8 → 68.0 | 8.8% |
| 06-30 | BLK | — | $962 | 76.7 → 67.9 | 8.8% |
| 07-01 | BLK | — | $980 | 75.3 → 66.3 | 9.1% |
| 07-02 | BLK + AVGO | — | $1,356 | 77.7 → 65.0 | 9.3% |
| 07-10 | EME | — | $782 | 81.3 → 74.0 | 7.3% |

- **Selection-by-share-price artifact rate** (the A-3 estimand): baseline 0% of
  zero-share-rounded candidates deploy; floor-ON 10/11 candidate-events deploy (the
  single exception is the correct one, see next bullet). Rescued names: AVGO, BLK,
  CAT, EME — exactly the BLK-class high-price names the artifact suppresses.
- **Cap boundedness demonstrated by counter-example** [VERIFIED]: ASML ($1,778–1,929)
  exceeds the 12%×PV regime cap (~$1,267) on both its dates and is correctly NOT
  rescued — the floor is not an unconditional round-up.
- **Zero admission distortion** [VERIFIED]: `n_buys=0` in every affected run, so no
  normally-sized candidate existed to displace; every rescue fits leftover cash
  (reserve=0 in BULL_CALM); max single-name rescue 9.3% PV < 12% cap; post-rescue
  cash never below 65%.
- **Cross-validation against the live measurement** [VERIFIED]: replay 07-02 =
  BLK $995.73 + AVGO $360.45 = $1,356.18 vs the independently recorded 07-02 live
  measurement $1,355 (BLK $995 + AVGO $360, config annotation + pipeline doc). The
  replay reproduces the number Codex called "a single historic estimate" — and extends
  it to 7 sessions with bounds.
- Non-degradation gate: turnover +1 buy/rescue-session by construction; concentration
  and cash bounded as above; drawdown/economic outcome NOT measurable at this sample
  size (the protocol itself says 10 sessions validate plumbing, not economics).

### 2.4 Floor — gaps

1. The RS-2 protocol's frozen numeric tolerances were never committed; freezing them
   now, before more data, is still possible and required.
2. Replay uses daily closes, not intent-time quotes (bounded by the 07-02 agreement).
3. The literal instrument the protocol names (shadow arm, same admission universe)
   does not exist and would need a prod-mirror shadow config (xgb + floor-ON single
   delta) plus ≥10 sessions of buy-stage activity — note prod itself produced
   zero-share events on only 8 of 28 dates, so 10 *expressed* sessions ≈ 5+ calendar
   weeks.

## 3. Software stops (S-FRAC stage 3)

### 3.1 What is armed today

- `execution.software_stops.enabled=false` in ALL pinned configs including shadow
  (deliberate: "arming the protection layer is a live-safety act, not a shadow
  experiment") [VERIFIED: pinned strategy-104 runtime configs].
- Registry file does not exist at the prod path; the liveness CLI run read-only
  against the real default path returns exit 0 "layer has never armed a stop"
  [VERIFIED: operational test #12].
- Current live book (MU/GRMN/AVGO, 1 share each): `live_state.alpaca.json`
  `stop_orders={}`; zero Z9/GTC lines in the 07-10 daily+intraday logs; historical
  stop exits (ORCL 06-10/11, CRWD 07-02) all came from the loop-resident
  `SELL_ATTEMPT_stop_loss/trailing_stop` path. Whether broker-resident GTC
  catastrophe stops are actually open at the broker **cannot be confirmed offline**
  — needs a read-only broker open-orders query. [GAP]

### 3.2 Registry freshness operational test (Codex demand #2, item 3) — DONE

Run 2026-07-11 against the PINNED runtime module
(`.subrepo_runtime/repos/renquant-pipeline/src/renquant_pipeline/software_stops.py`)
with a scratchpad registry mirroring the actual live book (MU/GRMN/AVGO ×1.0, stops at
the Z9 catastrophe distance 20% under the 07-10 closes). **12/12 PASS** [VERIFIED:
`evidence/2026-07-11-enablement/stops_operational_test_result.json`]:

| # | Check | Result |
|---|---|---|
| 1 | `from_config(enabled=false)` → layer does not exist (inert) | PASS |
| 2 | `from_config(enabled=true)` arms; broker-tagged path | PASS |
| 3 | register 3 stops == current live book, persisted atomically | PASS |
| 4 | evaluate at current prices: no false trigger; heartbeat stamped, age<1m, stale=False | PASS |
| 5 | ratchet-only: stop-lowering REFUSED and logged | PASS |
| 6 | breach → full-qty market-exit intent with measured gap_pct (10% gap case) | PASS |
| 7 | `gc(current_positions)`: ghost entry dropped → registry reconciles to positions | PASS |
| 8 | liveness CLI, fresh heartbeat, in-session → exit 0 OK | PASS |
| 9 | liveness CLI, 45m-old heartbeat (>30m budget), in-session → exit 1 STALE + runbook text | PASS |
| 10 | liveness CLI, stale but off-session (Saturday) → exit 0 by design | PASS |
| 11 | liveness CLI, corrupt registry → exit 2 CORRUPT, "OPERATOR ACTION REQUIRED" | PASS |
| 12 | liveness CLI vs REAL prod path → exit 0 "never armed" (current truth) | PASS |

Plus the owning repos' suites re-run locally: renquant-pipeline
`test_one_share_floor_initiation.py` + `test_software_stops.py` → **49 passed**;
renquant-execution `test_order_math.py` + `test_readonly_broker_port.py` →
**41 passed** [VERIFIED, 2026-07-11, `-p no:cacheprovider`].

### 3.3 Stage-3 packet scorecard (design §6 / D7 list)

| Stage-3 requirement | Status |
|---|---|
| ≥10 frozen shadow sessions, fractional qty sized & would-submit, stop armed at entry, clean liquidation, zero dust | **0 sessions** — stops+fractional armed nowhere, incl. shadow [VERIFIED] |
| Registry freshness operational test | **DONE** (§3.2) |
| Pager/SLA proof: test-fired page on a missed pass; §3.4 SLA = page ≤15m, respond ≤60m | **MISSING**: no launchd/cron entry anywhere references `check_software_stops_liveness.py` [VERIFIED: plist grep]; STALE→exit-1 detection proven (§3.2 #9) but no page has ever fired to the real topic and no response time is on record |
| Rollback drill (flag OFF with existing fractional holding stays exitable + stop-covered) | **MISSING** (requires a fractional holding; shadow-executable later) |
| Explicit machine-death risk acceptance (~2% PV @ assumed ≤20% adverse move on the 10% book cap; ~4% @ 40% gap) | **MISSING** — operator signature; it is an assumption, not an engineered bound |

## 4. Fractional (#56)

### 4.1 Mechanical readiness — the gate would fail-close

`fractional_capability_gate` (umbrella `adapters/commit_contract.py:190`) requires,
when enabled: (a) the broker adapter exposes `is_fractionable` + a no-submit
classifier; (b) the software-stop layer reports armed. Today:

- The LIVE runner's broker is umbrella `live/alpaca_broker.py::AlpacaBroker(BaseBroker)`
  — it has **none** of the contract methods [VERIFIED: grep]. They exist only in
  `renquant-execution/src/renquant_execution/alpaca_broker.py:667` and are not wired
  into the live path.
- The stop layer is unarmed (§3).

⇒ Enabling `execution.fractional_shares.enabled` today trips the gate and
**fail-closes ALL BUY emission** ("no fractional BUY ever reaches the broker while the
software-stop layer is absent" — and gate-fail blocks integral buys too). #56 as
stacked would not enable fractional trading; it would halt buying. [VERIFIED: code
inspection of the gate + fail-close path]

### 4.2 What IS in place

- Stages 0–2 merged and pinned: float-preserving commit contract + capability gate
  (44 stage-0 tests), execmath delegation to `renquant_execution.order_math`
  (`cap_affordable_qty`, single owner, fail-closed fallback), readonly notional guard
  (`shadow_ack`, orders swallowed in shadow) [VERIFIED: pinned runtime + suites §3.2].
- The config surface merged default-off as s104 **#54** (2026-07-11T00:09Z,
  supersedes deadlocked #46) but is **not yet pinned** (pin 0e5d9891 = #53 merge,
  2026-07-10T15:11Z) — merged ≠ deployed.

### 4.3 Fractional — gaps (all of Codex's demand list)

1. Pre-registered validation: **0** shadow sessions (not armed anywhere).
2. Broker capability/guard proof: account-level fractional trading status and
   per-symbol `fractionable` truth **unverified** (needs one read-only broker query);
   live-runner wiring of the contract methods **absent** (needs a small PR).
3. Operational stop evidence: §3 scorecard — pager + rollback drill missing.
4. Signed-off risk decision: missing (same signature as §3.3).

## 5. Operational blocker discovered (two-arm A/B keeps voiding)

The 07-11 two-arm session was excluded because the PINNED strategy-104 runtime
checkout is dirty: the legacy ops-shadow admission logger writes
`logs/admission_shadow.jsonl` INTO `.subrepo_runtime/repos/renquant-strategy-104/`
[VERIFIED: file exists; session record quotes `?? logs/`]. Every future 14:35 PT
session will keep excluding pairs until either the manifest check exempts untracked
`logs/` or the admission-shadow path is redirected outside the pinned tree. This
blocks the very shadow-session accumulation several gates above depend on.

## 6. Operator-action shortlist (the exact remaining items)

1. **Floor decision** (unblocks #55's floor bit): EITHER record acceptance of this
   replay as the RS-2 §A-3 gate instrument (deviation on record: replay-not-shadow,
   because the armed shadow runs a different scorer than prod and cannot express the
   estimand) + freeze the §A-3 tolerances + record the enable decision; OR order a
   prod-mirror shadow arm (xgb, floor-ON single delta) and wait for ≥10 expressed
   sessions (≈5+ weeks at observed base rates).
2. **Pager arming + SLA demo** (unblocks software_stops): install a launchd entry for
   `scripts/check_software_stops_liveness.py --broker alpaca --ntfy-topic <real topic>`
   at ~12m cadence; test-fire one STALE page (mechanism already proven, §3.2 #9) and
   record page latency + operator response time vs the 15m/60m SLA.
3. **Machine-death signature** (unblocks stops + fractional): sign the recorded risk
   statement — accepted worst-case ≈2% PV (10% book cap × assumed ≤20% adverse move),
   ≈4% at a 40% gap, machine-liveness dependency in exchange for fractional coverage.
4. **Broker wiring PR** (unblocks fractional mechanically): expose
   `is_fractionable` + no-submit classifier on the live runner's broker (or route the
   live path through the renquant-execution adapter). Until merged+pinned, #56 must
   stay blocked — it would halt all buys.
5. **Read-only broker verification** (one authorized query): account fractional
   capability, per-symbol fractionable flags, and the open-orders truth for GTC
   catastrophe stops (closes §3.1's coverage unknown).
6. **Unblock the two-arm A/B** (orchestrator/pipeline fix): exempt or relocate the
   `logs/` dirt in the pinned strategy-104 runtime (§5).
7. **Pin bump** past s104 #54 when the next deploy window opens (config surface only,
   still default-off).

## 7. Evidence artifacts

- `doc/research/evidence/2026-07-11-enablement/floor_replay.py` — replay method
  (reads a scratchpad DB copy + umbrella OHLCV read-only).
- `doc/research/evidence/2026-07-11-enablement/floor_replay_result.json` — full
  per-run verdicts incl. every not-rescued reason string.
- `doc/research/evidence/2026-07-11-enablement/stops_operational_test.py` — the 12-case
  operational test (imports the PINNED runtime module; scratchpad registry only).
- `doc/research/evidence/2026-07-11-enablement/stops_operational_test_result.json` —
  timestamped results incl. the mirrored live book.
