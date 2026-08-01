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

---

## ROUND 2 2026-07-31 — the tool did not prevent the error it was written about

Reviewed `[codex on orch#691]`: *"its lanes are arbitrary command-line directory names,
so invoking it for the GBDT directory and labeling the result clf recreates the exact
substitution this PR corrects."*

Correct, and it is the sharpest possible version of the point: a tool written **because**
one lane's number was attached to another lane accepted the lane name as a free-text
argument. It made that mistake faster to commit, not harder.

### The binding now comes from the artifact

```
artifact → metadata.wf_gate_metadata.artifact_usage.manifest_path
         → the walk-forward manifest
         → the fold artifact URIs it names
         → the corpus directory those folds live in
```

The caller names an **artifact** — the thing actually served — and every corpus statement
is derived from that artifact's own stamp. Mislabelling now requires falsifying a stamp,
not mistyping a path.

Run on three real artifacts `[本次实测 2026-07-31]`:

| artifact | status | folds | corpus |
|---|---|---:|---|
| `shadow/panel-clf.top-decile.fwd60.json` | **`NO_GATE_STAMP`** | 0 | — |
| `prod/panel-ltr.alpha158_fund.json` | **`MANIFEST_MISSING`** | — | stamp names `/tmp/gbdt_manifest_abs.json` |
| `prod/panel-ltr.alpha158_fund.previous.json` | **`COVERED`** | **43** | `walkforward_gbdt_prod_recipe_v2` |

**The clf finding is now derived rather than asserted** — it falls out of the resolution
as `no_gate_stamp`, and the 43 folds attach to the artifact that actually binds to them.

### A new finding the binding exposed

Surveying every stamped `prod/` artifact `[本次实测 2026-07-31]`:

| | |
|---|---:|
| `prod/` artifacts | 76 |
| carrying a gate stamp | 30 |
| whose stamp names a manifest | **30** |
| whose manifest **resolves on disk** | **17** |
| whose manifest path is under **`/tmp/`** | **13** |

So the canonical binding contract **exists in the data and is not durable**: 13 of 30
stamped artifacts point their provenance at an ephemeral path. Stated narrowly — this is
a fact about the **pointer**, not evidence the folds never existed, and the tool's
`manifest_missing` note says so in those words.

### Statuses are distinct facts

`no_gate_stamp` / `no_manifest_named` / `manifest_missing` / `unrecognised_manifest_shape`
/ `artifact_missing` / `artifact_unreadable` are separate, and none of them is "0 folds".
The last one is not hypothetical: the first implementation guessed a fixed list of row
keys and silently returned **0 folds** for the real manifest, whose rows live under
`retrains`. Row-key discovery now scans every list-valued key and **records which one
answered**, so a manifest shape change appears in the report instead of as a quiet zero.

14 tests.

---

## ROUND 3 2026-07-31 — `(x or {}).get(...)` is not a guard, and I had just fixed this shape elsewhere

Reviewed `[codex on orch#691]`: *"`_gate_block` calls `.get` on `metadata` after only
`or {}`, and `resolve` does the same for `artifact_usage`. A valid JSON artifact with
`metadata` or `artifact_usage` as a string raises `AttributeError` instead of returning an
explicit fail-closed status and controlled exit code."*

Correct, and confirmed by executing it before changing anything
`[本次实测 2026-07-31]`:

```
metadata = "n/a"                    -> *** CRASH *** AttributeError: 'str' has no 'get'
artifact_usage = "n/a"              -> *** CRASH *** AttributeError: 'str' has no 'get'
manifest_path = 7                   -> status=manifest_missing        <- WRONG STATUS
```

`or {}` is not a guard: a **non-empty string is truthy**, so the fallback never fires. And
the third case is worse than a crash because it is silent — it reported the pointer as
**missing** when it is **malformed**, which is a different defect with a different owner.

**This is the same shape I fixed in `gate_stamp_parity.py` (orch#687) and reintroduced
here about an hour later.** That is why `MALFORMED` is now a named module constant in this
file too, rather than a local `isinstance` check I have to remember to write.

Four distinct fail-closed statuses, none of which is "no coverage":

| shape | status |
|---|---|
| `metadata` is not an object | `malformed_gate_stamp` |
| the gate block (canonical **or** legacy) is not an object | `malformed_gate_stamp` |
| `artifact_usage` is not an object | `malformed_artifact_usage` |
| `manifest_path` is not a string | `malformed_manifest_path` |
| `manifest_path` is `""` or absent | `no_manifest_named` — the distinction cuts both ways |

### Scheduled behaviour is now pinned

`main()` is driven directly for every malformed shape, in both text and `--json` mode. The
reason is the one already on the register: `sys.exit(main())` makes an uncaught exception
and a deliberate alarm indistinguishable to a scheduled job — both are just non-zero. So
the tool must **return** a status, never raise, and the tests assert that by calling
`main()` rather than only `resolve()`.

23 tests (was 14).

### I pushed a red test in round 3, and the failure was informative

`test_no_reader_takes_the_gate_stamp_from_the_LEGACY_key_alone` — the repo-wide R8
invariant — flagged `wf_corpus_coverage.py` **after** I had pushed. I ran the suite and
pushed in the same batch instead of waiting for the result. That is the second time this
session; the rule is to gate the push on the suite, not to run them concurrently.

**The failure itself was a false positive, and fixing it correctly mattered.** The
detector accepted a canonical read only when the receiver was a bare `ast.Name`. My
round-3 refactor writes the defensive form:

```python
meta = payload.get("metadata")
... (meta or {}).get("wf_gate_metadata")
```

whose receiver is a `BoolOp`, not a `Name` — so a **compliant** reader scored as
legacy-only.

The tempting fix was an `ALLOWED_FALLBACK` entry. That would have silenced the invariant
for this file **permanently**, including for a future edit that really did read the legacy
key alone. Instead `_receiver_is_canonical()` now decides over the receiver's whole
subtree, with a test in **each** direction: the defensive form is accepted, and a genuine
`payload.get("wf_gate_metadata")` is still caught.

Suite: **4978 passed, 2 skipped**.
