# Progress: D6 confirmatory replay — first protocol-valid run

DATE: 2026-07-11
BRANCH: `research/d6-confirmatory-run`
PROTOCOL: `doc/design/2026-07-09-governor-prereg-replay-protocol.md` @ `1de64df9` (merged)
FREEZE COMMIT (pre-arm, pushed 2026-07-11T05:15:11Z): `d5c570e52060af62c7518a03009a658167406794`

## What was done

1. **Freeze-before-arms** (§1): generated the freeze record with the merged
   `scripts/d6_freeze_record.py` v2 (deterministic chronological split — the
   merged tool has no `--seed`; the retired seeded-hash draft is not the
   protocol) against a byte-copied production `sim_runs.db` (pristine sha
   `82084a6d…`; journal-normalized working copy `72b25fdb…` with proven
   logical identity `f342eebd…`). Union 497 sessions → tuning 249 / embargo
   60 / evaluation 188. All #442-inspected sessions fall inside the
   2026-06-23:2026-07-09 exclusion window (zero extra exclusions).
   Committed + pushed together with the DECLARED tuning grids/criterion
   BEFORE any arm ran; `--verify` re-run clean before tuning and evaluation.
2. **Tuning phase** (nested selection, tuning subset only): chose
   E_ceil = P_D5 (.95/.70/.60/.35), band 0.10, k 8; governor_kelly s 0.2,
   λ 0.3; voltarget σ_target 0.18. All tuning configs failed the tuning
   turnover-tax sanity ratio → declared fallback (best Sharpe, FLAGGED).
3. **Evaluation phase** (ONE pass, 188 frozen sessions, one continuous book
   per arm, L3_FULL conventions on pipeline main `3e68737`): 17-arm locked
   family — 7 Phase-1 baselines, 3 L1 candidates, cap{12,20}×{ew,ck} grid,
   equal-weight@E*_governor / @E*_incumbent (incumbent E* from the
   `pipeline_runs` run bundles, 100% session coverage), cash control.
   Veto-floor arms NOT run (moved to §2a live shadow by the merged
   amendment).
4. **Analysis per §1.2/§3/§4/§5**: NW-capped-lag unit-(i) comparisons;
   9×20d-block unit-(ii) with NW-lag-1 t(8) + stationary bootstrap (seed 0)
   conjunction + ESS; 3×60d blocks descriptive-only; full §4 gate table;
   fail-closed injection test 3/3.

## Result (bottom line)

**§5 verdict: REJECT / REDESIGN.** Primary L1 (`gov_ceiling_ck`) loses to
`equal_weight_top_k` (−3.95 bp/day, ns); family PBO 0.874 (bar ≤ 0.10) fails
every arm; turnover-tax gate fails EVERY arm (0.855–0.998 vs ≤ 0.50);
single-name construction invariant breached by whole-share drift in every
equity arm (harness trade-time breach counters 0 for Phase-2 arms — a $10.7k
PV quantization fact, cross-referencing D7). Marginal capital +5.1 bp/20d
(point ≥ 0, indistinguishable from 0). ENABLE was impossible by construction
(S1 live shadow required). Full detail:
`doc/research/2026-07-11-d6-confirmatory-replay-results.md`.

## Boundaries honored

- Production data read-only (byte-copy in scratchpad; sha-verified twice).
- No writes outside scratchpad + this orchestrator worktree; pipeline main
  harness worktree untouched (custom arms registered driver-side, cap-grid
  precedent); no git in the umbrella or any primary checkout's working tree.
- Exploratory runs (seeded-hash tuning subset) retired; nothing from them
  selected anything in this run.
- No self-merge; PR requires Codex approval.
