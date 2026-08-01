# GOAL-3 C6 — R9's remediation existed once, inside one tool. Now it is importable.

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-3 (twin registry, condition C6)

## R9, re-measured today

`panel-ltr.alpha158_fund.json` under `backtesting/renquant_104/artifacts`
`[本次实测 2026-08-01]`:

| | |
|---|--:|
| paths | **23** |
| distinct sha256 | **3** (×21, ×1, ×1) |
| under `prod/` | **1** |
| under `diagnostics/` | **22** |

Unchanged from the 2026-07-31 measurement. An `rglob` + `sorted(hits)[0]` still picks a
modal-sweep diagnostic copy.

## What C6 actually was, after two corrections

**First guess — "recursive globs are the hazard" — was wrong.**
`model_freshness_enforcer.default_search_dirs` rglobs `panel-ltr*.json`, which looked like a
live instance. Measured: its roots are `staging/ prod/ sim/`, and **0 of its 62 hits** are
diagnostics copies. It is not exposed. The hazard is not `rglob`; it is **globbing from a
root that contains the diagnostic tree**.

**Second guess — "the rule is implemented twice" — was also wrong.** I expected a copy in
`tests/test_bear_pass_is_one_small_regime.py`; that test *exercises*
`regime_profile_census`'s resolver rather than duplicating it. One implementation, with a
test.

**What was actually true:** the rule was **private to one census tool**. R9's subject is
*which copy gets used* — so a rule against it that every new caller must re-type is the
same hazard one level up. That is C6.

## The change

`ops/declared_root_resolve.py` — `resolve_artifact(basename, search_root, recursive=False)`
returning `resolved` / `not_found` / `ambiguous`. `regime_profile_census.py` now **imports**
it instead of restating it, and a test asserts the message string no longer lives in the
census.

Deliberate properties:

- **Non-recursive by default** — a caller who does not think about it gets the safe
  behaviour.
- **More than one distinct digest REFUSES.** Not "prefer prod", not "newest": choosing is
  what produced R9. There is intentionally no "just give me a path" variant, because that
  is the signature that caused it.
- **Many paths at one digest still resolves** — 21 identical copies are one artifact
  wearing 21 names, and refusing there would block a legitimate resolution.
- **An unreadable candidate is `ambiguous`, not a digest difference** — an IO error is not
  a content fact.

Verified against the live tree: from the artifacts root it returns **ambiguous (23 paths,
3 digests)**; from `prod/` it **resolves**.

## Behaviour invariance

`tests/test_bear_pass_is_one_small_regime.py`: **12 passed before the rewire and 12 after**.
Suite: **5193 passed, 2 skipped**.

## Not claimed

That every artifact-resolving site in the repo now uses this — only `regime_profile_census`
was rewired, because it was the only site that had the rule at all. Migrating others is a
follow-up that needs each call site's declared root established first, and inventing roots
for them would be worse than the duplication.
