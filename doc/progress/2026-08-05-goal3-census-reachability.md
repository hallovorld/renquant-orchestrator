# 2026-08-05 — GOAL-3: which duplicate definitions can a caller actually reach, and from where?

## Why

The census's duplicate names are a **work list, not findings**. What separates a
harmless internal candidate from a readability risk is whether a caller refers
to the name at all, and — the actual question — whether different callers reach
**different definitions**.

## Two review rounds, and the second one moved the numbers

**Round 1 — the scan only covered `src/`.** `tests/` imports several names I had
classified as never imported (`AdmittedName` among them). A reachability figure
computed over the package alone is not a reachability figure. Scan roots became
`src/`, `tests/`, `scripts/`, `ops/`. `[codex]`

**Round 2 — source identity.** The scan still counted every
`from MODULE import NAME` **by name alone**, so an unrelated module exporting
the same name made a duplicate look reachable, and two of them made it look
MULTI-SOURCE. `[codex]`

That is not hypothetical. Four such credits existed in the live packages
`[VERIFIED — this session]`:

| duplicate name | was credited to | what that module actually is |
|---|---|---|
| `optimal_block_length` | `arch.bootstrap` | a **third-party library** |
| `expected_max_sharpe` | `renquant_common.metrics.deflated_sharpe` | a **different repo** |
| `compute_perf_triple` | `renquant_common.metrics.perf_summary` | a **different repo** |
| `analyze` | `scripts.analyze_trade_decision_attribution` | an unrelated script |

## What changed, both directions

Permitted modules are now derived from each name's **own `sites`**, plus
ancestor packages and shim modules **verified** to re-export it (one hop, and
the limit is stated rather than left to be found). Relative imports are
normalised against the importing file's package. Anything else is recorded in
`foreign_import_sources` — **reported, never credited**. And reachability now
counts **distinct sites reached**, not import strings, because that is the
question being asked: could a reader expect one definition and get the other?

`[VERIFIED — this session]`, `no-import / one-source / MULTI-SOURCE`:

| package | duplicates | before | after |
|---|---|---|---|
| `renquant_pipeline` | 24 | 1 / 2 / 21 | **1 / 8 / 15** |
| `renquant_backtesting` | 34 | 18 / 13 / 3 | **20 / 7 / 7** |
| `renquant_orchestrator` | 42 | 17 / 10 / 15 | **17 / 11 / 14** |

It corrects in **both** directions, which is the sign it is measuring identity
rather than just tightening:

- **False MULTI-SOURCE removed.** `build_report`'s two "sources" were
  `renquant_orchestrator.attribution` and `…attribution.report` — the package
  re-exporting its own single definition. Two aliases of one definition are not
  a fork.
- **False one-source revealed as a real fork.** `annualized_sharpe` and
  `probability_of_backtest_overfitting` looked single-sourced only because two
  *different* files both appeared as the bare relative string
  `deflated_sharpe` / `pbo`. They genuinely reach
  `metrics/…` and `forensics/metrics/…` — a real twin the old counting hid.

A latent bug fell out of the same work: `from .x import y` inside
`pkg/sub/__init__.py` is relative to `pkg.sub`, not `pkg`. Resolving it one
level too high is how `renquant_backtesting.metrics.deflated_sharpe` was read as
the non-existent `renquant_backtesting.deflated_sharpe` and its importers scored
as foreign. Regression test added.

## Scope, stated because the first version overclaimed

This counts `from X import NAME` sites. It does **not** see `import X` +
`X.NAME` attribute access, star imports, `importlib`, lazy `__getattr__`
re-exports, or callers in other repositories. A name with no importers means
**"not imported by name anywhere this scan can see"** — narrower than
"unreachable", and the renderer says so on the line itself.

It is also still NOT the pipeline guard's relation (`__all__` export ↔ same-named
definition under `kernel/`). The two counts must not be compared.

Suites: 31 tests, incl. the unrelated-same-name regression, the alias-vs-fork
case, the `__init__` relative-resolution regression, and the live breakdown
pinned exactly · full suite green.
