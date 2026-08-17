# Design: G-I MoE — the (sector × regime) power-gated routing table

STATUS: **design for review (docs only — NO code / config / behavior change).**
DATE: 2026-08-17. Operator-directed ("自己set goal和loop来drive这个moe模型！设计要发pr
被approve之后再开始impl") — implementation starts ONLY after this design is approved.

## 1. Bottom line

The MoE is **a list of models filling a (sector × regime) table** — the operator's
definition, verbatim. Each cell of the 11-sector × 4-regime grid is served by the expert
best suited to it; **cells without the statistical power to choose an expert are
hard-wired to the champion** (today's prod blend). For hard-wired cells the worst case
equals today's system *by construction*; for the few tested cells the downside is
probabilistic and bounded by the frozen assignment rule in §5b — FWER ≤ 5% per batch,
prospective confirmation, and a demotion ratchet — not zero (§5b step 9 states the
honest guarantee). v1 is a **static, config-declared router** over models that
already exist or are derivable at ~zero marginal cost — **zero new data sources, zero new
training architecture** (operator constraint). Weighting is deferred (AC5); learned/
dispersion-gated routing ("living MoE") is a later stage.

## 2. Locked decisions (operator, 2026-08-13 .. 08-17)

1. Keep the blend prod (08-13); MoE evolves it, never reverts it.
2. MoE = model-list → (sector × regime) table, power-gated (08-07, restated 08-13).
3. **No new data pipelines / no new training architectures** — candidate experts must
   reuse the existing panel + the existing ledger-emitter pattern (08-17: "成本太大").
4. Fast and slow momentum are **separate experts** (08-17).
5. **Strategy-facing names, not algorithm names** (08-17: "xgb 不能告诉我偏向哪种策略")
   — an alias registry; serving keys unchanged (renaming live artifacts/config keys is a
   run-surface change with no upside).
6. New-expert quality bar = the momentum bar: momentum is trusted because it is a simple
   sort (not a learner), long-documented in the academic literature
   `[ASSUMED — literature consensus; no in-repo measurement backs the duration claim]`,
   and **survived our own kill machine**. Candidates must walk the same path.

   **The transfer statistic, corrected.** An earlier revision cited GOAL-8 transfer
   `t≈3.17` here as the strength of that survival. Sourcing it showed that is the **iid**
   figure and the dependence-adjusted one is far weaker:
   `t(iid) = +3.17`, `t(n_eff-adjusted) = +0.71`
   `[VERIFIED — prior work, doc/research/2026-08-08-moe-stage-minus1-results.md:173]`.
   Quoting 3.17 as the bar would have overstated the evidence by citing the number that
   ignores the very dependence this repo has been bitten by. **The bar is therefore
   "walked the same kill path", not "cleared t≈3.17"** — the adjusted statistic does not
   support a t-threshold, and no MoE admission decision here rests on one.

## 3. The grid and its power map

*Per-quantity tags below; the section carries no blanket tag — a hybrid
`[VERIFIED/DERIVED]` header cannot say which of its numbers were measured and which
were computed, which is the ambiguity row 10 exists to remove.*

44 cells = 11 GICS sectors (`data/ticker_sectors.json`, 304 tickers) × 4 HMM regimes
(`kernel/hmm_regime_labels.py` on SPY over the 125-fold WF set, 2019-01-14..2026-03-02).
The binding per-cell effective n is the **regime's independent episode count** — sector
breadth adds cross-section, never time-independence:

| regime column | episodes | v1 treatment |
|---|---:|---|
| BULL_VOLATILE | 17 | **the ONLY candidate-testable column** (11 cells); specialists assigned ONLY through the frozen §5b decision rule |
| BEAR | 8 | champion default; challenger only on a huge frozen-gate effect (this wall killed preregs #975/#976); `bear_exit` enters as the BEAR **policy overlay** (exit/defense), pending G-B — NOT as a per-cell scorer swap |
| CHOPPY | 5 | **hard-wired champion** |
| BULL_CALM | 3 | **hard-wired champion** |

**≈33 of 44 cells are pre-emptively hard-wired.** The frozen hard-wire list is prereg
content (runner-guards-are-prereg-content): no later rule may touch it. Realistic v1
outcome: **1–3 BULL_VOLATILE cells** get a specialist; everything else serves the
champion. That is the honest scope, not a defeat; downside on tested cells is bounded
per §5b step 9, and everywhere else equals today's system by construction.
Episode-granularity caveat: episodes counted at ~3-week fold granularity
(order-of-magnitude, not exact); the hopeless-column conclusion is robust to this.

## 4. Expert roster + alias registry

**Alias registry** = display/strategy name ↔ unchanged serving key; lives in the routing
config; every report/ntfy uses the strategy name.

Existing (6) — already trained, in prod or shadow:
| strategy name | serving identity | tilt | status |
|---|---|---|---|
| `multifactor_core` | panel-ltr.alpha158_fund (rank:pairwise) | price/volume+fundamental composite | prod blend leg 1 |
| `mom_slow_12m` | momentum ledger (12-1 residual, weekly) | slow momentum | prod blend leg 2; transfer t(iid)=+3.17 / t(n_eff-adj)=+0.71 `[VERIFIED — prior work, doc/research/2026-08-08-moe-stage-minus1-results.md:173]` |
| `mom_fast` | momentum_fast ledger | fast momentum | shadow |
| `mom_panel_60d` | xgb_mom_60d | momentum-factor panel learner | shadow (passed WF) |
| `topdecile_60d` | panel-clf.top-decile.fwd60 | top-decile classifier | shadow |
| `bear_exit` | G-B exit line (prereg orch#917) | BEAR exit/defense overlay | policy-grade, not yet a trade |

Candidates (4) — momentum-grade, **zero new data / zero new architecture**:
| strategy name | mechanism | build path | why momentum-grade |
|---|---|---|---|
| `high52w` | 52-week-high proximity (George–Hwang) | **clone the momentum ledger emitter**, swap the formula; existing OHLCV | momentum's closest sibling; simple sort, anchoring mechanism; cross-sectional (the killed thing was single-name time-series trend) |
| `lowbeta` | betting-against-beta (Frazzini–Pedersen) | same emitter clone; rolling beta on existing prices | most robust non-momentum price factor; **negatively correlated with momentum in crashes** — best MoE diversity |
| `quality_gp` | gross profitability (Novy-Marx) | same emitter clone; fundamental columns already in panel | most robust single fundamental factor `[ASSUMED — literature consensus (Novy-Marx); no in-repo measurement ranks it against alternatives]`; near-zero turnover, so cost is expected to be immaterial at our size `[ASSUMED — not measured here; the cheap IC screen in §5 is where cost must actually be charged]` |
| `tail_q90_20d` | quantile-regression (q90) on the existing panel | one retrain recipe on the existing panel pipeline | targets a tail-driven top-decile skill shape `[ASSUMED — the DGTW t=2.92 figure appears only in doc/memory/mid-term/model-edge.md, with no research artifact behind it; it is NOT a re-measured or reproducible result and must not be read as one]`; the current rank objective is hypothesised to dilute it |

**Kill list stays killed** (no re-entry without new evidence): time-series trend
(five canonical price-trend factors showed no robust unconditional edge
`[VERIFIED — prior work, doc/design/2026-06-28-renquant105-alpha-discovery.md:69]`), intraday open→close alpha (negative net), crypto, fundamental
momentum (tested, REJECTED), PatchTST (retired 08-02), short-term reversal (turnover >
our cost capacity — declared, not tested).

## 5. Candidate qualification — momentum's exact path, plus an information gate

Every candidate walks GOAL-7's validated pipeline; no shortcuts, no bespoke harness:
1. **Standalone emitter** (weekly, append-only hash-chained ledger — the momentum
   emitter pattern; new formula, same mechanics, same scorer-identity monitoring).
2. **Cheap IC screen first** (over-engineering-validation): score on the existing WF
   corpora; a candidate that can't show a placebo-clean IC *difference* dies before any
   prereg cathedral. Trust differences, not absolute IC (embargo-leakage floor ~+0.04 `[VERIFIED — prior work, doc/research/2026-06-28-renquant105-pead-signal.md:62 — shuffled-label floor on overlapping ~60d labels with a ~30d embargo gap]`).
3. **Prereg + WF gate** for survivors — frozen before the run; episode-block inference
   (block ≥ horizon; block-t critical values, never hardcoded 1.96 on single-digit
   blocks); effective sample counted BEFORE the decision rule (the #975/#976 lesson).
4. **Incremental-information gate**: admitted to the roster only if score correlation
   with `multifactor_core` AND with each already-admitted expert is |ρ| < 0.7
   `[ASSUMED — a design choice, not a measured threshold: it bounds re-skinned duplicates;
   no in-repo measurement selects 0.7 over a neighbouring value]`, or it
   shows incremental IC — no re-skinned duplicates.
5. **Shadow ledger** rides in the daily-full (a shadow lane) before any cell assignment.

## 5b. Preregistered cell-assignment decision rule (FROZEN — prereg content)

Codex review (2026-08-17) correctly found that §5 qualifies *experts* but never froze
the rule mapping an admitted expert into a BULL_VOLATILE cell, leaving implementation
enough freedom to pick specialists after seeing results. This section closes that gap.
It is prereg content: implementation parameterizes nothing here, and the hypothesis
family below is tested **once per frozen corpus** — re-running the batch on the same
corpus is forbidden.

1. **Unit of inference.** One block = one BULL_VOLATILE episode from the frozen corpus
   (125-fold WF set, 2019-01-14..2026-03-02; 17 episodes). Consecutive episodes whose
   gap is < 60 calendar days (the label horizon) merge into ONE block — labels that
   straddle the gap otherwise correlate adjacent blocks (the #975/#976 defect class).
   Effective block count `m` is counted BEFORE any test statistic is computed.
2. **Estimand + champion comparator.** For sector cell `s` and admitted candidate `c`:
   the block-level mean of daily cross-sectional Spearman rank IC of `c`'s score
   against the fwd-60d label on the cell's names, MINUS the same quantity for the
   champion — paired by (day, name), same panel, same label. The comparator is
   pinned: the prod champion blend at corpus freeze (config hash + pipeline commit
   recorded in the batch manifest).
3. **Coverage minima.** A `(c, s)` hypothesis is admissible iff ≥ 12 of the 17
   episodes qualify AND post-merge `m ≥ 10`, where an episode qualifies iff the cell
   has ≥ 8 names scored by BOTH `c` and the champion on ≥ 60% of its days.
   Inadmissible ⇒ the cell hard-wires to the champion (no-decision). Thresholds
   [ASSUMED — design choices frozen here: 8 names is the minimum cross-section for a
   stable rank IC on this universe (304 tickers / 11 sectors ≈ 28 median names per
   sector); `m ≥ 10` keeps block-t d.f. ≥ 9, off the single-digit-block regime that
   killed preregs #975/#976].
4. **Test + multiplicity family.** One-sided paired block-t over the `m` blocks;
   critical values from t(m−1), never a hardcoded 1.96. The family = ALL admissible
   `(c, s)` pairs in the batch (up to 4 candidates × 11 cells = 44 hypotheses);
   Holm–Bonferroni at family-wise α = 0.05 [ASSUMED — FWER rather than FDR because a
   false specialist serves real money; 0.05 is the repo's standing gate α]. Only
   survivors reach step 5.
5. **Minimum economically meaningful improvement.** A surviving `(c, s)` must also
   show pooled episode-weighted ΔIC ≥ +0.02 [ASSUMED — half the ~+0.04
   embargo-leakage floor §5 step 2 already uses: an improvement smaller than half a
   known measurement artifact is not economically credible]. Net-of-costs is enforced
   at Stage B (step 7), where the replay cost model exists; Stage-A candidates are
   low-turnover by roster construction (§4).
6. **Tie / no-decision.** In a cell with ≥ 2 survivors, the largest pooled ΔIC wins
   ONLY if it exceeds the runner-up by ≥ 1 paired SE of their difference; otherwise
   no-decision. EVERY failure mode — inadmissible, non-significant, sub-threshold,
   tie, missing data, ambiguity of any kind — resolves to the champion. There is no
   discretionary branch.
7. **Selection-bias separation (two stages).** Stage A (steps 1–6) yields a
   PROVISIONAL assignment from the frozen corpus. Stage B is prospective
   confirmation with its criterion frozen here, before any Stage-A result exists:
   the provisional router runs in the MoE shadow lane (AC4) until ≥ 40 trading days
   classify BULL_VOLATILE [ASSUMED — spans ≥ 1 fresh episode at observed episode
   lengths without stalling rollout]; the specialist confirms iff its cumulative net
   per-cell replay attribution (existing cost model) ≥ the champion's on the same
   cell-days. Fail or ambiguous ⇒ demote to champion. Stage B cannot resurrect a
   Stage-A loser and cannot re-litigate Stage-A numbers — evidence collected after
   assignment cannot have been selected on.
8. **Fallback ratchet.** Post-confirmation, at every BULL_VOLATILE episode close: a
   specialist whose cumulative net cell attribution trails the champion's demotes to
   champion, one-way. Re-admission requires a NEW Stage-A batch on an extended
   corpus.
9. **Honest downside guarantee (corrects the claim made by an earlier revision of §1).**
   "Worst case = today by construction" holds ONLY for the ≈33 hard-wired cells
   (byte-identical serving). For tested cells the guarantee is probabilistic and
   bounded: under the null of no true specialist, P(any false specialist
   provisionally assigned) ≤ 5% per batch (step 4); a false positive must still pass
   Stage B (step 7) and remains subject to the episode-close ratchet (step 8),
   bounding its exposure to the shadow window plus at most one episode of live
   underperformance in its single cell. Selected-cell downside is bounded and
   temporary — NOT zero.

## 6. Serving mechanics — composition machinery that already exists

- The prod blend is already an inference-only composition (`blend` kind); a
  **`regime_router` kind is already registered** in the pipeline model registry
  (inference-only; components trained separately). v1 MoE serving = a config-declared
  router whose cells map to component lists, composed per cell as the **same unweighted
  z-sum** the blend uses today (weighting = AC5, deferred).
- Regime at serve time: the existing regime machinery (`regime.gmm_artifact` / HMM
  labels). Sector: `ticker_sectors.json` (+ `sector_etf_map` already in config).
- Hard-wired cells: their component list IS the champion blend — byte-identical
  behavior to today for ≈33/44 cells, by construction.
- Implementation homes (impl phase, after approval) — **finalized against
  RENQUANT_REPOS.md, not assumed**: candidate emitters live in the MODEL FACTORY
  (`renquant-model`), beside the existing momentum emitter package
  `renquant_model_momentum` (`src/renquant_model_momentum/{train,ledger}.py`
  [VERIFIED — read 2026-08-17]) whose pattern they clone; an earlier revision said
  "the umbrella ops pattern", which was wrong — the repo map forbids new code in the
  umbrella. Ledger artifacts publish through the existing artifact path the serving
  side already reads; router composition in renquant-pipeline (the registry owner);
  orchestration/lane wiring here (renquant-orchestrator).

## 7. Rollout + acceptance criteria (measurable; merged ≠ delivered)

- **AC1** Frozen routing-table schema + the 33-cell hard-wire list + the §5b decision
  rule committed as prereg content; champion fallback proven byte-identical on
  hard-wired cells (test).
- **AC2** Alias registry committed; every operator-facing surface (reports, ntfy) uses
  strategy names; zero serving-key renames.
- **AC3** ≥1 candidate expert qualified END-TO-END through §5 (emitter live in shadow
  ledger + prereg verdict recorded) — regardless of pass/kill outcome; the pipeline
  itself is the deliverable.
- **AC4** MoE shadow lane live in the daily-full producing per-cell-routed scores, with
  replay attribution (which expert served which cell on which day) — this lane is also
  the §5b Stage-B confirmation surface.
- **AC5** (deferred, explicit non-goal of v1) per-component weights.
- **AC6** Promotion to prod: operator-gated, only after shadow evidence; the blend-level
  WF-gating gap (#982 deferred item) applies to the MoE composition identically and is
  NOT silently waived.

## 8. What this does NOT do (honesty ledger)

- Does NOT restore bull buying by itself — the no-bull-edge finding (P-WF-GATE refusal)
  is independent of routing; MoE's paths to helping are `tail_q90_20d`/`lowbeta`-class
  experts earning admission, not the router.
- Does NOT introduce any new data source, vendor, or training architecture.
- Does NOT learn the routing (v1 static; dispersion-gated "living MoE" ≈ Nov C-clock).
- Does NOT resolve G-B (BEAR policy) — `bear_exit` remains policy-gated there.
- Does NOT weight components (AC5 deferred) and does NOT gate the served z-sum at the
  WF level (deferred per #982's honesty ledger).

## 9. Plan

This design PR → codex approve → **impl phase** (each step its own codex-gated PR):
(1) emitter clones (`high52w`, `lowbeta`, `quality_gp`) + `tail_q90_20d` recipe →
(2) cheap IC screen, kill/advance verdicts recorded → (3) router config schema +
hard-wire list + alias registry → (4) §5b Stage-A assignment batch (frozen manifest,
one run per corpus) → (5) MoE shadow lane (§5b Stage-B confirmation) → (6) AC4 replay
attribution → operator-gated deploys throughout. Design-review fixes on THIS doc are
personal (not delegated).
