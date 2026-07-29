# MODEL CAPABILITY (GOAL-6) — resolution before architecture

> Tier: **MID.** Opened 2026-07-28 and **CONFIRMED the same day** — the
> operator directed it into existence ("根据这个情况该怎样构建试验来获得能力更强
> 的模型？发pr讨论设计，然后实现！这是新的goal！你来drive！") and then confirmed
> the recommendation ("按你的推荐推进试试"). This file is therefore the
> POST-decision record of a confirmed workstream, not a pending proposal.
> What remains open is narrower and listed under OPEN DECISIONS below —
> confirming a direction is not the same as answering every parameter.
> Design: `../../research/2026-07-28-goal6-model-capability-design.md`.
> Sibling: `model-edge.md` (does a given model have edge) ·
> `serving-reliability.md` (does a model's opinion reach the order path).
> This one owns: **can we RESOLVE whether a model has edge, and does the
> experimental setup let capability show up at all?**

GOAL:     move the recurring "underpowered" verdict to a decidable one, by
          fixing the measurement and buying the breadth we already own —
          then, and only then, spend on capacity/architecture.

HEADLINE: today's apparatus can only detect per-date IC >= **0.053-0.069** (two
          measured variance estimates) at 80% power, while plausible equity
          cross-sectional IC is 0.02-0.04 and the production admission bar is
          0.01 — a real model is statistically INVISIBLE to us. Breadth alone
          (142 -> 830 names) takes the MDE to 0.041-0.060; a 20d measurement
          horizon does NOT add further power — measured: the effect shrinks
          proportionately to the extra independent blocks, so the power ratio
          is flat (Stage 0, H2 NOT SUPPORTED; design doc §11 corrections).

WHY:      three measured facts, 2026-07-28 `[VERIFIED — direct reads]`:
          (1) 60d labels over 142 names = ~43 independent windows / 10.3y;
              fresh PatchTST IC +0.0430, naive t +5.39, block-adjusted
              t **+0.70** — 0.02-0.04 true IC is unresolvable here;
          (2) tail spread t=2.92 vs full-cross-section IC t=1.15 on the same
              panel — the ruler discards the skill we have;
          (3) training panel 142 tickers, fund panel 292, SEC fundamentals
              coverage **830** — we train on 17% of the cross-section we own.

STAGES:   0 re-baseline the ruler (free) → 1 build the 830-name PIT panel
          with a stamped freshness contract (achievable frontier, not raw
          calendar age — the RenQuant#541 lesson) → 2 retrain the CERTIFIED
          top-decile recipe on breadth through the same frozen chain → 3
          capacity/ensembling, only once 0-2 make results interpretable.

AC:       AC1 Stage-0 report (free-power multiplier per statistic × horizon,
          placebo-matched) · AC2 830-name PIT panel + machine-readable
          freshness contract + 142-name reproduction gate · AC3 breadth
          retrain clears its frozen comparison prereg (or the failure is
          reported with equal prominence) · AC4 tail statistic wired as a
          gate CO-PRIMARY in renquant-pipeline · AC5 nothing reaches
          production outside the standard chain.

BOUNDARY: base-data owns the panel builder; model owns recipes + the
          evaluation-statistics module; pipeline owns gates and the frontier
          rule; orchestrator owns sequencing and the prereg registry and
          holds NO panel/model internals; umbrella holds pins (+ fork
          mirrors until the fork is retired).

NOT IN:   hourly/intraday data (measured net-negative at this horizon:
          σ_oc ≈ 152bp, net edge −6.4bp at IC 0.03), new vendor spend, any
          live buy-path change, and PatchTST's own verdict (model#85).

NEXT:     operator confirms the staging; then Stage 0 runs under its own
          frozen prereg. Stage 1 is the first one that writes an artifact.
