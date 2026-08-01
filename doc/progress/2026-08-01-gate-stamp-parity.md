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
