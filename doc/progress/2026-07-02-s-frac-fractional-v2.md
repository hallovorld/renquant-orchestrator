# S-FRAC fractional shares v2 design — progress record

STATUS:   design / RFC for review (docs only, no code). Operator formally REOPENED
          fractional 2026-07-02 ("fraction重新讨论设计和实现，计入短期计划") and slotted it
          into the SHORT tier; this PR is the v2 re-discussion design.
REVISION: r2 — addressed Codex round-1 CHANGES_REQUESTED: added §7.5 (frozen comparison
          arms A/B/C + mechanical frozen-cohort rule for integer vs A-3 vs fractional),
          §7.6 (success criteria independent of PnL), expanded §2.3/§6 stage-0 coverage
          (partial-fill/cancel-replace state, restart stop-reconciliation, $0
          outage-window-loss-budget-by-construction proof), and §3.4 (quantified failure
          envelope: 10% PV cap × 20% worst-case single-session move = 2% PV worst-case
          loss bound; alert-to-recovery SLA: 15-min page + 60-min response = 75-min
          worst-case detect+respond window).
WHAT:     `doc/design/2026-07-02-s-frac-fractional-v2.md` — the fractional-shares v2
          design: narrowed scope (sizing fidelity + sliver sweep, NOT deployment/
          participation/alpha), active-path-first staging (stage 0 = umbrella
          `RunnerAdapter.commit` fractional contract + audit tests BEFORE any subrepo
          capability work), the software-stop layer design with failure-mode analysis,
          a verified Alpaca fractional order-semantics inventory, a reuse inventory over
          the preserved v1 branches (execution#19 / pipeline#153 / strategy#36), a
          4-stage plan with per-stage AC/tests/flags/kill conditions, interaction
          contracts (sleeve #157, A-3 #156, wash-sale/anti-churn, KPI sizing-fidelity
          metric), and the proposed S-FRAC row for the unified plan's SHORT tier.
WHY/DIR:  v1 (three subrepo PRs) was built capability-first and CLOSED 2026-06-30: the
          ACTIVE live path is the umbrella `RunnerAdapter.commit`, which int-truncates
          fractional fills (`runner.py:1372`), fractional positions cannot hold a
          broker-native GTC stop, and the dependency gate was prose-only. v2 is built ON
          those recorded lessons, not from scratch. What changed since the close: the
          sleeve (pipeline#157) now owns DEPLOYMENT and A-3 (pipeline#156) owns
          PARTICIPATION, so fractional's residual value narrows to SIZING FIDELITY —
          one mechanism kills both the `size_insufficient_cash` zero-drop (measured:
          BLK run `2026-07-01-live-01c54b39`; BLK+AVGO run `2026-07-02-live-85496d1c`)
          and A-3's ≈2.9× one-share round-up overshoot ($324 target → ~$950 share) —
          plus residual cash slivers (incl. fractional SPY/SGOV sleeve sweeps later).
EVIDENCE:
```
artifact:      doc/design/2026-07-02-s-frac-fractional-v2.md (design RFC, this PR)
prod or exp:   design only — no config/order/gate/code change; default-OFF staging
               specified for all future implementation stages
existing data: runs.alpaca.db candidate_scores.blocked_by='size_insufficient_cash'
               (read-only query 2026-07-02: BLK 07-01; BLK+AVGO 07-02); live-tree
               read-only inspection: backtesting/renquant_104/adapters/runner.py:1372
               (int truncation), adapters/z9_stops.py (no-arg supports_broker_side_stops,
               GTC dead-box invariant), renquant-execution alpaca_broker.py:183
               (place_stop_order GTC), com.renquant.intraday104.plist (12-min sell-only
               cadence); closed-PR review threads via gh (execution#19, pipeline#153,
               strategy-104#36); Alpaca fractional rules re-verified via WebSearch
               2026-07-02 (qty|notional exclusive, 9dp, min $1, market/limit/stop/
               stop-limit all TIF=DAY only — no GTC)
best-known?:   builds on the preserved feat/fractional-shares branches (subrepo-green at
               close) + the merged RS-1/RS-2 memos + #156/#157 division of labor
scope:         renquant-orchestrator docs; implementation stages land later as separate
               PRs in umbrella (stage 0), execution (stage 1), pipeline (stage 2-3),
               strategy-104 (final flag), per §6 of the design
```
NEXT:     (1) Codex review of this RFC (esp. §9 open questions: stage-0 blast radius,
          machine-death risk budget, N1-liveness dependency, notional-vs-qty for the
          sleeve sweep, dust threshold, A-3 supersession timing); (2) on merge, add the
          §8 S-FRAC row to the unified plan in its next revision; (3) stage 0 umbrella
          PR (active-path contract + audit tests) as the first implementation step —
          before any subrepo capability rebase.
