# Progress — small-n guard §4 shadow verdict (frozen replay)

Date: 2026-07-18
PR: research(funnel) — frozen §4 shadow verdict for the VetoWeakBuys small-n guard
Memory tier touched: MID (goal-5 daily-run reliability — HARD admission-gate change
gated on a frozen shadow verdict).

## What this PR delivers

- `doc/research/2026-07-18-smalln-guard-shadow-verdict.json` — the FROZEN verdict
  artifact (per-session partition + floors + delta, all 4 §4 GO criteria, NO-GO
  triggers, synthetic mislabel tests, corpus digest `3da8fcdc7ce595b17d8d37fc`).
- `doc/research/2026-07-18-smalln-guard-shadow-verdict.md` — the memo.
- `scripts/smalln_guard_shadow_replay.py` — the read-only reproducer.

## Verdict

**REPLAY-CONSISTENT / INSUFFICIENT-N** — not GO (2 operative CLEAN sessions vs
frozen `N_shadow=10`), not NO-GO (no blocking defect). Strong positive evidence.

## Method / safety

- Drove the DEPLOYED pinned code (pipeline `d32f7017`: `#205` guard + `#207/#208`
  eligibility ledger) on recorded `candidate_scores`.
- DBs opened `mode=ro&immutable=1`; **zero live orders**; temp-only writes.
- Reproduced recorded live floors exactly (07-16 0.561, 07-17 0.577) = harness faithful.
- Corpus = `#543`/`#544` evidence-script PART-3 target set (14 sessions), digest frozen.

## Key findings

1. Guard admits exactly `{ATI, EME, BWXT}` (all μ>0) on 07-16/07-17; `XLI`/`XLY`
   (μ<0) stay vetoed — matches AC-a/AC-A.
2. No downstream-gate bypass: floor is downstream of `risk_gate_vol`, upstream of
   Selection/QP/Kelly.
3. Eligibility ledger correctly SUPPRESSES real failure-residue days — notably
   averts a 33–38 name mass-admit on the 05-12…15 μ-none inflation days — and all
   synthetic AC-B/AC-F/AC-G + failure-marker cases return NOT-CLEAN.
4. Two caveats block a full GO: (a) replay cannot validate the mass-balance vs
   independent `expected_universe` counter (postdates the sessions) — only the
   synthetic AC-F does; (b) config floor-mode mismatch (shadow=quantile,
   prod=mean+1σ) makes live shadow accrual a weak path to N — recommend an
   expanded historical replay under the production floor mode.

## Guardrails honored

- No production key flipped; no merge; no live-tree mutation; feature branch off
  `origin/main`; mutual code-owner review required (CODEOWNERS).
- Single-identity commit: authored AND committed by `hallovorld` (the PR owner),
  with no co-author / session trailer, per the merged single-identity branch
  policy. Per CODEOWNERS the required reviewer is therefore `haorensjtu-dev` (an
  author cannot approve their own PR); this matches recent PRs #549–#554.

## Next

Accrue to `N_shadow=10` operative affected sessions (expanded historical replay
under prod `adaptive_mean_std` preferred) → operator authorization on the record
→ pin PR restoring keys to production+golden (superseding RenQuant#498).
