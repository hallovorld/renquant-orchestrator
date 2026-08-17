# Design: G-I MoE — the (sector × regime) power-gated routing table

STATUS: **design for review (docs only — NO code / config / behavior change).**
DATE: 2026-08-17. Operator-directed ("自己set goal和loop来drive这个moe模型！设计要发pr
被approve之后再开始impl") — implementation starts ONLY after this design is approved.

## 1. Bottom line

The MoE is **a list of models filling a (sector × regime) table** — the operator's
definition, verbatim. Each cell of the 11-sector × 4-regime grid is served by the expert
best suited to it; **cells without the statistical power to choose an expert are
hard-wired to the champion** (today's prod blend). For hard-wired cells the worst case
equals today's system *by construction*; for any tested cell the downside is
probabilistic and bounded by the frozen assignment rule in §5b — Holm FWER ≤ 5% per
batch over the FULL frozen candidate manifest, screen failures included (§5b step 4),
with Stage B as an operational fail-safe (not statistical confirmation) and a demotion
ratchet — not zero (§5b step 9 states the honest guarantee). In-session re-measurement
of the sample geometry (§3, corrected this revision) finds the BULL_VOLATILE column
carries only m = 2 independent blocks at the fwd-60d label horizon under §5b's own
gap-merge rule, so the honest v1 Stage-A expectation is **zero specialist assignments
— the entire grid serves the champion** until an extended corpus or a reviewed
estimand amendment clears the admissibility floor (§3, §10). v1 is still worth
building: it delivers the router machinery, the alias registry, the qualification
pipeline, and the fail-safe rule. v1 is a **static, config-declared router** over models that
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
   Completing the record (reconciled this revision): the later 278-date purged re-run
   of the SAME transfer regression reports **adjusted** t = +3.17 (β̂ = +3115 bps of
   top-3 fwd_20d per 1.0 IC, n = 278, clears the frozen n_eff-adjusted ≥ 2.0
   convention) `[VERIFIED — prior work,
   doc/research/2026-08-08-moe-s10-confirmatory-kill.md, subsidiary finding 1]` — the
   transfer MACHINERY is validated at depth, while the momentum-blend hypothesis it
   measured was killed by that same record. Neither reading changes the bar:
   admission is "walk the kill path", never a t-threshold.

## 3. The grid and its power map

*Per-quantity tags below; the section carries no blanket tag — a hybrid
`[VERIFIED/DERIVED]` header cannot say which of its numbers were measured and which
were computed, which is the ambiguity row 10 exists to remove.*

44 cells = 11 GICS sectors × 4 HMM regimes. Sector map: 304 tickers across exactly 11
distinct sectors `[VERIFIED — python read of data/ticker_sectors.json, 2026-08-17]`.
Regime labels: `kernel/hmm_regime_labels.py` (the stateless approximation of the prod
detector) on SPY daily closes over the frozen corpus span 2019-01-14..2026-03-02 —
the 125-window WF lineage's cutoff range (43 production + 82 extension windows)
`[VERIFIED — prior work, renquant-backtesting
doc/progress/2026-08-02-lineage-stage2-scoring-slice.md]`. The binding per-cell
effective n is the **regime column's count of independent evidence blocks at the
label horizon** — sector breadth adds cross-section, never time-independence.

Measured in-session `[VERIFIED —
kernel.hmm_regime_labels.compute_hmm_regime_labels(data/ohlcv/SPY/1d.parquet),
window 2019-01-14..2026-03-02 (1,792 trading days; SPY parquet starts 2016-01-04, so
no warm-up contamination); day-level maximal same-label runs; blocks = runs merged
when the gap < 60 calendar days, i.e. §5b step 1's rule]`:

| regime column | days | raw episodes | blocks after <60d merge | v1 treatment |
|---|---:|---:|---:|---|
| BULL_VOLATILE | 1,399 | 80 | **2** (split only at the 2020-02-24..2020-05-07 COVID gap) | the only column with material day-count, BUT m = 2 < the m ≥ 10 admissibility floor (§5b step 3) at the fwd-60d estimand ⇒ Stage A resolves to champion on current geometry |
| BEAR | 260 | 53 | 12 | champion default; short episodes whose fwd-60d labels mostly realize OUTSIDE the episode — the wall that killed preregs #975/#976; `bear_exit` enters as the BEAR **policy overlay** (exit/defense), pending G-B — NOT as a per-cell scorer swap |
| CHOPPY | 63 | 28 | 13 | **hard-wired champion** (63 total days) |
| BULL_CALM | 70 | 9 | 6 | **hard-wired champion** (70 total days) |

**Sensitivity — what m = 2 is and is not.** m = 2 is a JOINT property of the frozen
merge rule (gap < label horizon = 60 calendar days) and BULL_VOLATILE's day-occupancy
(1,399/1,792 ≈ 78% `[DERIVED — table above]`): the column's raw episodes are
separated by mostly-short non-BULL_VOLATILE interludes, so a 60-day gap-merge
collapses them. It does NOT say regime-conditional testing is impossible — a
shorter-horizon estimand (e.g. a fwd-20d variant) would merge less and yield a
different m. Any such variant is a NEW frozen batch spec (reviewed before corpus
scores are viewed), not a post-hoc knob.

**≈33 of 44 cells are pre-emptively hard-wired** `[DERIVED — 44 cells − the 11
BULL_VOLATILE cells]`. The frozen hard-wire list is prereg content
(runner-guards-are-prereg-content): no later rule may touch it. The 11 BULL_VOLATILE
cells stay testable IN PRINCIPLE through §5b — but on the current corpus the measured
m = 2 fails the m ≥ 10 admissibility floor, so the realistic v1 outcome — corrected
from an earlier revision's "1–3 BULL_VOLATILE cells get a specialist" — is
**0 specialist assignments; the entire grid serves the champion**, until either (i)
an extended corpus yields enough post-merge blocks or (ii) a reviewed amendment
freezes a shorter-horizon estimand (see Sensitivity above). Either route is a NEW
frozen §5b batch spec, committed before any corpus scores are viewed. Not a defeat:
the v1 deliverables are the router machinery, the alias registry, the qualification
pipeline, and the fail-safe rule itself (§7 AC1–AC4), plus an honestly-measured
power map. (An earlier revision claimed 17/8/5/3 episodes at ~3-week fold
granularity from an uncommitted 2026-08-13 session estimate; it does not reproduce
under the declared labeler at any granularity tried — see §10.)

## 4. Expert roster + alias registry

**Alias registry** = display/strategy name ↔ unchanged serving key; lives in the routing
config; every report/ntfy uses the strategy name.

Existing (6) — already trained, in prod or shadow:
| strategy name | serving identity | tilt | status |
|---|---|---|---|
| `multifactor_core` | panel-ltr.alpha158_fund (rank:pairwise) | price/volume+fundamental composite | prod blend leg 1 |
| `mom_slow_12m` | momentum ledger (12-1 residual, weekly) | slow momentum | prod blend leg 2; transfer at 33 dates t(iid)=+3.17 / t(n_eff-adj)=+0.71 `[VERIFIED — prior work, doc/research/2026-08-08-moe-stage-minus1-results.md:173]`; at 278 purged dates adj t=+3.17 `[VERIFIED — prior work, doc/research/2026-08-08-moe-s10-confirmatory-kill.md]` (§2 item 6) |
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
2. **Cheap IC screen** (over-engineering-validation), run ONLY AFTER the §5b candidate
   manifest is frozen — the screen views corpus scores, so it must not be able to
   shape the multiplicity family: score on the existing WF corpora; a candidate that
   can't show a placebo-clean IC *difference* dies before any prereg cathedral — it
   leaves the roster but stays counted in the §5b step-4 family. Trust differences,
   not absolute IC (embargo-leakage floor ~+0.04 `[VERIFIED — prior work, doc/research/2026-06-28-renquant105-pead-signal.md:62 — shuffled-label floor on overlapping ~60d labels with a ~30d embargo gap]`).
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

**Candidate-manifest freeze (the selection-bias wall; codex review 2026-08-17).**
Before ANY candidate score is computed on the frozen corpus — including the §5 step-2
cheap screen — the batch manifest is committed, listing every candidate name and its
EXACT formula/variant. The step-4 multiplicity family is defined by THAT manifest,
never by who survives screening or qualification: those steps run on this same
corpus, so a family reduced by them would be data-dependent hypothesis selection and
would void the FWER claim. A formula variant tried after the freeze cannot join this
batch — the corpus is burned for it; it waits for the next frozen corpus.

1. **Unit of inference.** One block = one BULL_VOLATILE episode from the frozen corpus
   (the 125-window WF lineage span, 2019-01-14..2026-03-02). Consecutive episodes
   whose gap is < 60 calendar days (the label horizon) merge into ONE block — labels
   that straddle the gap otherwise correlate adjacent blocks (the #975/#976 defect
   class). Effective block count `m` is counted BEFORE any test statistic is
   computed. Counted in-session on current data: 80 raw day-level episodes merge to
   **m = 2** `[VERIFIED — the §3 measurement command]`; see §3's Sensitivity note
   for what that number is a property of. (An earlier revision claimed "17
   episodes" from an uncommitted 2026-08-13 session estimate; it does not reproduce
   under the declared labeler — see §10.)
2. **Estimand + champion comparator.** For sector cell `s` and admitted candidate `c`:
   the block-level mean of daily cross-sectional Spearman rank IC of `c`'s score
   against the fwd-60d label on the cell's names, MINUS the same quantity for the
   champion — paired by (day, name), same panel, same label. The comparator is
   pinned: the prod champion blend at corpus freeze (config hash + pipeline commit
   recorded in the batch manifest).
3. **Coverage minima.** A `(c, s)` hypothesis is admissible iff ≥ 70% of the corpus's
   raw day-level episodes qualify `[DERIVED — the fraction originally frozen as
   "12 of 17" ≈ 70%, re-based off the corrected episode count]` AND post-merge
   `m ≥ 10`, where an episode qualifies iff the cell has ≥ 8 names scored by BOTH
   `c` and the champion on ≥ 60% of its days. Inadmissible ⇒ the cell hard-wires to
   the champion (no-decision). Thresholds `[ASSUMED — design choices frozen here:
   8 names is the minimum cross-section for a stable rank IC on this universe
   (304 tickers / 11 sectors ≈ 28 mean names per sector [DERIVED — 304/11 ≈ 27.6]);
   m ≥ 10 keeps block-t d.f. ≥ 9, off the single-digit-block regime that killed
   preregs #975/#976]`. On the current corpus the measured m = 2 (§3) fails this
   floor for EVERY BULL_VOLATILE cell ⇒ the whole batch resolves to champion. The
   floor is NOT lowered to fit the data — that would be the #975/#976 mistake with
   extra steps.
4. **Test + multiplicity family.** One-sided paired block-t over the `m` blocks;
   critical values from t(m−1), never a hardcoded 1.96. The family = the FULL frozen
   manifest × the 11 cells — EVERY manifest candidate counts, including §5 screen
   failures and pairs with inadmissible coverage (their hypotheses enter at p = 1,
   which only makes Holm stricter).

   **The manifest is enumerated, not described** (codex review 2026-08-17 round 5).
   An earlier revision wrote "for the §4 roster that is 4 × 11 = 44 hypotheses".
   The 4 was the four NOT-YET-BUILT candidates (`high52w`, `lowbeta`, `quality_gp`,
   `tail_q90_20d`) while §4 lists **ten** rows, and the text named "the §4 roster" —
   so the number and the object it claimed to count disagreed, in the direction that
   UNDER-states multiplicity and thereby inflates the FWER claim.

   **The rule, since no single number is defensible from this document alone:** the
   family is `|manifest| × 11 cells`, where the manifest enumerates every
   **assignment-eligible** candidate — i.e. anything that could be routed into a
   BULL_VOLATILE cell — not merely the ones newly built for this batch. Applying that
   to §4's ten rows: `multifactor_core` is excluded because it is the pinned CHAMPION
   COMPARATOR, not a candidate (a hypothesis of the champion against itself is not
   defined); `bear_exit` is excluded while it remains a policy-grade overlay that is
   "not yet a trade" per §4 and so cannot be assigned to a cell. The remaining eight
   — including the already-shadowed `mom_fast`, `mom_panel_60d` and `topdecile_60d`,
   which are assignment-eligible and corpus-exposed — are in. **The batch manifest
   restates that list verbatim with each exclusion and its reason, and `|manifest|` is
   read from that file; this document deliberately does not freeze a count**, because
   roster membership changes between batches and a number frozen in prose here would
   go stale exactly the way the "4" did.

   **Prior corpus exposure counts too — or the corpus is burned for that candidate.**
   The freeze above only bars variants tried AFTER it. That is insufficient on its
   own: several roster members were already scored on this same WF lineage in earlier
   work (`mom_panel_60d` is annotated "shadow (passed WF)" in §4; `topdecile_60d`,
   `bear_exit` and `high52w` likewise arrive from prior lines). Those earlier looks
   consumed the same corpus, so a family covering only this batch's fresh scores
   still understates multiplicity. **Rule: a candidate that has previously been
   scored on this corpus either (a) enters this family carrying its prior looks —
   one hypothesis per prior (candidate, variant) exposure, enumerated in the
   manifest — or (b) is declared corpus-burned and CANNOT be admitted to a cell on
   this corpus at all; it waits for the next frozen one.** Which of (a)/(b) applies
   to each roster member is recorded in the manifest at freeze, before any score.

   This enlargement cannot rescue a result: on the current corpus §5b step 3 already
   resolves every cell to the champion at m = 2, so a larger family changes no
   decision here. It is stated because the FWER claim must be true when the corpus
   is eventually large enough for a decision to turn on it. Defining the family by the manifest rather
   than by post-screen survivors is what makes the FWER claim valid: screening and
   qualification run on this same corpus, so a family reduced by them would
   understate multiplicity (codex review 2026-08-17). Holm–Bonferroni over that enumerated family at
   family-wise α = 0.05 `[ASSUMED — FWER rather than FDR because a false specialist
   serves real money; 0.05 is the repo's standing gate α]`. Only survivors reach
   step 5.
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
7. **Stage separation + the operational promotion gate.** Stage A (steps 1–6) yields
   a PROVISIONAL assignment from the frozen corpus. Stage B is the actual promotion
   gate — no specialist serves a live cell without it — but it is an **operational
   fail-safe, NOT statistical confirmation**: ~40 trading days is a single-episode
   sign check with no meaningful power, and it must NOT be read as strengthening
   the step-4 FWER number (codex review 2026-08-17). Criterion, frozen here before
   any Stage-A result exists: the provisional router runs in the MoE shadow lane
   (AC4) until ≥ 40 trading days classify BULL_VOLATILE `[ASSUMED — spans ≥ 1 fresh
   episode at the measured mean episode length of ≈17 trading days [DERIVED — 1,399
   days / 80 episodes, §3] without stalling rollout]`; the specialist confirms iff
   its cumulative net per-cell replay attribution (existing cost model) ≥ the
   champion's on the same cell-days. Fail or ambiguous ⇒ demote to champion. Stage B
   cannot resurrect a Stage-A loser and cannot re-litigate Stage-A numbers —
   evidence collected after assignment cannot have been selected on.
8. **Fallback ratchet.** Post-confirmation, at every BULL_VOLATILE episode close: a
   specialist whose cumulative net cell attribution trails the champion's demotes to
   champion, one-way. Re-admission requires a NEW Stage-A batch on an extended
   corpus.
9. **Honest downside guarantee (corrects the claim made by an earlier revision of §1).**
   "Worst case = today by construction" holds ONLY for the ≈33 hard-wired cells
   (byte-identical serving). For tested cells the guarantee is probabilistic,
   bounded, and rests ENTIRELY on Stage A: under the null of no true specialist,
   P(any false specialist provisionally assigned) ≤ 5% per batch `[DERIVED — Holm at
   α = 0.05 over the step-4 family; valid BECAUSE the family is the full frozen
   manifest, not the post-screen survivors, and conditional on the manifest freeze
   preceding all corpus scoring]`. Stage B (step 7) and the ratchet (step 8) do NOT
   tighten that probability — they are operational fail-safes that bound a false
   positive's EXPOSURE to the shadow window plus at most one episode of live
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
  the §5b Stage-B fail-safe surface.
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
(2) §5b candidate-manifest freeze (names + exact formulas, committed BEFORE any
corpus scoring) → (3) cheap IC screen, kill/advance verdicts recorded (kills leave
the roster, never the step-4 family) → (4) router config schema + hard-wire list +
alias registry → (5) §5b Stage-A assignment batch (one run per corpus; expected
all-champion on current geometry, §3) → (6) MoE shadow lane (§5b Stage-B fail-safe)
→ (7) AC4 replay attribution → operator-gated deploys throughout. Design-review
fixes on THIS doc are personal (not delegated).

## 10. Corrections (2026-08-17, this revision — visible per LONG ledger row 10)

0. *(prior commit 63aed761, same day)* the `t≈3.17` sourcing correction is recorded
   in-place in §2 item 6; this revision adds the 278-date s10 adjusted figure there
   to complete that record.
1. **Episode counts replaced.** The earlier "BULL_VOLATILE 17 / BEAR 8 / CHOPPY 5 /
   BULL_CALM 3 episodes (~3-week fold granularity)" came from an uncommitted
   2026-08-13 session estimate and does NOT reproduce under this doc's own declared
   method. In-session re-measurement (§3, exact command in the tag): days
   1,399 / 260 / 63 / 70; raw day-level episodes 80 / 53 / 28 / 9; blocks after the
   §5b <60-calendar-day gap-merge 2 / 12 / 13 / 6. Every downstream figure is
   reconciled (§1, §3 table, §5b steps 1/3/7). The m = 2 result is
   rule-and-occupancy joint, not a data-only fact — §3's Sensitivity note scopes it.
2. **Realistic v1 outcome revised** from "1–3 BULL_VOLATILE cells get a specialist"
   to "0 — the Stage-A batch is expected to resolve all-champion on current corpus
   geometry" (m = 2 < 10, §5b step 3). The admissibility floor is NOT lowered to
   rescue the outcome.
3. **Multiplicity family redefined** (codex review 2026-08-17, design (a)): the Holm
   family is the FULL frozen candidate manifest × 11 cells, screen failures
   included, with the manifest committed before any corpus scores are viewed.
   Previously the family was only post-screen admitted candidates — data-dependent
   hypothesis selection that voided the 5% FWER claim.
4. **Stage B demoted** from "prospective confirmation" to "operational fail-safe
   promotion gate with no statistical weight"; the ≤5% claim now rests on Stage A
   alone (§5b steps 7/9).
