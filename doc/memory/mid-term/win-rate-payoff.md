# Workstream: win-rate / payoff

STATUS:   parked — needs live trading to resume first (depends on `model-edge`).
GOAL:     raise live *return*, not hit-rate (hit-rate is already fine).
NEXT:     once trading resumes: investigate why winners are exited early; consider a
          meta-label *entry* filter.
EVIDENCE: live hit-rate ~83% (already > any target); the real lever is **payoff 0.89** —
          winners exited ~8d on a 60d-horizon strategy. Tool: PR #393 (live win-rate
          tracker). `[VERIFIED — runs.alpaca.db run_type='live' split]`
