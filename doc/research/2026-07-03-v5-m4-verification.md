# V5 verification — M4 intercept finding (pipeline PR #162 shadow replay): UPHELD

S-REL audit item V5. Adversarial independent verification of the M4/BL-1
intercept FINDING behind renquant-pipeline PR #162 (branch
`feat/bl1-recenter-raw`): committed evidence
`doc/evidence/2026-07-02-bl1-recenter-shadow-replay.json`, tool
`scripts/shadow_replay_bl1_recenter.py`. Mandate: try to OVERTURN the
load-bearing numbers with independent recomputation.

**Verdicts**

| Claim | Verdict |
|---|---|
| (i) Replay fidelity + laundering numbers | **UPHELD** — every number reproduces exactly with independent code; live BL-2 counters cross-check exactly on the current-vintage days |
| (ii) M4-b premise ("the 0.03 floor was gating a +2–3% drift intercept; ~0–1 admitted post-recentering") | **UPHELD with one scope refinement** — collapse 22→1 / 17→1 / 18→1 / 18→0 reproduced and robust to center choice; measured intercept ≈ **+2.0–2.1%** (the "+3%" top of their range is not observed); the premise is bound to the CURRENT drifted raw-score regime, whose evidence window is **4 full runs (2026-06-26..07-02)** |

Vintage-window ruling (check 5): the intercept regime begins **2026-06-26**
and is caused by a **+0.25 upward shift of the raw score cross-section**
(median raw −0.297 → −0.047), NOT by the 2026-07-01 calibrator re-stamp.
Calibrator-vintage drift is bounded at ≤ 0.0035 in μ across all six runs —
an order of magnitude smaller than the +0.02 intercept — and the intercept
is already present in the μ prod STORED on 06-26/06-30 under the
pre-re-stamp vintage. M4-b's premise is therefore about the current
**raw-scorer regime**, not the current calibrator vintage; on
anchor-adjacent cross-sections (06-24/25) recentering is a near-no-op and
the floor behaves as a genuine conviction bar.

## 1. Method — independent, not a rerun

`scripts/v5_m4_intercept_verification.py` (this repo). No pipeline imports:

- The calibrator's expected-return head is re-read from the live JSON
  artifact and re-implemented as **pure-Python** piecewise-linear
  interpolation (bisect + clamped ends, loader clip semantics replicated by
  reading `global_calibrator.py`, never importing it).
- `neutral_raw` re-derived by scanning the ER knot polyline for its first
  zero crossing: **−0.29021485236669337** — matches PR #162's −0.29021 to
  the last printed digit.
- Raw scores and stored prod μ come straight from `score_distribution`
  (DB opened `mode=ro`); the live BL-2 counters come from
  `pipeline_runs.counters_json` — a prod-written source their replay tool
  never read (independent cross-check).
- Run selection re-derived from their query semantics (6 most recent runs
  with ≥60 candidate rows, as-of 2026-07-02): **exact same 6 run_ids**.
- Stored `expected_return_horizon_days = mu_horizon_days = 60` on all rows
  = calibrator native horizon → no scaling term anywhere (verified, not
  assumed).

Inputs pinned by content hash in
`doc/research/evidence/2026-07-03-v5-m4-verification/verification.json`
(DB sha256 `0630ffb5…`, calibrator sha256 `cab09044…` — identical to the
sha in their committed evidence — their evidence file sha256 `f81eb7c5…`,
plus this script's own sha256). All inputs read-only; no git anywhere near
the live tree.

## 2. Checks 1–2 — fidelity and laundering: exact

| date | n | max\|Δ\| ER(raw) vs stored μ (mine) | theirs | laundered before (theirs → mine) | live BL-2 counter |
|---|---|---|---|---|---|
| 2026-07-02 | 83 | 1.7e−18 (exact) | 0.0 | 45 → **45** | **45** |
| 2026-07-01 | 83 | 3.5e−18 (exact) | 0.0 | 44 → **44** | **44** |
| 2026-06-30 | 83 | 0.0019754 | 0.0019754 | 43 → **43** | 42 |
| 2026-06-26 | 79 | 0.0018463 | 0.0018463 | 46 → **46** | 44 |
| 2026-06-25 | 76 | 0.0033291 | 0.0033291 | 26 → **26** | 24 |
| 2026-06-24 | 73 | 0.0034753 | 0.0034753 | 23 → **23** | 20 |

- Fidelity: on 07-01/02 my independent interpolation reproduces the stored
  prod μ to float-associativity noise (≤4e−18) — their "max |Δ| = 0.0" is
  genuine, and the current artifact is the one prod ran those days. The
  earlier-day diffs match theirs to 7 decimals and are honestly disclosed
  vintage drift.
- Laundering: recomputed counts match all six runs exactly, and the
  sign-disagreement is **100% one-directional** (raw<0 ∧ μ>0; the μ<0 ∧
  raw>0 count is 0 on every run) — "laundering" is the right word.
- Independent cross-check: the counters the live runs themselves persisted
  (`calibrator_sign_laundered` = 45/44 on 07-02/07-01) equal the replay
  exactly on the current-vintage days; pre-re-stamp days differ by 1–3
  names (42/44/24/20 vs 43/46/26/23) — that is the day's older calibrator
  vintage flipping near-neutral names, the same ≤0.0035 drift the fidelity
  row quantifies. Consistent, not contradictory.

## 3. Check 3 — admission collapse at mu_floor=0.03 + sensitivity

Baseline (their design: median center over candidates) and my variants:

| date | before (theirs → mine) | after median-cand (theirs → mine) | mean-cand | median cand+hold | mean cand+hold |
|---|---|---|---|---|---|
| 2026-07-02 | 22 → **22** | 1 → **1** | 1 | 1 | 1 |
| 2026-07-01 | 17 → **17** | 1 → **1** | 1 | 1 | 1 |
| 2026-06-30 | 18 → **18** | 1 → **1** | 1 | 1 | 1 |
| 2026-06-26 | 18 → **18** | 0 → **0** | 0 | 0 | 0 |
| 2026-06-25 | 5 → **5** | 6 → **6** | 0 | 0 | 0 |
| 2026-06-24 | 3 → **3** | 3 → **3** | 1 | 2 | 0 |

- The **~0–1 admission on the four drifted runs survives every center
  variant** (mean instead of median; including the 5–7 holdings rows in
  the center; both). The M4-b collapse is not an artifact of the median
  choice or of the candidates-only center.
- On the two anchor-adjacent runs the after-count is center-noise
  (06-25: 6 vs 0; 06-24: 3/1/2/0) — with a near-zero shift, admission sits
  at the μ≈0.03 boundary ≈ the cross-section max, so ±0.01 of center moves
  1–6 names. This does not weaken M4-b (those runs are the no-intercept
  regime where the flag is a near-no-op); it does mean the 06-24/25 rows
  should not be quoted as precise.
- `laundered_after = 0` on **all six runs under all four center variants**
  — the PR's acceptance metric is fully robust.

## 4. Check 4 — is "drift intercept" the right decomposition? Yes (≈ +2%)

| date | median μ before | mean μ before | floor − median (σ units) | after recenter (σ units) | removed shift/name (mean ± std) | admitted before | admitted after @ intercept-adjusted floor |
|---|---|---|---|---|---|---|---|
| 2026-07-02 | +0.0216 | +0.0189 | 0.0084 (0.63σ) | 2.31σ | +0.0213 ± 0.0011 | 22 | **23** |
| 2026-07-01 | +0.0202 | +0.0182 | 0.0098 (0.75σ) | 2.32σ | +0.0199 ± 0.0008 | 17 | **19** |
| 2026-06-30 | +0.0207 | +0.0182 | 0.0093 (0.70σ) | 2.33σ | +0.0204 ± 0.0012 | 18 | **20** |
| 2026-06-26 | +0.0206 | +0.0198 | 0.0094 (0.76σ) | 2.43σ | +0.0205 ± 0.0005 | 18 | **18** |
| 2026-06-25 | −0.0006 | +0.0042 | 0.0306 (2.10σ) | 2.06σ | −0.0006 ± 0.0000 | 5 | 5 |
| 2026-06-24 | +0.0007 | +0.0047 | 0.0293 (1.89σ) | 1.94σ | +0.0007 ± 0.0000 | 3 | 3 |

- The recentering removes a **near-uniform additive term**: per-name
  removed shift has std ≤ 0.0012 vs mean ≈ +0.020 (≤6% dispersion; the ER
  head is close to linear over the occupied span). "Intercept" is a fair
  decomposition, not a rhetorical flourish.
- Mechanism quantified: before recentering the floor sat only **0.63–0.76σ
  above the cross-sectional median** — inside the bulk (admits 20–27% of
  names); after, the median is 0 by construction and the floor is
  **2.3–2.4σ out** (admits ~0–1). On 06-24/25 the floor was ALREADY
  1.9–2.1σ out with no intercept to remove — same geometry as the
  post-recenter state, and admission was 3–5.
- The clincher: re-expressing the floor relative to the pre-recenter median
  (floor′ = 0.03 − median μ_before) restores the admission count to
  **23/19/20/18 vs 22/17/18/18 before** — the floor's entire selection on
  the drifted runs is reproduced by the intercept plus a relative bar. The
  0.03 floor was gating the intercept, not conviction.
- Wording nit: the PR's "+2–3% drift intercept" — measured is
  **+2.0–2.1% (median), +1.8–2.0% (mean)** across the four drifted runs.
  "+3%" is not observed in this window. Their own μ tables say the same
  (+0.019 mean); the prose range is mildly generous, the substance stands.

## 5. Check 5 — the 06-24/25 anomaly and the vintage window

Per-date regime timeline (candidates only, stored values — independent of
any calibrator):

| window | median raw | mean stored μ | regime |
|---|---|---|---|
| 06-09 .. 06-11 | −0.19 | +0.000 .. +0.004 | anchored-ish, no intercept |
| 06-22 .. 06-25 | −0.28 .. −0.30 | +0.003 .. +0.004 | **on the anchor** (−0.2902), no intercept |
| **06-26 .. 07-02** | **−0.036 .. −0.053** | **+0.018 .. +0.021** | **drifted, +2% intercept** (incl. 3 thin 06-29 runs, mean μ +0.021) |

- The regime boundary is **06-25 → 06-26** and it is a **raw-score
  cross-section shift** (median raw jumps +0.25). The calibrator re-stamp
  boundary is **06-30 → 07-01** (fidelity 0.00198 → 0.0; artifact
  `trained_date = 2026-07-01`, file re-stamped 07-02 15:28 together with
  the scorer artifact). These are different events three sessions apart.
- The audit hypothesis "the calibrator vintage change explains the 06-24/25
  anomaly" is therefore **refuted in direction but refined, not fatal to
  M4-b**: vintage drift moves μ by ≤0.0035 (fidelity bound, all six runs)
  and flips only 1–3 near-neutral laundering names; it cannot produce or
  remove a +0.02 intercept. The intercept exists in the μ prod stored on
  06-26/06-30 under the OLD vintage — so M4-b's premise does not depend on
  the 07-01 re-stamp.
- What it DOES depend on: the raw cross-section staying ~+0.25 above the
  pooled anchor. That state is **4 full runs old** (06-26, 06-30, 07-01,
  07-02; plus the three thin 06-29 runs). If the raw center reverts to the
  anchor (as it sat 06-22..06-25), enabling `recenter_raw_per_bar` alone
  changes ~nothing and the floor is a real conviction bar again. The
  enable-protocol consequence in PR #162 (re-derive `mu_floor` as a
  relative-conviction quantity before flipping the flag) is the right
  conclusion under BOTH regimes; the "near-sell-only if enabled alone"
  warning is regime-conditional with a 4-run evidence window.
- Root cause of the 06-26 raw shift is out of V5 scope (the scorer
  artifact's `trained_date` is unchanged at 2026-05-18; the shift timing
  coincides with the 06-25/26 ops window — fund-freshness feed rebuild,
  live-tree hotfix incident). Flagged for follow-up, not asserted.

## 6. Minor findings (non-verdict-relevant)

1. Their evidence stamps `calibrator.trained_date: null` — the replay tool
   reads `cal.metadata.get("trained_date")` but the artifact stores
   `trained_date` top-level (= 2026-07-01). Cosmetic; under-reports the
   vintage identity the fidelity row then has to carry. Worth a one-line
   fix if the tool is reused.
2. Their `sign_laundered_before` definition is `raw · μ < 0` (either
   direction); on this data it equals the raw<0 ∧ μ>0 count (the reverse
   direction is 0 everywhere), so the PR's framing is unaffected.
3. The DB is a moving prod file; my evidence JSON pins the exact bytes
   verified (sha256 `0630ffb5…`, mtime 2026-07-02T21:07:28Z, 97 MB).

## 7. Reproduce

```bash
python3 scripts/v5_m4_intercept_verification.py \
  --committed-evidence <their doc/evidence/2026-07-02-bl1-recenter-shadow-replay.json> \
  --json-out doc/research/evidence/2026-07-03-v5-m4-verification/verification.json
```
