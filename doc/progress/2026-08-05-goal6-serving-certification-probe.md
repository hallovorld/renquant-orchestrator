# 2026-08-05 — GOAL-6: does each serving artifact make a claim that can be CHECKED?

## Why

orch#726 filed three defects against the serving artifacts on 2026-08-01.
Re-measuring today `[VERIFIED — this session]`: **two were already fixed** (the
prod manifest and the override rollback no longer point at a vanished `/tmp`
path) and **one was unchanged** (the clf lane carries no `wf_gate_metadata` at
all, in either the canonical or the legacy location).

Nobody noticed either fact for four days, because checking meant reading two
artifacts by hand. **A three-claim P0 sitting two-thirds fixed is how a reader
learns to discount P0s.**

## What the probe answers

One question per serving artifact: **does it make a walk-forward claim that can
be checked at all?** It deliberately does NOT judge the claim — fold counts are
counts of manifest rows and say nothing about leakage or quality. Establishing
that a claim EXISTS is a different, prior question, and conflating them is what
let one lane's 43 folds read as coverage for a lane with zero.

## Live result `[VERIFIED — this session]`

| artifact | state |
|---|---|
| prod panel (XGB recipe) | **CLAIM_POINTS_AT_A_MISSING_PATH** — 1 of 64 refs: `config_parity.candidate_artifact` → `…weekly_20260802T170002Z.staging.json`; a further 1 ref is path-shaped but unresolvable |
| clf top-decile fwd60 (shadow member) | **NO_GATE_STAMP** |

## Two review rounds, and the second is the interesting one

**Round 1 — enumerating keys was the bug.** v1 checked `/tmp` strings plus two
manifest keys, and therefore reported the live prod artifact as *checkable* while
`config_parity.candidate_artifact` dangled. Fixed by inverting the default:
walk the whole stamp, treat anything path-shaped as a reference that must
resolve. `[codex]`

**Round 2 — the wording outran the matcher.** v2 said it walked "every
path-shaped string". It did not: the regex took only POSIX absolute or
dot-relative strings ending in one of six extensions. It missed bare relatives,
extensionless paths, other extensions, Windows paths and `file://` URLs, and it
*accepted* globs it cannot resolve. **A recogniser that silently drops a
reference is the same fail-open the inversion was meant to close** — the state
depends on it, so this was never only wording. `[codex]`

Measured on the live prod stamp: the v2 matcher saw **59 of 64** references.
The 5 it dropped `[VERIFIED — this session]`:

- an extensionless trace directory `…/wf_trade_traces/20260802T170340Z`
- three `.md` fold reports under it
- one bare relative config path
  `artifacts/diagnostics/wf_eval_configs/…prod_semantic.json`

## The contract now, stated exactly

A string is a **reference** iff, stripped and non-empty, it is a `file://` URL,
or rooted (`/…`, `./…`, `../…`, `~/…`, `C:\…`, `\\host\share`), or
separator-bearing with an extension on its last segment, or bare but carrying an
artifact extension. Each reference is classified **three** ways, never two:

- **RESOLVABLE** — an absolute POSIX path this box can stat;
- **UNRESOLVABLE** — path-shaped but not checkable *here*, with the reason
  named: relative to an unstated base, a glob, a Windows path, a remote scheme;
- **not a reference** — everything else.

`UNRESOLVABLE` is **actionable**. A reference this probe cannot check is not a
checked one, and reporting it as a checkable claim is exactly the failure the
inversion exists to prevent. Note this also closes a latent v2 bug: `./x.json`
was stat'ed against the process CWD, so the answer depended on where you stood.

**The declared limit, named so it is read rather than discovered:** a
separator-bearing string with no extension on its last segment (`relative/noext`,
`n/a`, `1x/2x/3x`, `2026/08/05`) is NOT treated as a reference. It is
indistinguishable from an ordinary identifier, and turning identifiers into
dangling paths is the false positive that discredits the probe. Twelve
classified cases and eight declared non-references are pinned by name in the
suite.

A dangling path outranks an unresolvable one for the row's state, but **never
erases it** — the weaker finding stays on the record, because a worse finding
swallowing a lesser one is how two-thirds-fixed P0s stay invisible.

## Not claimed

Read-only. No schedule, no artifact touched, and no judgement of any claim's
quality — only whether it exists and resolves.

**Round 3 — a valid JSON root is not an artifact.** `json.loads` succeeding
says nothing about shape: `[]`, `null` and scalars are all valid JSON, and
`_gate_stamp` reached `.get` on them. That raised `AttributeError` and took
down the **whole probe** — so one malformed artifact reported no state for
*either* serving artifact, which is strictly worse than reporting a bad one.
The root is now validated before it is reached into, and a non-object root is
`STAMP_MALFORMED` (broken, not uncertified). `[codex]`

Suites: 43 tests, incl. five non-object roots by name and the
one-malformed-artifact-does-not-hide-the-other case · full suite green.
