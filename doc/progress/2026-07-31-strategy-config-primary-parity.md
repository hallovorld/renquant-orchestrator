# GOAL-5 — two strategy-config surfaces disagree about which model decides, in mirror image

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 (P0), daily-run reliability

## The finding

Both files below present as the renquant-104 strategy config. Read directly
`[本次实测 2026-07-31]`:

| | `renquant-strategy-104/configs/strategy_config.json` | `RenQuant/backtesting/renquant_104/strategy_config.json` |
|---|---|---|
| `ranking.panel_scoring.kind` | **`xgb`** | **`hf_patchtst`** |
| `enabled` | `true` | `true` |
| `artifact_path` | `artifacts/prod/panel-ltr.alpha158_fund.json` | `.../patchtst_shadow/pt07_strict_.../hf_patchtst_all_seed44_model.pt` |
| `shadow_models` | `hf_patchtst_pt07_strict_seed44_previous_primary`, `topdecile_clf_blend_leg` | `xgb_alpha158_fund_previous_primary` |

**Primary and shadow are exactly swapped.** One surface says XGB decides and PatchTST
watches; the other says PatchTST decides and XGB watches. Each surface's primary appears
in the other's shadow list, under a `_previous_primary` name.

## Why nothing caught it

`engineering_census._default_strategy_configs` already names **both** paths — and then:

```python
if not any(item["exists"] for item in payload["strategy_configs"]):
```

An existence check over **interchangeable candidates cannot notice that the candidates
contradict each other**. The census passes as long as one of them is on disk, which is
true when they disagree and true when they agree.

## What this does NOT establish, and why the restraint matters

**It does not identify which surface the daily run reads.** That resolution lives in the
run scripts, and asserting it from a directory layout is precisely how "which copy
executes" defects have been published as facts in this programme before. The tool prints
that sentence, and a test asserts it prints it.

So the finding is: **two declared surfaces disagree about who decides.** Establishing
which is authoritative, and repairing the other, is the follow-up — and it needs run-side
evidence this tool deliberately does not invent.

It also reconciles two separate staleness observations without merging them: the
625-day-stale served primary (orch#688) is about the **PatchTST** identity, while
"the booster has not changed since 2026-07-16" (orch#692) is about the **XGB** artifact.
Different lanes. Which of them is the live primary is exactly the open question above.

## The tool

`ops/strategy_config_primary_parity.py` — compares `kind`, `enabled`, `artifact_path` and
the shadow-model name set across every surface named on the command line, and calls out
the **mirror** case by name because "the kind differs" understates it.

Statuses are distinct and none of them is agreement: `absent` (a surface not deployed here
says nothing about the ones that are — recorded, excluded, never counted either way),
`unreadable`, `no_panel_scoring`, `malformed_shadow_models`. Zero readable surfaces exits
**2**, because "nothing to compare" must never read as "they agree".

Every container is type-checked rather than `or {}`-ed — a non-empty string is truthy, so
the fallback never fires and `.get` raises. **Three tools in this repo have now needed
that sentence.**

Read-only: opens config files, writes nothing, never invokes git.

## Tests

13, aimed at the ways a parity check reports agreement that is not there: an absent
surface counted neither way; a **broken** surface making the check fail rather than
silently shrinking the comparison; a string `ranking` / `panel_scoring` not crashing; a
non-list `shadow_models` reported as malformed rather than as an empty shadow set (which
would make a corrupt surface agree with a genuinely shadow-free one); zero readable
surfaces exiting 2; anti-vacuity where identical surfaces agree; and the refusal to name
an authoritative surface asserted present in the output.

Suite: **5002 passed, 2 skipped**.

---

## Second finding, same subject — `artifact_path` has no single base (GOAL-7 prerequisite)

Chasing GOAL-7's real question — *what must a new shadow lane satisfy to go live?* — I
checked whether the **existing** shadow declarations resolve to real artifacts.

**A claim I nearly published, and why it was wrong.** My first pass resolved the pinned
config's PatchTST shadow against three roots I chose, found nothing, and I was about to
report *"the reviewed surface declares a shadow whose artifact does not exist"*. Searching
the whole tree instead: **the file exists** — under the umbrella root
`RenQuant/artifacts/patchtst_shadow/…`, not under `backtesting/renquant_104/artifacts/`.
*"Not found" only ever means "not found in the roots I searched."* That rule caught a
false finding one step before publication.

**The real result is narrower and more useful** `[本次实测 2026-07-31]`. Within the
**same** pinned config file:

| declared `artifact_path` | umbrella root | `backtesting/renquant_104` |
|---|:--:|:--:|
| `artifacts/patchtst_shadow/…/seed_44/…model.pt` | **EXISTS** | missing |
| `artifacts/shadow/panel-clf.top-decile.fwd60.json` | missing | **EXISTS** |
| `artifacts/prod/panel-ltr.alpha158_fund.json` | missing | **EXISTS** |

**No single base resolves all three.** Either the loader applies a different base per
lane, or one of these lanes does not resolve at run time — and a shadow lane that fails to
resolve is skipped, which is precisely the silent-death class GOAL-1 exists for.

**Why this is GOAL-7's blocker and not a footnote.** GOAL-7 wants a standalone momentum
model deployed *to shadow*. Before that is even meaningful, `artifact_path` must have one
answer to "relative to what?". Today it does not, and the ambiguity is invisible: both
readings produce a file for *some* lane.

`audit_paths()` reports **every** base a path resolves under — plural on purpose, because
returning the first hit would conceal which base answered, and that concealment is the
whole defect. `bases_disagree` and `unresolvable` are separate: *"the files are in
different places"* and *"the file is nowhere"* are different problems.

The audit is **skipped entirely when no `--base` is given** — a resolution check with no
bases would report every path unresolvable, an alarm manufactured by the absence of an
argument.

**Still not claimed:** which base the loader actually uses. Naming an authoritative base
from a directory layout is the same over-reach this module already refuses for the
authoritative *surface*.

20 tests (was 13). Suite: **5009 passed, 2 skipped** — run before the push.

---

## ROUND 2 — two fail-open paths, both "silently normalise corruption into a matchable value"

Reviewed `[codex on orch#694]`: *"`read_surface` accepts any list as `shadow_models` and
silently drops non-object members or members without a string name. For example,
`[{"name": 7}]` is reduced to `[]`, so it can agree with a genuinely empty shadow list.
Likewise, missing `kind`, `enabled`, or `artifact_path` values can compare as equal `None`
values."*

Both confirmed by executing them before changing anything `[本次实测 2026-07-31]`:

```
corrupt shadow entry vs genuinely empty  -> disagreements: []   n_broken: 0
both surfaces missing all identity fields -> disagreements: []   n_broken: 0
```

**They are one shape, twice: a corrupt input normalised into a value that can MATCH.** A
filtered-out member becomes `[]`, which equals a real `[]`. A missing field becomes
`None`, which equals another missing field. In both cases the tool built to detect
disagreement reported agreement between a corrupt surface and a healthy one — the
fail-open shape this module exists to catch, committed by the module.

**Fixes.** A malformed shadow **member** — non-object, or a non-string `name` — makes the
surface `malformed_shadow_models`, and **every** bad entry is reported, not just the
first. The three identity fields are **required**: a surface missing any of them is
`incomplete_identity`, because *a surface that does not say who decides cannot agree with
one that does*.

The distinction still cuts both ways: an **empty** shadow list on a complete surface is
valid — a lane-free config is legitimate — and only a **corrupt** one is broken.

**Three of my own earlier path-audit tests failed on this change**, because their fixtures
omitted `enabled` and were relying on exactly the fail-open being closed. Completing the
fixtures was the fix: a path audit only means anything on a readable surface.

**The real finding survives the strictness** — asserted directly, because if the live
configs had become "broken" the mirror-swap would be hidden behind a validation error
instead of reported. Both real surfaces still read cleanly and still disagree.

28 tests (was 20). Suite: **5017 passed, 2 skipped** — run before the push.

---

## CORRECTION 2026-07-31 — this was already registered as R5, and I did not check

**The mirror-swap is not a new finding.** It is **R5** in
`doc/arch/twin-implementation-registry.md`, in this repo, merged as orch#623 — and R5 has
*more* than I re-derived:

| | R5 (already recorded) | what I published as new |
|---|---|---|
| the inversion | pinned `xgb` vs umbrella `hf_patchtst`, roles exactly inverted | same |
| which one runs | **the runner takes the pinned config** — `daily_104.sh`, via `renquant_strategy_config "$SUBREPO_ROOT"` | *"I refuse to say"* |
| watchlist gap | 145 vs 142, exactly `CRWV` / `RKLB` / `SPCX` | not measured |
| the consequence | a resolver failure promotes a **623-day-stale** shadow checkpoint to primary; its all-negative scores admit no name, i.e. a **silent sell-only book** | not connected |

I measured the files and wrote it up **without checking the registry first**. The registry
is GOAL-3's entire product, and its purpose is to stop exactly this. Verified since:
`daily_104.sh` resolves `PROD_STRATEGY_CONFIG` through
`renquant_strategy_config "$SUBREPO_ROOT" strategy_config.json`, with a fallback that is
fail-closed **only** when `RENQUANT_STRICT_SUBREPO_PATHS=1` or `RENQUANT_OPS_FAIL_CLOSED=1`
`[本次实测 2026-07-31]`.

**My restraint was also wrong in a specific way.** Refusing to name the authoritative
surface was correct *for what I had measured* — but the repo already knew, and "I cannot
tell from a directory layout" is not the same as "this is unknown". Presenting the second
as the first understates the programme's own evidence.

### What this branch does still contribute

1. **R5's retirement condition #3, mechanically.** R5 asks for *"a single source for role
   assignment — today three files assert it"*. This is its detection half: a check that
   **fails** when the surfaces disagree, so the divergence stops depending on someone
   re-reading two files. A registry row records a defect; this makes it *detectable*.
2. **The `artifact_path` base ambiguity**, which R5 does not cover: within the pinned
   config, three declared paths resolve under **two different bases** and **no single base
   resolves all three** `[本次实测 2026-07-31]`. That is a distinct defect from the
   inversion, and it is the one blocking GOAL-7's path-to-shadow.

The PR is retitled accordingly. The tool's own docstring now opens with the attribution,
so a reader who never sees this document still learns it from the code.
