# GOAL-6 — I withdrew a correct goal anchor using a measurement of a different lane

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-6 (model capability) / clf shadow lane

## What I got wrong

The GOAL-6 lane list carries this anchor:

> *clf WF 语料补齐（Stage 0 暴露的覆盖缺口：**认证过的配方没有样本外语料**）*

Earlier this session I reported that anchor as **stale**, on the grounds that the
certified recipe *does* have an out-of-sample corpus — **43 folds / 178,191 rows / 625
OOS dates / 292 tickers**, leakage contract enforced in code.

Those numbers are real. **They belong to a different lane.** They are
`walkforward_gbdt_prod_recipe_v2` — the GBDT production recipe. The anchor is about
**clf**. I measured one lane's corpus and used it to retire an anchor about another.

This is the shape already on the register as *"withdrawing one instrument, reaching for
another"*: the retraction was delivered honestly and the **substitute** carried the same
error in new words. Here it is worse than a substitution — the original anchor was
**correct**, and my correction removed a true premise from the work queue.

## The measurement, this time on the lane in question

`[本次实测 2026-07-31]`, direct inspection plus `ops/renquant104/gate_stamp_parity.py`
(merged in #687):

**1. Walk-forward corpora that exist at all**

| corpus directory | dated folds | span |
|---|---:|---|
| `walkforward_gbdt_prod_recipe_v2` | **43** | 2023-10-02 … 2026-03-02 |
| `walkforward_patchtst` | **1** | 2026-04-27 |
| `walkforward_b4_fwd20d` | **1** | 2024-02-01 |
| *any* `walkforward_*clf*` | **0 — the directory does not exist** | — |

**2. Gate stamps, by artifact directory**

| directory | artifacts | carrying a WF-gate stamp | **carrying none** |
|---|---:|---:|---:|
| `shadow/` | 9 | **0** | **9** |
| `prod/` | 76 | 30 | 46 |

**3. The clf artifact itself** — `shadow/panel-clf.top-decile.fwd60.json`:

```
has metadata.wf_gate_metadata (canonical) : False
has legacy top-level wf_gate_metadata     : False
                                            *** NO GATE BLOCK AT ALL ***
effective_train_cutoff_date               : 2026-04-28
```

## What this supports — stated narrowly

**The clf lane has no walk-forward evidence of its own.** No corpus directory, and no
gate verdict on its artifact. The anchor was right.

**What it does NOT mean.** "No gate stamp" is not "failed the gate" and not "no
out-of-sample evaluation of any kind". A shadow lane does not admit capital, so it is not
obviously *supposed* to carry a capital-gate verdict — that 9/9 of `shadow/` is unstamped
is consistent with shadows being outside the gate by design, not with nine silent
failures. This document does not claim otherwise, and deciding whether shadow lanes
*should* be gated is a design question that is not settled here.

**The consequence for GOAL-6 Stage 2 is the part that matters.** Stage 2 wants a
width-retrain judged on evidence. On the clf lane there is currently nothing to judge it
against: no fold series, no per-fold economics, no gate verdict. So Stage 2 on clf is
blocked on corpus construction, exactly as the anchor said — and my withdrawal of that
anchor would have removed the blocker from view rather than clearing it.

**Separately noted, not investigated here:** 46 of 76 `prod/` artifacts also carry no
gate stamp. `prod/` holds retired and rollback copies as well as served ones, so that
count is not by itself a finding — it is a denominator that wants a follow-up before
anyone quotes it.

## Correction to the record

The earlier claim — *"the certified clf recipe does have an OOS corpus (43 folds /
178,191 rows / 625 OOS dates / 292 tickers)"* — is **withdrawn**. The corpus is real; it
is the GBDT production recipe's. The clf statement it was used to retire stands.
