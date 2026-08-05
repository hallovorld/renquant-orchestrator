# 2026-08-05 — GOAL-3: an internal duplicate-definition census, and the guard's missing root

## What this is, after review

**Two separate things, kept separate** `[codex on orch#814]`:

**(a) A duplicate-definition CENSUS.** Per package: which module-level public
names are defined in more than one file, and whether the bodies are identical
(a copy — divergence risk) or differ (the twin shape — which one does a caller
reach?).

**(b) One contract-faithful fact about the guard**, needing no new machinery
`[VERIFIED — 2026-08-05]`: **`renquant-pipeline` is the only repo with a
`kernel/` root at all.** Its guard's relation is *export ↔ same-named definition
under `kernel/`*. Everywhere else that relation is **UNDEFINED — not "passes",
not "clean", undefined** — so "install the guard there" is not yet a well-formed
proposal.

### What I had to withdraw

My first version reported a **"guard subject coverage"** percentage (`__all__`
over all module-level public defs: 3/949 = 0.3% for the orchestrator) and framed
the census's duplicates as what the guard "cannot see". Both are wrong, and
codex was right to block them:

- the census's all-files same-name scan is **not the guard's relation**, so its
  20 pipeline collisions are **not** a positive control for the guard, and its
  counts must never be compared with the guard's;
- the coverage percentage compared **the documented API against unrelated
  internal names** — a ratio of two things that are not about each other.

Both are removed from the tool, its output, this document and the tests, and a
test keeps them removed.

## The census, measured `[VERIFIED — this session]`

| repo | `__all__` | public defs | duplicate names | also exported | `kernel/` root |
|---|---|---|---|---|---|
| renquant-pipeline | 56 | 836 | 24 | 20 | **present** |
| renquant-orchestrator | 3 | 949 | **42** | 0 | absent |
| renquant-backtesting | 2 | 348 | 34 | 0 | absent |
| renquant-base-data | 7 | 261 | 30 | 0 | absent |
| renquant-execution | 125 | 132 | 1 | 0 | absent |
| renquant-common | 53 | 152 | 0 | 0 | absent |
| renquant-strategy-104 | 2 | 13 | 0 | 0 | absent |

## The candidates, and the negative result

Shapes in the orchestrator `[VERIFIED — body digests]`: `BuildAlpha158PanelTask`
(fund 13 L vs linear 15 L, different bodies), `RefitCalibratorTask` (fund 18 L vs
patchtst 23 L), `RetrainJob` in four files, `EmitJob` identical
(`21f0b25f6e90`) in two manifest builders.

**None of them is a twin.** `[VERIFIED — codex on orch#814, reading the call
sites]` Each is instantiated only by its own module-local job
(`retrain_alpha158_linear.py:146-153`, `retrain_alpha158_fund.py:1581-1593`,
`retrain_patchtst.py:322-330`) — no caller shadowing, no "which copy runs"
ambiguity. Same-named Tasks in separate retrain modules.

**Of the four candidates actually read, zero are twins.** A duplicate is where
you start reading, not a finding, and the tool says so in its own output.

## The near-miss worth recording

My first measurement parsed `__all__` with `ast.literal_eval` and reported
**zero duplicates in every repo, including pipeline** — a clean bill of health.
The positive control caught it: pipeline is *known* to have ~20, so a method
finding none there is broken. `__all__` is built dynamically in that package,
`literal_eval` returned `[]`, and `if not names: continue` skipped the repo
silently. **A silent skip is a vacuous pass.**

And the control is now **in the suite, not only in this paragraph**: I had
described it in prose while the tests checked only loose thresholds on this
repo, so a regression to the dynamic-`__all__` failure would still have passed.

## NEXT

The useful next step is **not** "install the guard elsewhere" — that proposal
does not parse without a counterpart root. It is to decide, per repo, whether a
public/internal split like pipeline's is even the right shape, and separately to
read down the census's candidate list (the retrain Tasks first, since they sit
on the model-production path).

Suites: 14 tests · 5638 passed, 2 skipped repo-wide.
