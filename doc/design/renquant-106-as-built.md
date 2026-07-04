# RenQuant-106 As-Built Architecture

> Signal evolution serving path. This documents **what is implemented** as of
> 2026-07-04. The experiment framework is delivered; signal candidates have
> been measured and mostly REJECTED or remain UNADJUDICATED.

## Purpose

106 is the systematic program for finding and validating new signal features
beyond the current alpha158 panel. It encompasses: the PIT (point-in-time) data
pipeline, the experiment framework (expkit), the M-SIG signal stack, and the
evidence governance that gates any new feature into production.

## Architecture

```
Data sources
  → PIT revision features (C1, renquant-base-data)
  → analyst/fundamental features (FMP Starter, renquant-base-data)
  → alpha158 panel (existing, renquant-base-data)
  ↓
Experiment framework (expkit, renquant-orchestrator)
  → pre-registration (freeze-first)
  → evaluation (placebo-clean IC, matched admission)
  → block bootstrap statistics
  → evidence manifests + verdicts
  ↓
M-SIG signal stack (spec + frozen prereg per candidate)
  → C1 revision drift (PIT clock 2027-01)
  → C2 quality (REJECTED on free-tier)
  → C3 residual momentum (UNADJUDICATED)
  → C4 trend-scan (INCONCLUSIVE)
  ↓
G106 gate: ≥2-of-4 candidates PASS → signal enters production scorer
```

## Key Modules

### renquant-orchestrator (expkit)

| Module | Role |
|---|---|
| `expkit/prereg.py` | Pre-registration: frozen spec, git-history-aware assert that spec committed BEFORE results |
| `expkit/evaluation.py` | Evaluation: per-date IC, placebo-clean differences, matched admission rate, forward excess |
| `expkit/stats.py` | Block bootstrap with small-n auto-refusal, paired deltas |
| `expkit/evidence.py` | Evidence manifests: content hashing, git provenance, manifest verification |

### renquant-base-data

| Module | Role | Status |
|---|---|---|
| `pit_revision_features.py` | C1 PIT revision-drift feature pipeline (strict PIT discipline) | Code delivered; PIT clock set to 2027-01 (data accrual pending FMP Starter) |
| `transformer_corpus.py` | TRUE panel recipe (B1 fix: unified train/serve) | Delivered |
| `rawlabel_sidecar.py` | Raw label recipe with NaN-extension to bar frontier | Delivered |
| `alpha158_ops.py` | Unified train/serve alpha158 operators (B8 fix) | Delivered |

### renquant-orchestrator (collectors, scheduled)

| Module | Role | Status |
|---|---|---|
| `intraday_quote_logger.py` | Tick feed for 105's class-D (also serves 106's intraday features) | Active |
| PIT snapshot job | Daily estimates snapshot for C1 data accrual | Installed (launchd) |
| FMP harvest | `scripts/fmp_harvest/` in base-data; FMP Starter subscribed | Authorized |

## M-SIG Signal Stack

The signal stack (spec: `doc/design/2026-07-02-m-sig-signal-stack-spec.md`) defines
four pre-registered candidates with frozen criteria:

| ID | Candidate | Verdict | Evidence |
|---|---|---|---|
| C1 | Revision drift (estimate revision timing) | **PENDING** — PIT clock 2027-01; data accruing | No measurement yet; FMP Starter data flow active |
| C2 | Quality (ROE, gross profitability, asset growth) | **REJECTED** on free-tier fundamentals | Reproduction at 1e-13; ADDS value in BULL_CALM only, HURTS in BULL_VOLATILE → no global retrain |
| C3 | Residual momentum (stock vs sector/beta/momentum) | **UNADJUDICATED** — mechanical MISS on non-PIT substrate | Placebo-clean −0.0040 vs +0.015 bar; formal vote NOT cast; needs PIT-clean rerun |
| C4 | Trend-scan label | **INCONCLUSIVE** — frozen as C4 with prior evidence labeled retrospective | Pre-repair WF harness caveats; runs on repaired WF gate (S1–S3) |

G106 composite gate: ≥2-of-4 must PASS (currently 0 PASS, 1 REJECT, 1 UNADJUDICATED,
1 INCONCLUSIVE, 1 not-yet-measured → G106 structurally NOT clearable today).

## Evidence Hierarchy and Prereg Discipline

The S-REL program governs all 106 experiment evidence:

1. **Freeze-first**: hypothesis, thresholds, family size, seeds, evidence boundary,
   reopening conditions committed BEFORE any measurement
2. **Placebo-clean differences only**: ~+0.04 embargo floor on absolute IC means
   only DIFFERENCES between treatment and placebo are trusted
3. **Block bootstrap**: with small-n auto-refusal (the expkit refuses to compute
   p-values when bootstrap atoms < threshold)
4. **Mandatory dual controls**: positive control (known-good signal) + negative
   control (shuffled label) must both fire correctly
5. **Evidence manifests**: content-hashed, git-provenance-stamped, machine-verifiable
6. **Verdict taxonomy**: PROVISIONAL → IN FLIGHT → UPHELD / WEAKENED / OVERTURNED /
   SETTLED-BY-REVIEW — tracked in `doc/research/VERDICTS.md`

## Standing Verdicts Relevant to 106

See `doc/research/VERDICTS.md` for the full ledger. Key items:

- Label neutralization: **REJECTED** (destroys BULL_CALM)
- Fundamental momentum: **REJECTED** on free-tier (reopening path = C2 on FMP Starter data)
- Trend-scan: **CAVEATED-PROMISING**, superseded by C4 frozen prereg
- Phase −1 intraday alpha: **NO-GO** (net edge negative)
- Canonical price-trend: **NULL** (all momentum factors fail 20/60d bar)

## Current Status

- expkit framework: DELIVERED (4 modules, integrated with S-REL)
- M-SIG spec: MERGED and frozen
- C1 data pipeline: ACTIVE (collectors installed, PIT snapshots accumulating)
- C2: CLOSED (rejected)
- C3: BLOCKED on PIT-clean substrate
- C4: BLOCKED on repaired WF gate
- G106: NOT CLEARABLE with current evidence
- Track B (the only remaining directional path): requires PIT earnings-surprise
  data with genuine `acceptedDate` source

## Cross-references

- [104 as-built](renquant-104-as-built.md) — 106 experiments target 104's scoring pipeline
- [105 as-built](renquant-105-as-built.md) — signal quality from 106 feeds 105's class-A inputs
- [107 as-built](renquant-107-as-built.md) — S-REL governs 106's evidence; VERDICTS.md is shared governance
