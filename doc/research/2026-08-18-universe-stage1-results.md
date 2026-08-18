# Universe-extension Stage 1 — the ONE triage run: DEPRIORITIZED (3 of 4 bars pass; the transfer prediction fails)

STATUS: **the authorized one-shot run under the frozen spec — the shot is now
SPENT (U10 marker armed by the committed outputs).** Spec:
`doc/research/2026-08-18-universe-stage1-triage-spec.md` (orch#995, merged).
Runner: `doc/research/data/2026-08-18-universe-stage1-derivation.py` (orch#998,
merged), executed VERBATIM from orchestrator main `9d73d546` — zero edits, zero
added parameters, ONE execution, exit 0. U11 verified the executing bytes
against a freshly FETCHED origin/main before any work; U3's positive control
passed BEFORE any Arm A cross-section was scored. No fix-and-rerun occurred.

DATE: 2026-08-18 (run at 2026-08-18T08:33:45Z, runtime 782.8 s `[VERIFIED —
results JSON run_utc/runtime_sec]`).

SEMANTICS (spec §1): Stage 1 **TRIAGES** — it neither kills nor admits.
DEPRIORITIZED parks the down-cap thesis with evidence at ~zero cost; it is NOT
a kill (survivor-universe fails are directional, not final, in both
directions). PASS (triage) would have authorized ONLY the Stage-2 PIT program
proposal. **Nothing below changes serving, retrains anything, or moves
capital.**

PROVENANCE: every number is `[VERIFIED — read from
doc/research/data/2026-08-18-universe-stage1-results.json / …-obs.csv as
written by this run]` unless tagged otherwise. Runner identity recorded BY THE
RUN ITSELF in the output pins: origin/main `9d73d5463b23218bf8bded9ff75f9bbf479a3543`,
runner sha256 `93877dba751380a3b5a30f83db236821d850759e8d39af13c25d4261e6c7a5a2`
`[VERIFIED — results JSON pins.runner_identity, written after the U11
fetch-first byte compare]`.

## 1. VERDICT (h=60, Arm A — the frozen §5 four-condition bar)

| # | frozen condition | measured | outcome |
|---|---|---|---|
| 1 | net-of-cost Δspread > 0 | **+0.007517** (gross +0.013773 − mean drag 0.006256) | **PASS** |
| 2 | block-t(gross Δ) ≥ 1.0 over 19 blocks | **+1.580** (df=18 context) | **PASS** |
| 3 | >50% of blocks-with-data positive | **73.7%** (14/19 gross blocks) | **PASS** |
| 4 | transfer: ∃ costable ADV bucket with Δspread_A,b ≥ Δspread_W | best bucket **+0.013026** (≥$25M) vs Arm W **+0.071816** | **FAIL** |

**VERDICT: DEPRIORITIZED** — `transfer: no costable bucket with ArmA >= ArmW`
`[VERIFIED — results JSON verdict block; identical string printed by the run]`.
U8 floor met: 19/19 complete blocks had data (≥10 required).

What the run actually found, in one sentence: **the served panel pin's
tail-spread signal DOES transfer out-of-ticker — positive, placebo-beating,
and net-of-cost positive in the ≥$25M-ADV extension bucket — but at ~1/5 the
strength of the watchlist's own reading, and it decays (goes negative) moving
down-cap, which is the OPPOSITE of the structural down-cap thesis this triage
existed to test.** The frozen bar demanded at least one costable bucket match
the watchlist; none came close (best bucket = 0.18× Arm W `[DERIVED —
0.013026 / 0.071816]`).

## 2. Arm-W positive control (U3) — PASSED before Arm A was computed

- Control statistic (reference instrument's units, per-date CS-sigma):
  **+0.68298 σ** ≥ frozen floor +0.08013 (= committed reference
  +0.24038 / 3). The run proceeded; a failure here would have VOIDed the run
  with no Arm A computation.
- Telemetry: the control read 2.84× the reference `[DERIVED — 0.68298 /
  0.24038]`, under the 3× telemetry line. Direction expected and declared in
  the frozen U3 rationale: the served pin (trained 2026-08-02) is in-sample on
  most of this corpus, so INFLATION is not a failure mode the control polices
  — only collapse or sign-flip is, and neither occurred.
- Control detail: Δ(genuine−placebo) +0.43704 σ, block-t 7.91, 19/19 blocks
  positive, 232/232 cross-sections kept.

The instrument therefore reproduces the capacity-memo tail-spread phenomenon
on the watchlist through this harness — Arm A's weaker reading is a property
of the extension universe, not of a broken harness.

## 3. The transfer prediction — per-ADV-bucket table (h=60, the decision table)

Arm W benchmark (gross, uncosted mega-cap): Δspread = **+0.071816**
(block-t 6.52, 18/19 blocks positive, mean genuine IC +0.111).

Arm A per costable bucket (deciles re-selected WITHIN bucket; DGTW cells
arm-level; gross vs W per the frozen bar, net shown for bar-1 context):

| ADV bucket | RT cost | mean names/date | n_kept obs | blocks | gross Δ | net Δ | block-t (gross) | pos blocks | vs Arm W +0.0718 |
|---|---|---|---|---|---|---|---|---|---|
| ≥$25M | 25 bps | 535.7 | 232 | 19/19 | **+0.013026** | **+0.006959** | +1.489 | 63.2% | 0.18× — FAIL |
| $10–25M | 40 bps | 10.0 (floor) | 201 | 17/19 | **−0.021718** | −0.040822 | −1.465 | 35.3% | negative — FAIL |
| $5–10M | 60 bps | — | **0** | — | NO DATA (10-name/date floor never met) | — | — | — | untestable — FAIL |

Notes, reported not papered over:
- Arm A pooled = the ≥$25M bucket to first order (535.7 of ~572 shared names
  per date `[DERIVED — mean_names vs median n_pairs_shared 609 incl. below-floor
  names]`); the arm-level PASS on bars 1–3 is carried by the most
  institutional slice of the extension.
- The $10–25M bucket sat exactly at its 10-name floor on every kept date and
  is thin by construction — its negative read is annotation-grade, but its
  SIGN is the wrong direction for the down-cap thesis.
- The $5–10M bucket never reached 10 Arm-A names on any shared cross-section
  (609 names, ADV measured at the snapshot edge), so bar 4 was effectively
  testable on two buckets. This is the frozen construction behaving as
  designed, recorded by the runner itself.
- EVIDENCE-BOUNDARY caveat on bar 4 (declared before the run in the U3
  rationale, restated here as an interpretive boundary, NOT a relitigation):
  Arm W's +0.0718 is an in-training-ticker reading (the pin trained on the
  292-name panel containing the watchlist, window overlapping this corpus)
  while Arm A names were never in training. The frozen bar compares them
  anyway — a conservative bar for the extension. A Stage-2 case, if ever
  re-pitched, must address this asymmetry with an out-of-sample-in-time
  design; on THIS bar, as frozen, the answer is FAIL.

## 4. h=20 secondary (reported, never decisive)

| arm | gross Δ | net Δ | block-t | pos blocks (58) |
|---|---|---|---|---|
| A | +0.001367 | −0.000725 | +0.828 | 53.4% |
| W | +0.001861 | (uncosted) | +0.577 | 53.4% |

The tail-spread phenomenon is an h=60 structure in BOTH arms — at h=20 even
the watchlist reads near-zero (+0.0019, t=0.58). The h=60 primary was the
right frozen choice; h=20 adds no contradicting signal, and Arm A's net at
h=20 is negative (turnover cost at 20d dominates a 4× smaller gross).

## 5. Arm B — exploratory coverage map (FENCED: labeled variant, never pooled, can neither pass nor fail anything)

Arm B (1,955 names, alpha158-only, 14 recipe features absent → serve
transform's fillna(0.0) — the spec's own NaN-variant) maps where coverage
spend would matter IF the thesis ever re-opens. h=60, per bucket:

| ADV bucket | gross Δ | net Δ | block-t | mean names | note |
|---|---|---|---|---|---|
| ≥$25M | −0.010122 | −0.019490 | −1.526 | 1,026.6 | negative |
| $10–25M | +0.008586 | −0.006594 | +0.393 | 352.0 | gross-positive, dies net |
| $5–10M | −0.006205 | −0.031599 | −0.376 | 212.9 | negative |
| $1–5M | −0.016532 | UNCOSTABLE | −1.447 | 283.9 | exploratory only, never a verdict input |

Pooled h=60: −0.008706 (block-t −1.32); h=20 pooled −0.000515 (t −0.16).

Reading, with the fence intact: stripped of the 14 fundamental/PEAD/SUE/
sentiment features, the pin has NO positive net edge anywhere in the
extension — including the ≥$25M bucket where the full-recipe Arm A was
positive. The full recipe is load-bearing for the transfer that does exist
(Arm A ≥$25M +0.0130 gross vs Arm B ≥$25M −0.0101 gross on overlapping
names `[DERIVED — cross-arm contrast, exploratory]`). Coverage spend for a
hypothetical future stage would have to buy FUNDAMENTALS down-cap, not more
tickers.

## 6. Coverage and telemetry

- Zero dropped cross-sections in every arm/horizon (`floor_paired: 0`
  everywhere); 233 kept at h=20, 232 at h=60 (one grid obs edge-trimmed, §7).
- Shared paired cross-sections `[VERIFIED — obs CSV aggregates]`: Arm A
  min/median 128/609 (h=60), Arm W 137/143, Arm B 1,351/1,951. Early-corpus
  minima reflect extension histories ramping into the placebo lag window —
  every complete block still had data (19/19, 58/58).
- DGTW small-cell flags (cells <15 names left unadjusted, per the frozen
  floor): Arm W median 66 of 143 names/date — the watchlist's DGTW adjustment
  is largely vacuous by the spec's own floor (145 names / 27 cells), exactly
  as the frozen header declared. Arm A median 66/609 (~11%), Arm B 44/1,951
  (~2%).
- Whole-cross-section IC (informational): Arm A h=60 genuine +0.0239 vs Arm W
  +0.1113; same ordering as the spread estimand.

## 7. Guard outcomes and deviations (all reported by the run itself)

- **U1–U11 all passed; exit 0; one execution.** U10's marker is now armed by
  the committed outputs (a re-run mechanically refuses). U3 passed before Arm
  A existed. U9 PIT held for all five fundamental columns on both full-recipe
  arms.
- **U1 declared deviation** (frozen in the reviewed header, restated): the
  spec's "served production model pin" is implemented as the served blend's
  PANEL component pin (`artifacts/prod/panel-ltr.alpha158_fund.json`, file
  sha256 `6461b827…`, config_fp `sha256:f8fb2259b2bf1537`, trained
  2026-08-02) — the #987/capacity-memo instrument lineage. The blend's
  momentum leg (genesis 2026-08, no historical coverage) was recorded as
  context, never scored.
- **U4**: the frozen every-5th-trading-day rule yields 233 cross-sections on
  the 1,161-day window vs the spec's derived "~231" — the rule governs, the
  discrepancy is recorded in the results JSON.
- **U6**: exactly one h=60 obs trimmed (grid date 2026-02-13, label endpoint
  2026-05-12 > snapshot edge 2026-05-08 — the discrepancy the runner header
  pre-declared); it lies outside every complete block; h=20 lost nothing.
- **U2**: final arm counts landed EXACT on the feasibility memo's numbers
  (Arm A 609, Arm B 1,955, W 145). The cascade's intermediate stage counts
  (2,787 inventory → 2,643 → 2,324 → 2,188 → 2,075 → 1,667 → 609) differ from
  the memo's staged quotes (different filter order); the guard binds on the
  final counts, all recorded.
- **Runtime deviation**: 782.8 s (~13 min) vs the spec's ~1h corpus-build
  estimate — the alpha158 feature path was much cheaper than the un-memoized
  hurst estimate. No computational shortcut was taken; the per-ticker cache
  lived in the isolated scratch as designed.
- **Execution environment**: isolated worktree of orchestrator main at
  `9d73d546`; scratch redirected via the runner's own `RQ_STAGE1_SCRATCH` env
  contract to a session-isolated directory outside every repo; zero writes to
  `data/`, the umbrella tree, or any live store (U7 enforced every write).
- **Post-run test transition (this PR, declared)**: the runner-PR test
  `test_this_pr_ships_unrun_no_outputs_committed` asserted "no outputs exist"
  — an invariant of the ships-un-run state. Committing the run's outputs
  flips it BY DESIGN; the test now asserts the post-run invariant (U10
  refuses). Runner tests: 32/32 pass. The runner file itself is untouched
  (byte-identical to the executed copy).

## 8. Pins and reproduction

All from the results JSON `pins` block `[VERIFIED]`:

- orchestrator origin/main (runner source + execution base): `9d73d5463b23218bf8bded9ff75f9bbf479a3543`
- runner file sha256: `93877dba751380a3b5a30f83db236821d850759e8d39af13c25d4261e6c7a5a2`
- served artifact: `…/backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json`,
  file sha256 `6461b827ab2339a8d2351db6e45ac4f4c8d4c231937d8d6a4f8d127ecc546d15`,
  config_fp `sha256:f8fb2259b2bf1537`, trained 2026-08-02
- strategy config: `strategy_config.golden.json` sha256 `d93d28c5…4b555` (watchlist n=145)
- `sec_fundamentals_daily.parquet` sha256 `aa5b06e3…f66b`
- repo heads at run time: umbrella `3296d369`, strategy-104 `86a78b41`,
  base-data `f8514066`, pipeline `69bf7116`, common `20d4570a`
- outputs (committed in this PR): `2026-08-18-universe-stage1-results.json`
  sha256 `8a058490710336c1078feb53f2fc2e534b2c4c226b94aacc846371a1cdd3a7c7`,
  `…-obs.csv` sha256 `e64054bc3ead1a9e862490e8f57bc99c7ba888d1267ded3fe92f1696f67ca1cd`
  `[VERIFIED — shasum after the run]`
- python: `/Users/renhao/git/github/RenQuant/.venv` (numpy 2.0.2, pandas
  2.3.3, xgboost 2.1.4) `[VERIFIED — version probe before the run]`

The runner is deterministic (no randomness, no clock in any computed number):
re-executing at these pins reproduces these outputs bit-for-bit — and U10 now
refuses such a re-execution anyway; reproduction would require a fresh
worktree and is NOT a re-run of the triage (the one-shot budget is spent).

## 9. What happens next (per the merged spec — no new decisions here)

- The down-cap universe-extension thesis is **DEPRIORITIZED**: no Stage-2 PIT
  program, no data spend, no retrain, no serving change. Parked with
  evidence, at ~zero cost, exactly as spec §1 defined.
- The recorded positives — out-of-ticker transfer exists in the ≥$25M
  full-recipe band (net +0.70%/60d, t=1.49 triage-grade), and the full recipe
  (not ticker count) is what coverage spend would have to buy — are facts a
  future re-pitch may cite, but a re-pitch requires a NEW frozen spec with an
  out-of-sample-in-time design for the W-vs-A asymmetry (§3 note), and it
  cannot re-run this corpus (U10).
- VERDICTS.md gains this row in the same PR, per the ledger's own rule.
