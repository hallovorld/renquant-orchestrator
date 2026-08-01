# GOAL-3 — R6 re-measured: four surfaces, two pairs, and that says WHERE a guard must look

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-3 (twin registry R6 / condition 3)

## What the registry said, and what is there

R6 records that a drift guard compares `strategy_config.json` against
`strategy_config.golden.json` and *"both name `hf_patchtst` primary, so the guard reports
clean forever"*. Retirement condition 3 says *"three files assert which model is primary
and two of them are wrong"*.

Measured `[本次实测 2026-08-01]` — **four**, splitting **2–2**:

| surface | `ranking.panel_scoring.kind` |
|---|---|
| `renquant-strategy-104/configs/strategy_config.json` — **the runner's**, per R5 | **`xgb`** |
| `renquant-strategy-104/configs/strategy_config.golden.json` | **`xgb`** |
| `RenQuant/backtesting/renquant_104/strategy_config.json` | **`hf_patchtst`** |
| `RenQuant/backtesting/renquant_104/strategy_config.golden.json` | **`hf_patchtst`** |

## The shape matters more than the count

**Each pair agrees internally.** So R6's guard is not comparing a good copy against a bad
one — **it is comparing two members of the same pair**, and any check that stays on one
side of the pinned/umbrella boundary **passes forever by construction**.

That is a stronger and more useful statement than *"both are wrong"*: it says **where** a
guard has to look. `ops/strategy_config_primary_parity.py` (orch#694, merged) already
looks across the boundary and fails on the disagreement.

So condition 3's status is now precise: **detection exists; a single source does not.**
The registry row now records both.

## Tests

6. The **registry text** is asserted — it runs everywhere including CI, because the
document is the deliverable. Then, when the checkouts are present: each **pair agrees
internally** (the load-bearing shape — if they did not, R6's guard would have caught the
divergence and the row would not exist); the **two pairs disagree**; each surface still
declares the kind the registry records, so a surface moving fails here rather than being
quietly inherited; and a **missing** surface **skips rather than passing**, since a machine
with fewer checkouts must not read as agreement.

Suite: **5127 passed, 2 skipped**.

## Not done

This re-measures R6 and sharpens condition 3. It does **not** create the single source —
that is a change to how role assignment is published across repos, and it is the one part
of this row that a measurement cannot supply.
