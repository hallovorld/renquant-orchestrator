# Twin-implementation registry (GOAL-3)

**What this is.** A registry of places where the same logic exists in more than one
copy, and the copy that RUNS is not the copy a reader would find first. Not a
remediation plan — GOAL-3 is audit-and-register, and each row's fix has a
different owner and blast radius.

**Why it is worth a registry rather than seven bug reports.** Every row below cost
real time to establish, and in **four** of them a defect was filed or a fix was
written against the WRONG COPY before the live one was found. The failure is not
"there are duplicates" — duplication is sometimes deliberate. The failure is that
**nothing in the repo tells you which copy executes.**

Every claim below carries a provenance tag per `doc/memory/long-term-agreements.md`
item 10 (`[VERIFIED — <file/command>]`, `[VERIFIED — prior work, <issue/PR>]`, or
`[ASSUMED — <why>]`). Every row also states how the live copy was IDENTIFIED, because
"I read the one that looked canonical" is how four of these went wrong.

---

## R1 — the public export is the non-kernel twin

| | |
|---|---|
| copies | `renquant_pipeline.VetoWeakBuysTask` (public top-level export) vs the kernel `job_panel_scoring.py` implementation |
| which runs | `renquant_pipeline/__init__.py` maps the public name to `panel_scoring.py`, **not** the kernel |
| how identified | reading `__init__.py`'s mapping |
| cost | a kernel-only fix misses the documented symbol; this is the third instance of the both-copies class `[VERIFIED — prior work, renquant-pipeline#222]` |
| open | renquant-pipeline#222 — the panel_scoring twin is missing 3 kernel guards |

## R2 — the documented fix lives in dead code

| | |
|---|---|
| copies | `RenQuant/scripts/fetch_sec_fundamentals.py` (**legacy/dead**) vs `renquant-base-data/src/renquant_base_data/sec_fundamentals.py` (**live**, invoked by `weekly_fundamental_refresh.sh:94`) |
| the trap | `_safe_ratio(num, denom, eps=1.0)` exists ONLY in the dead script. `grep -rn "_safe_ratio"` over the live package's `src` and `tests` returned **zero matches** |
| consequence | `book_to_price` reached **1.68e19** on **21,722 rows = 1.616%** of non-null across 26 tickers, five weeks after the fix was "documented as applied" `[VERIFIED — prior work, renquant-base-data#55]` |
| how identified | grepping the live package, after filing the defect against the dead one |
| cost | **RenQuant#545 named the wrong file** and had to be corrected in-thread; real fix is base-data#55 |

## R3 — three trainers, and the producer is the one nobody names

| | |
|---|---|
| copies | `RenQuant/scripts/train_production_model.py` · `renquant-model/src/renquant_model_gbdt/panel_trainer.py` · **`renquant-orchestrator/src/renquant_orchestrator/train_gbdt.py`** (pinned) |
| which runs | the **pinned orchestrator** one |
| how identified | two independent signatures — the incumbent artifact's `training_notes` string exists only at `train_gbdt.py:228`, and its `params` **omit `nthread`** (matching `PANEL_LTR_PARAMS`, whereas `train_production_model.py:58` hardcodes it) `[VERIFIED — renquant-orchestrator/src/renquant_orchestrator/train_gbdt.py:228, RenQuant/scripts/train_production_model.py:58]`. Corroborated by orch#620's bit-identical `booster_raw_json` check between the stamping branch and `origin/main` `[VERIFIED — prior work, renquant-orchestrator#620]` — that check confirms the stamping change didn't alter the booster, not a direct three-way reproduction against the other two trainers `[ASSUMED — inferred from orch#620's booster-identity methodology]` |
| cost | I pointed a delegated retrain at the wrong twin **twice** before this was settled; its metadata came out non-production-shaped (`nthread: 14`) |

## R4 — the artifact metadata dict is in neither obvious place

| | |
|---|---|
| copies | the orchestrator constructs a `GbdtTrainingContext` at `train_gbdt.py:226`; the dict is assembled in the **model pin** at `renquant-model/.../panel_trainer.py:246` (`build_model_artifact`, literal at `:272`), and driver fields are layered in at `pipeline.py:150` via `artifact.update(ctx.extra_artifact_fields)` |
| cost | I assumed it was in the orchestrator and was wrong; the stamping fix (orch#620) had to route through `extra_artifact_fields` to avoid touching model internals |

## R5 — the config the runner reads and the config the trainer reads disagree, INVERTED

| | |
|---|---|
| copies | pinned `renquant-strategy-104/configs/strategy_config.json` (**runner**, `daily_104.sh:113`) vs `RenQuant/backtesting/renquant_104/strategy_config.json` (**trainer**) |
| divergence | primary `ranking.panel_scoring.kind`: pinned **`xgb`**, umbrella **`hf_patchtst`** — the two models' roles are **exactly inverted**. Watchlists 145 vs 142, gap exactly `CRWV`/`RKLB`/`SPCX` `[VERIFIED — prior work, RenQuant#544]` |
| consequence | a resolver failure promoted a **623-day-stale** shadow checkpoint to primary; its scores are intrinsically all-negative, so the ordinary buy floor admits **no name at all** — a silent sell-only book `[VERIFIED — prior work, RenQuant#546]` |
| open | RenQuant#544 (ownership), RenQuant#546 (the hazard); fail-closed landed as RenQuant#547 |

## R6 — the drift guard compares one stale copy against another

| | |
|---|---|
| copies | `strategy_config.json` vs `strategy_config.golden.json`, both under `backtesting/renquant_104/` |
| the trap | **both** name `hf_patchtst` primary, so the guard reports **clean forever** while both disagree with production `[VERIFIED — prior work, RenQuant#547]` |
| re-measured 2026-08-01 | there are **FOUR** surfaces, not three, and they split **2–2 into two internally-consistent PAIRS** `[VERIFIED — this session]`:<br>**xgb**: `renquant-strategy-104/configs/strategy_config.json` (the runner's, per R5) and `.../strategy_config.golden.json`<br>**hf_patchtst**: `RenQuant/backtesting/renquant_104/strategy_config.json` and `.../strategy_config.golden.json`<br>So the guard is not comparing a good copy against a bad one — it is comparing **two members of the same pair**. Any check that stays on one side of the pinned/umbrella boundary passes forever *by construction*, which is a stronger statement than "both are wrong": it says **where** a guard has to look. |
| cost | my first proposed fix was "validate the fallback against golden" — it would have added a check that **passes forever**, which is worse than no check because it reads as protection. Only laying out all three configs revealed golden was itself inverted |

## R7 — the same twin-ness inside one file: cost-aware branch never reached

| | |
|---|---|
| copies | `is_wash_sale_blocked_with_cost` branch (a) — cost-vs-return — and branch (b), the fallback |
| which runs | **(b) only.** None of the three live call sites passes `expected_dollar_return`, so the cost-aware branch never executes in production `[VERIFIED — prior work, renquant-pipeline#227]` |
| the claim it broke | the docstring says *"callers that have μ̂ should pass `expected_dollar_return`"* — satisfied by **0 of 3** callers `[VERIFIED — prior work, renquant-pipeline#227]` |
| consequence | buys zeroed on **3 of 5** sessions to protect **$0.04–$13.62** of NPV while **$6,868** of cash sat unused `[VERIFIED — prior work, doc/progress/2026-07-29-wash-sale-block-starves-deployment.md, renquant-pipeline#227]` |
| fix | renquant-pipeline#227 (merged) |

---

## R8 — the SAME gate stamp in two locations inside one artifact, and they disagree

**A different species from R1–R7: this twin is in the DATA, not the code.**

| | |
|---|---|
| copies | `metadata.wf_gate_metadata` (**canonical**) and a legacy top-level `wf_gate_metadata`, in the same JSON artifact |
| which copy is authoritative | the canonical one — but nothing in the artifact says so |
| measured | over 29 prod `panel-ltr.alpha158_fund*.json`: **29 carry the canonical block; 14 also carry the legacy copy; 0 carry only the legacy one.** Where both exist they **agree on 12 and DISAGREE on 2** — the legacy block has no `sanity_eval_scope` while the canonical one records `walkforward_manifest` `[VERIFIED — 本次实测 2026-07-31, direct JSON inspection]` |
| cost | **three defects in one evening, two of them published claims I had to retract** |

The three:

1. **backtesting#89** — a census read the top-level key, found it on 14 of 29, and
   concluded *"fifteen rows asserted an observation nobody made."* **A fabrication
   accusation against real evidence.** Retracted.
2. **orch#680** — the same read produced *"ten of the eleven artifacts cannot re-derive
   the table."* All 11 can; 44 of 44 rows re-derive exactly. Retracted.
3. **orch#683** — `bundle_seal.extract_bindings` read the legacy key only. The deployed
   panel happens to carry both, so it is correct today **by luck**; on the 15 panels
   carrying only the canonical block it would seal `wf_gate_verdict: "UNSTAMPED"` and
   drop all seven override-provenance fields — while its docstring claimed it closed the
   GOAL-5 *"override provenance not in the run bundle"* gap.

**Why this species is worse than R1–R7.** A code twin misleads whoever reads the source.
A *data* twin misleads every tool that reads the artifact, independently, and each one
fails differently — a census under-counts, a seal writes UNSTAMPED, an audit cries
fabrication. And the failure is **silent and direction-dependent**: reading the wrong key
returns `None`, which every reader interprets as *"the thing isn't there"* rather than
*"I looked in the wrong place."*

> **A checker looking in the wrong place does not discover that its subjects are missing
> — it discovers that it is looking in the wrong place.**

**What the live path does right, and it is worth recording.** A sweep of every
`wf_gate_metadata` reader across seven repos found the production readers **already**
correct: `preflight.py`, `job_panel_scoring.py`, `model_acceptance.py`,
`latest_run_docs.py`, `assemble_track_b_verdict.py`, `model_bundle.py`,
`model_freshness_enforcer.py` and `check_model_bundle_consistency.py` all read canonical
first. **Only the new audit tools written that evening had the bug**, plus `bundle_seal`.
The first pass of that sweep flagged six production files and **five were false
positives** — a regex cannot tell whether the receiver of `.get("wf_gate_metadata")` is
the whole payload or the `metadata` sub-dict.

## R9 — one artifact basename, 23 paths, 3 distinct digests

| | |
|---|---|
| copies | `panel-ltr.alpha158_fund.json` resolves to **23 paths** under `backtesting/renquant_104/artifacts` with **3 distinct sha256** — 21 of them inside `diagnostics/modal_sweep_*/bundle/kernel/artifacts/prod/`, one in `diagnostics/wf_audit_20260527/`, one in `prod/` `[VERIFIED — 本次实测 2026-07-31]` |
| which copy is live | `prod/panel-ltr.alpha158_fund.json` — nothing in the tree says so |
| cost | an `rglob` + `sorted(hits)[0]` in a census silently measured a **modal-sweep diagnostic copy** and shifted `BULL_CALM`'s median from `0.022029` to `0.021927` **with no error raised**. Caught only because two runs of the same tool disagreed |

This is R1–R7's *"which copy executes"* displaced by one step: **which copy gets
MEASURED**. It appeared inside the tool written to make a measurement auditable.

**Remediation applied here:** resolve against a **declared root, non-recursively**, and
treat a basename resolving to more than one **distinct digest** as `AMBIGUOUS` — refuse
rather than choose. That is now enforced by a fixture in
`tests/test_bear_pass_is_one_small_regime.py`.

## The pattern, stated once

In R2, R3, R5 and R6 a defect was filed or a fix written against a copy that does
not run. The distinguishing signature in every case was **not** in the code's
structure — it was in a runtime artifact: an invocation line in a shell script, a
`training_notes` string, a stamped `params` key, a value printed by running the
thing. **Identifying the live copy required executing or reading output, not
reading source.**

That is the registry's actual finding, and it is what a remediation should target.

## What would remove a row from this registry

Not deleting a copy — some duplication is deliberate (a portable kernel plus a
richer public surface, a legacy script kept for reference). A row is retired when
**the repo itself states which copy executes**, mechanically:

1. **an executable pointer** — the non-live copy raises or logs on import, or
   carries a header naming the live one at a path a grep will hit;
2. **a parity test** for copies that are meant to agree (R1's kernel-vs-public,
   R3's trainers) that fails when they drift, so "twin" becomes "mirrored";
3. **a single source for role assignment** in R5/R6 — **four** files assert which
   model is primary (re-measured 2026-08-01), splitting 2–2 into two
   internally-consistent pairs across the pinned/umbrella boundary. Detection now
   exists — `ops/strategy_config_primary_parity.py` (orch#694) compares **across**
   the boundary and fails on the disagreement — but a single *source* does not;
4. **a reachability assertion** for R7's shape — a branch no caller reaches is
   dead code wearing a docstring, and a test can say so;
5. **for R8, a stated canonical key** — every reader resolves through one helper that
   keys on the canonical location's PRESENCE (not its truthiness, or an emptied stamp
   resurrects the legacy value), records which key answered, and a parity check reports
   the artifacts where the two copies disagree instead of silently preferring one;
6. **for R9, a declared root** — no basename glob over an artifact tree that contains
   diagnostic bundles; ambiguity is an error, not a choice.

None of that is implemented here. This document is the register; each row's fix
has a different owner and a different blast radius, and R5's in particular changes
what the daily run trains on.
