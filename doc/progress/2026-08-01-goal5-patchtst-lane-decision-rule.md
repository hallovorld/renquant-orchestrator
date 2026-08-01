# PatchTST lane: a frozen decision rule (GOAL-5 / PatchTST 关线)

## What landed

`doc/design/2026-08-01-patchtst-lane-decision-rule.md` — a decision rule for the
`hf_patchtst` shadow lane, frozen before any verdict is computed.

## Why it is split in two

The lane sat undecided because "is it compliant" and "is it any good" were being answered
together. They have different answers and different availability:

* **Limb A (governance)** — answerable today, deterministically, with no inference.
  Artifact **625 d** stale against the **28 d** `STALENESS_MAX_DAYS` limit (RFC #210),
  ≈ **22×**; the weekly retrain **has not acted on 4 consecutive runs**, 3 of them
  crashes (orch#724). `[本次实测 2026-08-01]`
* **Limb B (merit)** — **not answerable today**, and the rule says so instead of guessing.

## The ambiguity I had to resolve before writing a threshold

The sentinel reports `limit_28d` while the pinned config carries `max_age_days: 30`. Those
are **different objects**: the 28 is `rq104_shadow_scorer_sentinel.py:284`
(`STALENESS_MAX_DAYS`, env-overridable), and the 30 belongs to
`.panel_ltr.asset_embeddings.max_age_days` — asset embeddings, a node that is itself
`enabled=False`. Citing the 30 would have put the wrong limit into a frozen rule.

## Why limb B is frozen rather than run

`renquant-model#153` measured on the committed per-date series that for this arm
ρ₁ = 0.8222 with ρ₂ = 0.8018 ≫ ρ₁² = 0.6761 (**not AR(1)**), that its permutation null has
ρ₁ ≈ 0 and therefore the wrong width, and that `N/h` errs in both directions. Every
off-the-shelf yardstick is currently invalid for it. Running the test now would reproduce
exactly what closed model#124/#128/#135.

The frozen rule fixes: the statistic, the null (explicitly **not** the existing `ic_perm`
column), a per-arm dependence correction, a mandatory positive control that must NOT
reject, the comparator means recorded in advance (`certified_clf 0.0830`,
`prod_XGB 0.0907` vs PatchTST **0.0164**) so the bar cannot move afterwards, and the
decision map. A rejection never licenses promotion out of shadow.

## Not done here

The retire-or-fix call on limb A. That is a live-surface change and an operator decision;
this document names the breach and hands it over. Docs only — no code, no config, no
production surface touched.
