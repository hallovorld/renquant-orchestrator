# PatchTST edge-recovery experiment — pre-registration

STATUS:   in-progress (experiment-prep PR; the runs launch concurrently in /tmp, isolated)
WHAT:     pre-registers two concurrent 60d PatchTST experiments + their reliability checks:
          A = reproduce B2 (exclude MIN/STD/IMIN); B = B2 + prune the pure-placebo drivers
          (IMXD/CORR/RANK/RSV/IMAX/gross_profitability/sue_signal). Judge = production WF gate.
WHY/DIR:  north star = a gate-passing 60d model so daily-full can trade again. B2 is the ONLY
          config with positive val IC (+0.024); hypothesis = prune the remaining pure-placebo
          features to clean the gate placebo while keeping the signal.
EVIDENCE: path-pinned per claim. **All sources are SESSION-LOCAL / EPHEMERAL (`/tmp`)** — they
          are *motivating* observations, not durable proof; the **authoritative** evidence for
          the decision is the forthcoming experiment gate VERDICTS, committed in the results PR.

  Claim 1 — 60d-unpruned FAILS the gate, real_ic = -0.0227.
    artifact:   backtesting/renquant_104/artifacts/walkforward_patchtst/2026-03-09/hf_patchtst_all_seed44_model.pt
    prod/exp:   experiment (fresh rebuild, not prod)
    existing:   /tmp/patchtst_gate.log → "real_ic = -0.0227" + "VERDICT: FAIL" (placebo)
    best-known: no — a control baseline
    scope:      single seed, default recipe, full WF gate, recent val slice
    [VERIFIED — /tmp/patchtst_gate.log, ephemeral]

  Claim 2 — 20d FAILS the gate (real_ic -0.0196) and is the WORST val IC (-0.07).
    artifact:   walkforward_patchtst_20d/2026-03-09/...seed44.pt; B6_label20d_pruned_seed{44,45}
    prod/exp:   experiment
    existing:   /tmp/patchtst_20d_gate.log → "real_ic = -0.0196","VERDICT: FAIL" (regime sanity);
                B6 summary.json best_val_ic = -0.0705 / -0.0698
    best-known: no — worst direction
    scope:      2 seeds (B6), full WF gate (20d corpus)
    [VERIFIED — /tmp/patchtst_20d_gate.log + /tmp/rq-b2knob/.../B6_*/summary.json, ephemeral]

  Claim 3 — B2 (60d, prune STD/MIN/IMIN) is the ONLY positive-val-IC config (+0.0040 / +0.0239).
    artifact:   /tmp/rq-b2knob/artifacts/patchtst_shadow/B2_pruned_valdays126_seed{44,45}/hf_patchtst_all_seed{44,45}_summary.json (key: best_val_ic)
    prod/exp:   experiment
    existing:   best_val_ic seed44 +0.0040, seed45 +0.0239 (every other config ≤ 0)
    best-known: YES — the lead this experiment builds on
    scope:      2 seeds; val IC only (NOT a gate pass — that is what Exp A re-tests)
    [VERIFIED — summary.json best_val_ic, ephemeral]

  Claim 4 — B2 excluded exactly 15 cols = {STD,MIN,IMIN}×{5,10,20,30,60}.
    artifact:   B2 metadata feature_cols (157) vs panel transformer_v4_wl200_clean.parquet (172 feat)
    prod/exp:   experiment artifact metadata vs prod panel (read-only)
    existing:   set difference = STD5..60, MIN5..60, IMIN5..60 (+ split_label)
    scope:      exact set diff; reproduced as Exp A's --exclude-features
    [VERIFIED — metadata diff this session]

  Claim 5 — pure-placebo drivers (placebo_dominance > 1.5, ~zero aligned IC) =
            {IMXD,CORR,RANK,RSV,IMAX}×horizons + gross_profitability, sue_signal.
    artifact:   /tmp/feat_ic_audit.py output (per-feature aligned vs placebo per-day IC, recent slice)
    prod/exp:   diagnostic on the prod panel (read-only)
    existing:   those families have |aligned_ic| ≈ 0 with placebo_dominance 7–214
    best-known: n/a (a linear PROXY — explicit caveat in the design doc §3)
    scope:      recent-slice per-day spearman; basis for Exp B's extra prune (Exp B = Exp A + these)
    [VERIFIED — feat_ic_audit run, ephemeral]

NEXT:     run A+B (isolated /tmp, multi-seed) → gate each → the gate VERDICTS (path-pinned,
          committed in the results PR) are the authoritative evidence. Promotion only on a
          clean gate PASS + operator sign-off; never bypass the gate.
