# GOAL-2v3 Stage I-0 — the GATE RUN: PASS (BEAR n_eff_adj 191 vs bar 30)

Date: 2026-08-29 10:04–10:06 UTC (~03:05 PDT; derived from file timestamps,
see provenance). Executed with `--gate-run` from the frozen main commit
**f3d5bf7b** (Amendment A1 acknowledged by the operator, #1074), on a fresh
vendor fetch of the same 2,144-name seed (2,124 with bars + 20 empty —
identical tally to the development fetch; sha256 of every consumed bar file
is in the committed audit artifact).

**Run ID `i0-gate-20260829-f3d5bf7b`.** The bundle lives in its own immutable
directory `doc/research/data/2026-08-29-g2v3-i0-gate-run/`; the 2026-08-27
development artifacts in `doc/research/data/2026-08-27-g2v3-i0/` are
untouched (`run_status: DEVELOPMENT_ONLY`, `gate_verdict: null`).

Every gate parameter was frozen on main BEFORE this run: bar (BEAR
n_eff_adj ≥ 30 @ h=13), the AR(1) fail-closed estimator with raw ρ̂₁
reported beside the floored value, the canonical 39-slot grid, the s₀ proxy,
the trailing eligibility rule, and the A1 drift thresholds (1% name-day /
5% eligible-day breach, in declared order).

## The table (machine-readable report in the gate-run bundle; `run_status: GATE_RUN`)

| regime | n_blocks | episodes | ρ̂₁ raw → used | **n_eff_adj** | s₀ block IC |
|---|---|---|---|---|---|
| **BEAR** | 191 | 11 | −0.057 → 0.00 | **191** | +0.021 |
| BULL_CALM | 520 | 16 | +0.022 → +0.022 | 497.4 | +0.014 |
| BULL_VOLATILE | 159 | 16 | −0.100 → 0.00 | 159 | +0.011 |
| CHOPPY | 47 | 10 | −0.184 → 0.00 | 47 | +0.035 |

917 block sessions; median eligible cross-section 1,256 names; 102 names
excluded by the frozen two-layer drift rule (the development runs' 432 was
the pre-A1 all-days rate — this is the declared rule's output).

## Verdict

**`gate_verdict: PASS` — BEAR n_eff_adj = 191, 6.4× the bar.** Raw
dependence is small and mostly negative; the conservative floor changes
CALM only (520 → 497.4). Every regime clears 30, so Stage I-1 conditioning
is fundable in all states. The naive frozen proxy carries positive block IC
in every regime (diagnostic, not a gate).

Development-run indication (191, #1073) and gate run agree on the count
because the count is a property of the frozen construction; the s₀ ICs
moved slightly with the re-fetched vendor bytes (expected; hashes differ
and are recorded).

## Bundle + provenance (review r1 of #1083)

`doc/research/data/2026-08-29-g2v3-i0-gate-run/` — three files, `provenance.json`
written last; `tests/test_g2v3_gate_run_bundle_provenance.py` fails CI if any
GATE_RUN report lacks a provenance file or disagrees with it (report/audit
hashes, seed hash + count, 40-hex frozen commit, verdict cross-check,
script/design hashes, input-manifest aggregate), and if a DEVELOPMENT_ONLY
report ever carries a GATE_RUN claim.

| item | value |
|---|---|
| frozen source commit | `f3d5bf7bd75ffa9c0fb59f8c3bfa98fa509e8779` (clean tree; only the untracked bar store + outputs) |
| invocation | `G2V3_BAR_STORE=<store> caffeinate -i .venv/bin/python scripts/experiments/g2v3_stage_i0_census.py --gate-run` |
| UTC start / end | `2026-08-29T10:04:12Z` / `2026-08-29T10:06:40Z` — **derived from file timestamps** (launcher stdout birth; report mtime), the script logs no clock |
| seed list | `2026-08-27-g2v3-i0/g2v3_seed.txt`, 2,144 names, sha256 `cd6f3ed7ab1f353b21154ecb0cba4b27811927854f5a8666e62bfd86c7d9a3cc` |
| census script @f3d5bf7b | sha256 `8e6ddd6e361edcf8f6fdc0d8b02f53ee8af5418943fa081c84459f3b2386eada` |
| design doc @f3d5bf7b (carries A1) | sha256 `21678a53c593ead945193566bed4ea30c1e6f364dbfde5da8d5c49539b3808f6` |
| input manifest (audit `bar_store_sha256`) | 2,124 files, aggregate sha256 `a878f1caeaee863cc06c2f9b3ab0d6eba4389d656a4b4dabd731a1844cdfd4d9`; bar store re-hashed 2,124/2,124 match |
| `g2v3_stage_i0_report.json` | sha256 `da41a706f31b3f39b9ccc9631b93a76a6cb994c8877f112ce49989916634cf44` |
| `g2v3_stage_i0_audit.json.gz` | sha256 `dd5127d7326919b777acd0a6bf819dcc158c9cd02a44cd76ef7ca71fa844f3a9` |

The full frozen parameter block (h=13, bar, 0.01/0.05 drift in declared
order, 60/0.80 eligibility, ≥100 names per bar-time, ≥8 pairs fail-closed,
K5 regime formula, s₀ definition, window) is spelled out in
`provenance.json.frozen_parameters`.

## Next

Stage I-1 exactly as preregistered in the design (#1076, merged before this
result existed): bases B0/B1/B2/B3, feature set F, K5 XGB verbatim with the
literal seeds, five 6-month OOF folds with a 13-bar purge, life screen
block-t ≥ 1.0 at h=13 on dependence-adjusted units, overall bar only.
Evaluation window 2024-07..2026-06 remains sealed.
