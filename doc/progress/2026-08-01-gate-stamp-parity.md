# R8's parity check exists now — and two artifacts disagree with themselves about `passed`

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-3 (twin registry R8) / GOAL-5 (AC6)

The twin registry's retirement condition for **R8** asks for *"a parity check that reports
the artifacts where the two copies disagree instead of silently preferring one."* Nothing
performed it. This is that check, and its first run found more than a marker mismatch.

## What the first run found

`[本次实测 2026-08-01, ops/renquant104/gate_stamp_parity.py --root <umbrella>/backtesting/renquant_104/artifacts/prod]`

```
30 artifact(s) scanned — 15 carry BOTH copies, 15 canonical-only,
0 legacy-only, 0 no stamp, 0 unreadable
```

**Two of the fifteen disagree, and not on a cosmetic field:**

| field | canonical (`metadata.wf_gate_metadata`) | legacy (top-level) |
|---|---|---|
| **`passed`** | **False** | **True** |
| `sanity_eval_scope` / `wf_eval_scope` | `walkforward_manifest` | **absent** |
| `gate_verdict_before_override` | **absent** | `False` |
| `operator_authorized_override` | **absent** | **`True`** |
| `override_reason` | **absent** | *"Operator authorized 2026-07-05: absolute returns positive (3/3 cuts), model freshness priority over benchmark-beat in bull market. APY lag vs SPY = −5.7%."* |

Affected: `panel-ltr.alpha158_fund.previous.json` and
`panel-ltr.alpha158_fund.weekly_rollback_2026-07-06.json`.

> **Inside one file, a reader taking the canonical block sees a gate that FAILED with no
> explanation; a reader taking the legacy block sees one that PASSED under a recorded
> operator override.** Those are opposite operational conclusions about the same artifact.

## The uncomfortable part: canonical-first LOSES the override record here

Every reader in this repo was moved to canonical-first — correctly, and that fixed the
scope-marker reads. But on these two artifacts the **override provenance exists only in
the legacy copy**. A canonical-only reader silently drops
`operator_authorized_override`, `gate_verdict_before_override` and `override_reason`.

That is the same evidence AC6 R4 exists to preserve (orch#685 puts a
`wf_gate_provenance` block in the daily bundle; `renquant-common#40` teaches the contract
about it). **Neither copy is complete on these two files:** canonical has the scope
fields and no override; legacy has the override and no scope. Preferring one silently —
in either direction — discards something.

## What the check does and does not claim

**Reports, with a nonzero exit.** A disagreement is a defect **of the artifact**, not of
whichever reader happens to look. Absent-in-one-copy counts as a disagreement:
treating absent as "no opinion" is what would have hidden the missing scope fields.

**Does NOT claim which copy is right.** The registry says the canonical key is canonical;
that is about **where a reader should look**, not about which value is true when they
differ. Deciding these two artifacts is a per-artifact judgment with an operator override
in it — **not something a scan should resolve, and not resolved here.**

**Does NOT touch any artifact.** Read-only.

## Tests

7, on **synthetic fixtures**, so they measure the contract rather than this operator's
artifact tree: agreement is clean; a `passed` disagreement is reported; **absent counts
as a disagreement**; canonical-only and legacy-only are counted but not flagged; an empty
scan is a **problem** (no subjects ≠ parity); an unreadable artifact is reported rather
than skipped; and the exit code is nonzero exactly when a disagreement exists.

## A method note

The first live run was piped to `head` and I read `$?` after the pipe — which is `head`'s
status, not the tool's. That is the "never swallow an exit code in a pipe" rule, broken
by me, in the same session I wrote it down. The exit-code behaviour is now asserted by a
test rather than eyeballed.

---

## ROUND 2 2026-07-31 — the eight-field enumeration WAS the fail-open default

Reviewed `[codex on orch#687]`: *"the scanner compares only eight selected fields, so a
disagreement in any later or currently unlisted gate field passes cleanly; it also treats
a non-object canonical or legacy stamp as absent, which can turn a malformed dual stamp
into no-stamp rather than a problem."*

Both correct, and the first is a shape this programme has a registry entry for:
**an enumerated allow-list leaves a fail-open default.** A gate field added tomorrow sits
outside `COMPARED_FIELDS` and diverges silently — the check would keep reporting clean on
exactly the drift it exists to find.

**Three changes:**

1. **The comparison surface is now the union of every key in both blocks**, walked
   recursively, each divergence reported at its dotted path. `COMPARED_FIELDS` is gone;
   `SALIENT_FIELDS` survives only to *order* the output.
2. **Fail closed on a malformed copy.** A stamp that is present but not a JSON object is
   `MALFORMED`, not absent — including when `metadata` itself is malformed. A JSON
   `null` is still absent, and there is a test for each direction so the distinction is
   not merely a stricter alarm.
3. **Presence, not truthiness.** `if canon and legacy` treated an EMPTY canonical block
   `{}` as missing and fell through to `elif legacy`, counting a dual-stamped artifact as
   legacy-only and skipping the comparison. This is the identical defect codex found in
   orch#683; it is now keyed on `is not None`.

Plus: the scan states its own denominator (every matched artifact lands in exactly one
bucket, and a fall-through is itself a problem), and one side of a reported difference is
truncated at 160 chars — presentation only, after a live artifact rendered
`artifact_usage` as a ~6 KB line.

### The live finding, re-measured — it NARROWS

Same corpus, same 30 artifacts `[本次实测 2026-07-31]`:

```
30 scanned — 15 carry BOTH copies, 15 canonical-only, 0 legacy-only,
0 no stamp, 0 malformed, 0 unreadable
```

Two artifacts disagree — `panel-ltr.alpha158_fund.previous.json` and
`panel-ltr.alpha158_fund.weekly_rollback_2026-07-06.json`, identically. The eight-field
check reported "they disagree on `passed`". The complete walk reports **57 paths**, and
decomposing those is what makes the finding precise rather than merely bigger:

| | count |
|---|---:|
| present canonically, **absent** from legacy | **53** |
| present in legacy, **absent** canonically | **3** |
| present in **both** and holding different values | **1** |

- The **one** genuine value conflict is `passed`: **canonical `False`, legacy `True`**.
- The **three** legacy-only keys are exactly the override provenance —
  `gate_verdict_before_override`, `operator_authorized_override`, `override_reason`
  (the reason names an operator authorization dated 2026-07-05, citing 3/3 positive cuts
  and an APY lag of −5.7% vs SPY).

**So the legacy copy is not a stale duplicate of the canonical one — it is a different,
smaller schema.** The canonical block records the gate's own verdict (`passed: False`)
and carries the richer diagnostics, but **no override provenance at all**. The legacy
block records the post-override verdict (`passed: True`) together with who authorized it
and why.

**The precise statement.** Neither copy alone is complete. A canonical-first reader sees
`passed: False` and cannot see that the failure was knowingly overridden; a legacy reader
sees `passed: True` and cannot see what the gate objected to. The override itself is
documented — this is **not** evidence of an undocumented promotion, and this document does
not claim one.

**What this does not do:** it does not reconcile the two copies, and it does not decide
which one a consumer should read. It reports. Retiring R8 needs the producer to stop
writing two schemas; that is a change in the gate, not here.

18 tests pass — including the two fixtures codex asked for (an unlisted-field difference,
and a malformed copy in each position) and an anti-vacuity case where two identical
blocks are still clean.

## ROUND 3 2026-07-31 — the last fail-open: a non-object JSON root

Reviewed `[codex on orch#687]`: *"a JSON file whose top-level value is not an object …
`scan` increments `unreadable` and continues without appending a problem, so a scan
containing only a valid JSON array exits zero while the summary admits one unreadable
artifact."*

Correct, and the sharp part is **which two surfaces disagreed**: the summary said
`1 unreadable`, the exit code said `0`, and a scheduled job reads the exit code. A parse
that yields a non-object is exactly as uninspectable as a parse that raises, and is now
reported the same way.

Four regressions: a JSON **array** root and a **scalar** root each raise a problem naming
the actual type; the **exit code** is driven directly (`main(...) != 0`) because the
finding was a contradiction *between* surfaces, so one surface alone cannot pin it; and an
anti-vacuity case where a valid object root still exits `0`.

22 tests pass.
