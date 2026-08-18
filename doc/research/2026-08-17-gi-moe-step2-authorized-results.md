# G-I MoE step 2 — the AUTHORIZED one-shot IC screen: 0 of 3 not flagged

STATUS: **the authorized run under the frozen spec — the one-shot budget is now
SPENT.** Spec: `doc/research/2026-08-17-gi-moe-step2-ic-screen-spec.md`
(orch#987, merged). Runner: the corrected, reviewed script merged in orch#990,
executed VERBATIM from orchestrator main `252fa4f6` — zero edits, zero added
parameters. One execution; these numbers are final for this corpus. The
sequencing the spec §7 requires (spec merged → runner committed AND reviewed →
run) held for the first time: the pilot could not claim it, this run can.

DATE: 2026-08-17 (run at 2026-08-18T00:25:22Z, runtime 104.5 s
`[VERIFIED — results JSON run_utc/runtime_sec]`).

SEMANTICS (spec §1): the screen **TRIAGES** — it neither kills nor admits.
FLAGGED = deprioritised in the #984 §5b queue and a point-in-time-universe
rerun is required before any kill decision. NOT FLAGGED would have meant only
"not obviously dead". **Nothing below kills any candidate.**

PROVENANCE: every number is `[VERIFIED — read from
doc/research/data/2026-08-17-gi-moe-screen-results.json /
…-ic-series.csv as written by this run]` unless tagged otherwise.
Runner identity: `doc/research/data/2026-08-17-gi-moe-screen-derivation.py`,
byte-identical to orchestrator main `252fa4f6` (git blob `59cbc99e`, file
sha256 `f4f19683d5641dbc1555436d061111d7c5b24646ac6a72de7cf5a5638f2adc4f`)
`[VERIFIED — `git diff --quiet origin/main -- <runner>` clean + shasum,
computed BEFORE execution]`. The results JSON carries no runner digest (the
frozen runner could not be edited to add one — orch#990 NEXT item 2 remains
open); this externally-computed digest is the substitute.

## 1. VERDICTS (h=20, the frozen §5 rule — FINAL for this corpus)

| candidate | Δ = mean(gen)−mean(plac) | block-t (89 blocks) | % pos blocks | verdict |
|---|---|---|---|---|
| `high52w` | +0.00799 | 0.483 | 48.3% | **FLAGGED** (t < 1.0 AND pos ≤ 50%) |
| `lowbeta` | +0.00432 | 0.819 | 49.4% | **FLAGGED** (t < 1.0 AND pos ≤ 50%) |
| `quality_gp` | +0.00270 | 1.045 | 49.4% | **FLAGGED** (pos ≤ 50%) |

**0 of 3 not flagged.** No candidate proceeds to the #984 §5b manifest freeze
on this screen. All three are deprioritised; under spec §1/§2 each may only be
killed after a point-in-time-universe rerun (for `lowbeta` and `quality_gp`
especially, the spec's survivorship analysis says the current-watchlist corpus
may UNDERSTATE them — a flag here is not evidence of death).

`quality_gp` is the near-miss: Δ > 0 and block-t 1.045 ≥ 1.0 both held; it
flags on the block-majority criterion alone (44/89 positive blocks, needed
> 44.5 `[DERIVED — 0.4944 × 89]`).

## 2. Pilot vs authorized — what the pairing correction changed

The pilot numbers below are the WITHDRAWN run of the pilot-era runner
(commit `52d198c0`, results committed at `da9b05bb`, in-tree before this PR)
`[VERIFIED — read from the da9b05bb version of the results JSON /
doc/research/2026-08-17-gi-moe-step2-screen-results.md]`. They are shown for
contrast ONLY — they carry no verdict weight and are not blended into any
number above. Input digests are IDENTICAL between the two runs (watchlist
`d93d28c5…`, sec_fundamentals `aa5b06e3…`, SPY `68665523…`, OHLCV
digest-of-digests `96a1050d…` `[VERIFIED — pins blocks of both JSON
versions]`), and the emitter pin is the same `74c22647`, so every difference
in this table is attributable to the paired-cross-section correction (G7) and
nothing else.

| candidate | Δ pilot → authorized | block-t pilot → auth | % pos pilot → auth | outcome pilot → auth |
|---|---|---|---|---|
| `high52w` | +0.00863 → +0.00799 | 0.528 → 0.483 | 49.4% → 48.3% | FLAGGED → FLAGGED |
| `lowbeta` | +0.00495 → +0.00432 | 0.911 → 0.819 | 50.6% → 49.4% | FLAGGED → FLAGGED |
| `quality_gp` | +0.00417 → +0.00270 | 1.443 → 1.045 | 51.7% → 49.4% | **NOT FLAGGED → FLAGGED** |

Every Δ moved DOWN under pairing — the direction consistent with codex's HIGH
finding on orch#990: the unpaired legs let a lag-dependent coverage difference
appear as signal. For `quality_gp` the artifact was worth ~35% of its measured
Δ (+0.00417 → +0.00270 `[DERIVED]`) and the whole of its pilot pass: the
pilot's "1/3 not flagged" was a composition artifact, not a candidate
property. The screen's answer changed from 1/3 to **0/3**.

Measured size of the removed confound (per-leg minus shared-leg coverage,
telemetry columns in the CSV): at h=20 the genuine leg averaged +0.33 more
names than the placebo leg for `high52w`/`lowbeta` (max +4, nonzero on
76/359 dates) and −0.53 for `quality_gp` (range −9..+2, nonzero on 142/359
dates); at h=60 the gaps grow to +1.01 / −1.48 mean (max +6 / range −12..+4)
`[VERIFIED — aggregated from the CSV telemetry columns]`. Note the
`quality_gp` gap is NEGATIVE (the lagged leg covered MORE names — fundamental
snapshots age past MAX_AGE_DAYS at the genuine date while still fresh at the
lagged date), so the defect was not even sign-stable across candidates.

## 3. Per-horizon detail

Mean ICs are levels and carry the ~+0.04 embargo-leakage caution — only the
genuine−placebo DIFFERENCE is decision-relevant (spec §3).

### h=20 (primary; 359/359 weekly obs kept; 89/89 blocks with data)

| candidate | mean IC genuine | mean IC placebo | Δ | block-t | % pos blocks |
|---|---|---|---|---|---|
| `high52w` | −0.00954 | −0.01753 | +0.00799 | 0.483 | 48.3% |
| `lowbeta` | −0.05073 | −0.05504 | +0.00432 | 0.819 | 49.4% |
| `quality_gp` | +0.01193 | +0.00923 | +0.00270 | 1.045 | 49.4% |

### h=60 (informational ONLY, never decisive; 359/359 kept; 29/29 blocks)

| candidate | mean IC genuine | mean IC placebo | Δ | block-t | % pos blocks |
|---|---|---|---|---|---|
| `high52w` | −0.02992 | −0.02067 | −0.00925 | −0.364 | 55.2% |
| `lowbeta` | −0.10315 | −0.12228 | +0.01913 | 1.291 | 69.0% |
| `quality_gp` | +0.00629 | −0.00547 | +0.01176 | 1.323 | 55.2% |

Annotation-grade (n_eff≈16 at h=60, spec §4): `lowbeta`'s Δ again strengthens
with horizon while its IC LEVEL stays strongly negative in both arms — the
pattern the spec's survivorship caveat predicts for it. `quality_gp` remains
the only candidate with positive genuine levels at both horizons, and its
h=60 Δ (+0.01176, t=1.323) is the strongest informational signal in the
table. `high52w`'s Δ is again sign-unstable across horizons —
noise-compatible.

## 4. Coverage and dropped dates

Zero dropped dates: all 359 cross-sections passed the ≥50 PAIRED-names floor
for every candidate at both horizons (`dropped = {floor_paired: 0,
degenerate: 0}` in every cell); 89/89 (h=20) and 29/29 (h=60) blocks have
data. Minimum shared cross-section over all kept dates: 128 names
(`high52w`/`lowbeta`, h=20), 67 (`quality_gp`) `[VERIFIED — CSV
n_pairs_shared min]`. Per-date coverage (median n_scored): high52w 143,
lowbeta 143, quality_gp 73 — identical to the pilot.

## 5. ρ matrix (informational — the |ρ|<0.7 gate is APPLIED at #984 §5b, not here)

Mean per-date cross-sectional Spearman ρ over 359 dates (sd in parens):

| candidate | vs `mom_slow_12m` (v0) | vs `mom_fast` (v1_fast) | vs `multifactor_core` |
|---|---|---|---|
| `high52w` | +0.439 (0.192) | +0.513 (0.156) | NAMED GAP (§6) |
| `lowbeta` | +0.046 (0.251) | +0.010 (0.311) | NAMED GAP (§6) |
| `quality_gp` | +0.087 (0.152) | +0.031 (0.168) | NAMED GAP (§6) |

Unchanged from the pilot to 3 decimals — expected, since the ρ matrix uses
genuine scores only and was never touched by the pairing correction.
`high52w` remains momentum's closest sibling (≈0.44–0.51 against both
momentum clocks, under the 0.7 bar); `lowbeta` and `quality_gp` are
near-orthogonal to the momentum lanes.

## 6. Named gaps (recorded, not fabricated)

1. **`multifactor_core` ρ column** — no committed/reachable historical score
   series on the corpus dates without running the panel pipeline
   (`score_db.sqlite` empty; run bundles 2026-only); deferred to the #984 §5b
   Stage-A batch (recorded inside the results JSON itself).
2. **Point-in-time universe** — inherited from spec §2: the corpus is the
   current 145-name watchlist, survivorship-tilted for 2019-era
   cross-sections; this is why FLAGGED ≠ killed, for all three candidates.

## 7. Guard outcomes and deviations (reported, not papered over)

- **All G1–G12 guards passed**; the runner exited 0 on its single execution
  `[VERIFIED — run log, exit code 0]`. No fix-and-rerun occurred; no
  parameter was touched; the script ran once and only once.
- **G1 (359 vs 358)**: the frozen every-5th-trading-day RULE yields 359
  cross-sections on the 1,792-day window; the spec's derived count said 358.
  The rule governs; the discrepancy is asserted tight (|n−358| ≤ 1) and
  reported by the runner itself in the results JSON. Nothing dropped.
- **In-tree outputs replaced**: this PR overwrites the pilot's retained
  JSON/CSV at `doc/research/data/` with the authorized run's outputs (the
  runner writes fixed paths — frozen, not editable). The pilot's outputs
  remain recoverable at commit `da9b05bb`; the pilot memo
  (`2026-08-17-gi-moe-step2-screen-results.md`) now carries a pointer note.

## 8. Pins and reproduction

Inputs (all read-only; sha256 digests in the results JSON `pins` block):

- orchestrator main (runner source + execution base): `252fa4f6758671947dc7efc8bf9696e01c2890bd` `[VERIFIED — rev-parse origin/main at fetch]`
- runner file sha256: `f4f19683d5641dbc1555436d061111d7c5b24646ac6a72de7cf5a5638f2adc4f` (git blob `59cbc99e`) `[VERIFIED — shasum before run]`
- `renquant-model` HEAD: `74c22647a7880c6a3234e53fb5d037d82fde3faf` = the frozen model#227 merge pin exactly (G3 ancestor assert passed) `[VERIFIED — rev-parse + results JSON pins]`
- `renquant-strategy-104` checkout: `86a78b41236cfe13b2c717bf448e7282793ce8f7`, watchlist n=145, sha256 `d93d28c5…4b555` `[VERIFIED — rev-parse + pins]`
- data: OHLCV digest-of-digests `96a1050d…e746`, `sec_fundamentals_daily.parquet` `aa5b06e3…f66b`, SPY `68665523…b0ee` `[VERIFIED — pins]`
- python: `/Users/renhao/git/github/RenQuant/.venv` (numpy 2.0.2, pandas 2.3.3, scipy 1.13.1) `[VERIFIED — version probe]`
- execution: isolated worktree of orchestrator main at `252fa4f6`; wrote only
  `doc/research/data/` outputs inside the worktree; no live-tree or
  production-path writes.

The script is deterministic — no randomness, no clock in any computed number
— so re-executing it at these pins reproduces these outputs bit-for-bit
(reproduction is not a re-run of the screen; the one-shot budget is spent).

## 9. What happens next (per the merged spec, no new decisions here)

All three candidates sit deprioritised in the #984 §5b queue. The path for
any of them is the point-in-time-universe rerun (spec §2's named fix, still
deferred); no kill may be decided on this corpus. `quality_gp`'s
one-criterion miss and its h=60 informational strength are recorded facts a
future PIT rerun can confirm or dissolve — they authorize nothing today.
