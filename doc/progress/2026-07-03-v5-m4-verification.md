# V5 verification — M4 intercept finding: verdict UPHELD (both parts)

STATUS:   COMPLETE — **(i) fidelity+laundering UPHELD; (ii) M4-b premise
          UPHELD with one scope refinement.** The M4 intercept finding
          (renquant-pipeline PR #162 shadow replay, committed evidence
          `doc/evidence/2026-07-02-bl1-recenter-shadow-replay.json`)
          survives an adversarial independent recomputation whose mandate
          was to overturn it. Every load-bearing number reproduces exactly:
          neutral_raw −0.29021485236669337 to the last digit; fidelity
          max|Δ| ≤ 4e−18 on 07-01/02 (their "0.0" is genuine) and matches
          their earlier-day vintage-drift values to 7 decimals; laundering
          45/44/43/46/26/23 exact, 100% one-directional (raw<0 ∧ μ>0), and
          cross-checked against the prod-written BL-2 counters in
          `pipeline_runs.counters_json` (45/44 exact on current-vintage
          days); admission collapse 22→1/17→1/18→1/18→0 exact AND robust to
          center choice (mean-center, cand+holdings center: still 0–1 on
          all four drifted runs). Read-only on all inputs; no git anywhere
          near the live tree.
WHAT:     `scripts/v5_m4_intercept_verification.py` — independent code, not
          a rerun: own pure-Python interpolation of the calibrator JSON
          knots + own zero-crossing scan (no pipeline imports), own DB
          queries, own run selection (same 6 run_ids re-derived), horizon
          60==native verified from stored columns. Intercept decomposition
          quantified: the recentering removes a near-uniform +2.0–2.1%
          additive term (per-name shift std ≤0.0012); the floor sat
          0.63–0.76σ above the cross-section median before vs 2.3–2.4σ
          after; re-expressing the floor relative to the median restores
          the admission set (23/19/20/18 vs 22/17/18/18) — the 0.03 floor
          was gating the intercept, not conviction. Wording nit: PR says
          "+2–3%", measured is ≈+2%. Evidence (input content hashes + code
          sha stamped, S-REL convention):
          `doc/research/evidence/2026-07-03-v5-m4-verification/verification.json`;
          memo: `doc/research/2026-07-03-v5-m4-verification.md`.
WHY/DIR:  Vintage-window ruling: the intercept regime begins 2026-06-26 and
          is a +0.25 RAW-score cross-section shift (median raw −0.297 →
          −0.047), NOT the 2026-07-01 calibrator re-stamp (vintage drift
          bounded ≤0.0035 μ across all six runs; the intercept already
          exists in stored prod μ on 06-26/30 under the old vintage). So
          M4-b's premise is bound to the current drifted RAW-scorer regime
          — evidence window **4 full runs** (06-26..07-02, +3 thin 06-29
          runs) — not to the calibrator vintage. If the raw center reverts
          to the anchor (as on 06-22..06-25), enabling the flag alone
          changes ~nothing. PR #162's enable-protocol conclusion (re-derive
          mu_floor as relative conviction before flipping) is correct under
          both regimes. Root cause of the 06-26 raw shift (scorer
          trained_date unchanged 2026-05-18; coincides with the 06-25/26
          feed-rebuild/hotfix ops window) flagged for follow-up, out of V5
          scope.
