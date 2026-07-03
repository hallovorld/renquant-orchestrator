# M8 cluster wave-1 NO-GO — independent adversarial verification: UPHELD

STATUS: verification memo only (no re-design). Adversarial independent check
of PR #261 (`doc/research/2026-07-03-m8-cluster-wave1.md`, verdict NO-GO,
waves stop). Mandate: try to OVERTURN it. All load-bearing claims were
re-derived with an independently written implementation
(`scripts/m8_independent_verification.py` — different IC code, different
group construction, different normalization guard; their script was NOT
rerun as the source of any verification number), plus robustness probes the
original did not run (multi-seed retrains, random-wave control,
leave-one-cut-out, alternative qualifying rules). All production data
read-only. Evidence:
`doc/research/evidence/2026-07-03-m8-verification/verification_results.json`.

**VERDICT: UPHELD.** The frozen gate's NO-GO is decisively correct: every
gate number recomputes exactly, the paired degradation is robust to training
seed (gate fails at −0.0506/−0.0159/−0.0452 across seeds 42/7/2026, all
outside the −0.010 band), the qualifying-cut rule and its data-topology
basis verify against the raw dataset, harness parity with production
holds, and the selection-window overlap is NOT outcome leakage (and is
anti-conservative for PASS, i.e., it could only have helped the wave).
One diagnostic narrative is corrected (§5 below): the incumbent-book
dilution is specific to the similarity-selected names, not a generic
breadth effect — material for any future D3 revisit, immaterial to the
gate verdict itself.

## 1. Per-check results (their number vs independently recomputed)

| # | Check | Their number | Mine (independent) | Result |
|---|---|---:|---:|---|
| 2 | mean paired Δ, qualifying cuts (fwd_60d) | −0.0477 | −0.047666 | exact |
| 2 | per-cut Δ 5 / 6 / 7 | −0.0764 / +0.0159 / −0.0825 | −0.076422 / +0.015944 / −0.082520 | exact |
| 2 | all-7-cut mean Δ | −0.0183 | −0.018344 | exact |
| 2 | placebo-clean paired Δ (qualifying) | −0.0328 | −0.032768 | exact |
| 2 | fwd_20d mean Δ qualifying / placebo-clean | −0.0171 / −0.0288 | −0.017090 / −0.028829 | exact |
| 2 | pooled date-level Δ / naive SE / n | −0.0476 / 0.0037 / 691 | −0.047574 / 0.003740 / 691 | exact |
| 2 | evidence internal consistency (40 runs, ic_mean vs per-date file) | — | max discrepancy 4.9e−07, 0 mismatches | clean |
| 1 | cut5 baseline / aug-full / aug-on-incumbents (seed 42) | +0.139812 / +0.063390 / +0.066329 | +0.139812 / +0.063390 / +0.066329 | exact |
| 1 | cut7 aug-on-incumbents dilution | +0.128→+0.061 | +0.143→+0.074 (impl-variant; dilution +0.069) | reproduced |
| 1 | frozen gate per seed 42 / 7 / 2026 | −0.0477 (seed 42 only) | −0.0506 / −0.0159 / −0.0452 — all FAIL | seed-robust |
| 4 | candidate start-date artifact | 512/683 start 2021-05-03 | 512/683 start 2021-05-03 | exact |
| 4 | per-cut wave coverage | 26/28/28/29/100/100/100 | 26/28/28/29/100/100/100 (%) | exact |
| 4 | qualifying cuts | {5, 6, 7} | {5, 6, 7} | exact |
| 4 | gate under alternative rules (all-7, ≥25%, cuts 4–7, leave-one-out ×3) | — | −0.0183…−0.0795, ALL fail the band | rule-robust |
| 5 | XGB params vs `panel_trainer.PANEL_LTR_PARAMS` + 100 rounds + label | claimed identical | identical (their extra `nthread: 8` is perf-only) | verified |
| 5 | CUTS vs umbrella `walk_forward_extended.py` | claimed identical | identical | verified |
| 5 | single shared train path for both arms; 158 features, none fwd-named | claimed | verified | verified |
| — | their exact impl reruns their committed numbers | — | cut5 and cut7 baseline: abs diff 0.000000 | deterministic |

## 2. Check 1 — training-dilution diagnostic (the decisive evidence)

Independent retrain of baseline-133 vs augmented-233 on all three qualifying
cuts, seeds {42, 7, 2026}, my own implementation:

- **Seed 42 reproduces their committed numbers exactly on cut 5** (all three
  statistics to 6 dp) — their pipeline and mine are data-identical.
- Cut 6/7 differ slightly between implementations for a diagnosed, benign
  reason: those train windows contain degenerate near-constant features
  (min feature std ≈ 5e−17); the frozen spec does not pin the normalization
  epsilon, so their `sd + 1e−9` and my zero-guard diverge on those columns
  and act as an extra seed. Their own implementation reruns their committed
  cut-7 number to 0.000000 — the committed evidence is genuine and
  deterministic.
- **Incumbent-subset dilution reproduces**: cut5 +0.073/+0.009/+0.039 and
  cut7 +0.069/+0.011/+0.056 across the three seeds (positive at every seed);
  cut6 mixed-sign, as in their own table. Caveat: the memo's headline "6–8
  IC points" is the seed-42 draw; the seed-averaged dilution is ~2–7 points
  with large seed variance.
- **The frozen gate itself fails at every seed**: −0.0506 / −0.0159 /
  −0.0452, i.e., 1.6×–5× the −0.010 band. The NO-GO is not a seed artifact.

## 3. Check 3 — selection-criterion leakage ruling

The similarity criterion reads feature ranks on 101 weekly dates in
2023-01→2024-12, which overlaps test windows of qualifying cuts 5 (2023) and
6 (2024). Argued both ways:

- *Against the design*: alpha158 features embed trailing price paths, so
  in-window feature-rank similarity conditions wave composition on realized
  2023–24 co-movement with incumbents — technically in-sample information
  about the evaluation period, and E34-literal selection was rejected for
  coverage reasons rather than principle.
- *For the design*: the criterion never touches forward labels, model
  outputs, or any performance statistic (feature-name audit: 158 columns,
  none forward-looking; labels excluded by construction), so it cannot
  select on evaluation-window IC luck. Directionally, matching in-window
  behavior to incumbents makes the wave maximally in-distribution during
  the test windows — a bias TOWARD the wave ranking well, i.e., toward
  PASS. And empirically the largest degradation is cut 7 (test 2025),
  entirely OUTSIDE the similarity window (−0.083 theirs / −0.090 mine).

**Ruling: not outcome leakage.** The overlap could only have flattered the
wave; the NO-GO is conservative against it, and the worst cut is
out-of-window. The coverage-based rejection of the disjoint-window
alternative verifies against the data (512/683 candidates start 2021-05-03;
pre-2019 coverage would be ~26%).

## 4. Check 4 — qualifying-cut rule

Recomputed from the raw parquet: coverage fractions 0.26/0.28/0.28/0.29/
1.00/1.00/1.00 → exactly cuts {5,6,7} qualify under the frozen ≥50% rule;
the 512/683 fetch-window artifact claim is exact. The gate read is
insensitive to the rule: every alternative inclusion (all 7 cuts, ≥25%
coverage, cuts 4–7, and all three leave-one-qualifying-cut-out variants)
still fails the −0.010 band (range −0.0183 to −0.0795). There is no
cut-selection path to a PASS.

## 5. Material correction to the §4 mechanism narrative (does NOT reopen the gate)

The original memo generalizes: "even the most feature-structure-similar 100
names carry enough signal-structure difference to dilute the panel fit,"
presenting the incumbent-book dilution as E34's transfer-coefficient
collapse surviving similarity selection — implying breadth per se is the
problem. A control the original did not run contradicts the generalization:

**Random-wave control** (3 draws of 100 uniformly random eligible
candidates, same harness, seed 42): random waves mostly IMPROVE the
incumbent book — aug-on-incumbents cut7 = 0.171/0.207/0.208 vs baseline
0.143 (and vs the similarity wave's 0.074); cut6 all improve; cut5 par in
2/3 draws. The full-universe gate under random waves still fails in 2/3
draws (−0.0321, −0.0144) and marginally passes once (−0.0091), mean −0.0185.

So: (a) the NO-GO on wave-1 as frozen is, if anything, reinforced — the
similarity-selected wave is distinctly WORSE than random selection
(−0.048 vs −0.0185 mean gate delta); but (b) the mechanism story is
inverted: the incumbent-book dilution is specific to the
similarity-selected names, not a generic cost of +100 breadth, so this
experiment does NOT establish "any wave would fail." Caveats on the
control: single training seed, random draws are not sector-balanced
(composition confound), and one marginal band-pass is within seed noise.
The pre-registered consequence (waves STOP; BR via D3 down-cap) binds
procedurally and is not reopened by this correction — but any future D3
synthesis should cite the gate failure of THIS wave, not "similarity-proof
dilution," as the established fact. A gate-design note for future frozen
specs: the gate statistic moves ~±0.02 across training seeds, so a
single-seed read against a ±0.010 band is under-powered for marginal
outcomes (immaterial here — wave-1 fails at every seed).

## 6. What was attacked and did not break

Arithmetic (exact to 6 dp from committed evidence, plus internal
cross-consistency of the two evidence files), determinism (their exact
implementation reruns committed numbers bit-stable), seed dependence (gate
fails at all 3 seeds), implementation dependence (independent impl, same
verdict), qualifying-rule dependence (7 alternative rules, same verdict),
selection leakage (ruled benign; worst cut is out-of-window), harness
parity (params/cuts/label match production sources byte-for-byte), and the
mechanism diagnostic (dilution reproduces exactly at seed 42, direction
survives seeds). The only finding is interpretive (§5), not decisional.

## 7. Reproduction

```bash
# umbrella venv (xgboost); ~50s total, 24 XGB trainings
/Users/renhao/git/github/RenQuant/.venv/bin/python \
    scripts/m8_independent_verification.py
```

Inputs read-only: `RenQuant/data/alpha158_816_dataset.parquet`,
`renquant-strategy-104/configs/strategy_config.json`,
`renquant-model/.../panel_trainer.py`,
`RenQuant/scripts/walk_forward_extended.py`, and the committed PR #261
evidence under `doc/research/evidence/2026-07-03-m8/`.
