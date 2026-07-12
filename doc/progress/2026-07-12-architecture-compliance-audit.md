# Architecture Compliance Audit — GOAL-3

Date: 2026-07-12 (original); **re-audited 2026-07-12 (round 2)** in response to
Codex CHANGES_REQUESTED.
Status: COMPLETE (audit phase, round 2). Remediation sequenced, not started.
PR: orchestrator (this PR)

## Round 2: re-audit in response to Codex review

Codex (2026-07-12T16:22:41Z) blocked round 1 as "useful raw material, but not
yet reproducible or current enough to merge": stale on facts already merged
same-day (V-017, R-003), no machine-verifiable evidence (audited SHA / exact
command / path classification per entry), remediation presented as settled
architecture rather than options, no severity rubric, no concrete GOAL-2
acceptance tests, PR behind main.

Every one of the 19 violations + 3 resolved entries was re-verified from
scratch against a freshly-fetched `origin/main` of each relevant repo (10
repos total, read-only — no sibling repo's working tree or branch was
touched), split across two independent passes (umbrella/orchestrator/hygiene
cluster; GOAL-2/crypto cluster) and reconciled into one document. Full detail,
per-entry audited-commit/command/evidence/path-classification/severity/fact-vs-hypothesis,
is in `doc/research/2026-07-12-architecture-violation-registry.md` (revised).

### What changed from round 1

- **Severity rubric applied for the first time** (4 boolean-ish axes:
  production safety, deployability, correctness/drift, GOAL-2 hard-block;
  P0 = production-safety AND active-runtime-path; P1 = hard-block OR
  (correctness/drift AND active-runtime-path); P2 = otherwise). Re-scoring
  every entry under this rubric — rather than carrying forward round 1's
  labels — moved several items:
  - **V-005** P0→P1 (kernel-internal-import breakage fails loud at import
    time, not the rubric's "incorrect live trading behavior" test)
  - **V-008** P1→**P0** (worse on inspection: a net-of-cost primitive
    `renquant_common.cost_model` now exists and is trusted for live
    execution accounting, yet the WF gate that decides what trades real
    money still doesn't consume it)
  - **V-012** P1→P2 (the claimed fail-closed per-ticker fundamentals block
    doesn't exist in current code; the real mechanism is feed-level and
    fails OPEN via median imputation — a data-quality issue, not a gate)
- **Resolved same-round-1-day, missed by round 1**: V-007 (NYSE calendar),
  V-010 (wash-sale), and V-019 (annualization factor) were all fixed by a
  2026-07-10 crypto-RFC wiring wave — 2 days before round 1's own stated
  audit date. V-017 (execution↔pipeline private-API import) resolved for
  real during round 2 itself (pipeline#192 + execution#30 merged ~4 hours
  before this revision) — exactly the fix path Codex predicted.
- **Reclassified NOT A VIOLATION** (not forced into a P-tier): V-009
  (equity DAY-only TIF hard-reject is architecturally unreachable from the
  isolated crypto order-placement branch — confirmed by tracing
  `alpaca_broker.place_order`'s dispatch, per Codex's own hint) and V-019
  (both originally-cited annualization-252 sites are already asset-class-aware
  at their real call sites).
- **R-001 reopened as CONTESTED**, not a clean resolve: the canonical
  `renquant-pipeline`/`renquant-model` repos are genuinely unified on
  `renquant_common.model_fingerprint`, but the umbrella's own dual-home
  kernel copy (`RenQuant/backtesting/renquant_104/kernel/panel_pipeline/panel_scorer.py:108`)
  still defines an independent `model_content_sha256` that feeds the
  production calibrator fit + WF stamping — a live P0-equivalent gap the
  round-1 "resolved" table hid. Tracked against V-001/V-014's dual-home-kernel
  finding rather than given a new ID, to avoid double-counting one root cause.
- **V-006, V-011, V-013** (broker allowlist, vol clips, reconciliation filter)
  remain open but with substantially revised evidence: in each case the
  underlying abstraction/capability now exists (asset_class.py bypass
  functions, a parameterized broker filter) but isn't wired at the specific
  flagged call site — a different, more precise failure mode than "doesn't
  exist at all."
- **V-014** (274 umbrella scripts) split: the weekly-tournament-retrain chain
  specifically (writes live buy-admission models, acceptance gate disabled)
  is now flagged as its own P0-equivalent risk rather than folded into
  general "274 scripts" hygiene.

## Findings (revised counts)

19 violations + 3 resolved entries re-verified across 10 repos (9 subrepos +
the umbrella). See the registry's Summary table for the full old-vs-new
severity breakdown; headline:

| Severity | Round 1 count | Round 2 count | Key themes |
|---|---|---|---|
| P0 | 5 | 4 (+1 mixed, +1 reopened) | V-001/V-002 unchanged (umbrella runner.py + daily_104.sh place/schedule every live order); **V-008 up** (WF gate cost model — primitive exists, unused where it matters); **V-014's tournament-retrain subset**; **R-001's umbrella-copy remainder** reopened |
| P1 | 8 | 5 | V-003, V-005 (reverse/internal imports); V-006, V-011, V-013 (abstraction exists, not wired at the flagged call site — the recurring pattern this round surfaced) |
| P2 | 5 | 5 | V-004, V-015, V-016, V-018 unchanged in tier; **V-012 downgraded** (mechanism mischaracterized) |
| NOT A VIOLATION | 0 | 2 | V-009 (equity/crypto TIF genuinely isolated), V-019 (annualization already asset-class-aware) |
| RESOLVED | 3 | 5 | R-002, R-003 confirmed; **V-007, V-010, V-017 added**; **R-001 downgraded to CONTESTED** |

Full registry: `doc/research/2026-07-12-architecture-violation-registry.md`

## Relationship to GOAL-2 (Crypto)

Re-verification found the crypto-blocking picture is BETTER than round 1
believed on several items (a 2026-07-10 wiring wave the round-1 audit missed
despite being dated the same day resolved V-007/V-010/V-019 and made V-009 not
a violation) but WORSE on the one item that matters most for an actual go-live:
**V-013** (execution reconciliation) is a hard, complete blind spot for crypto
fills/open-orders if a sleeve goes live before its two production call sites
are updated — the underlying capability already exists, this is a cheap fix.
V-011's residual SPY-proxy defect in portfolio-level vol targeting is a similar
latent, not-yet-triggered risk. See the registry's per-entry GOAL-2 acceptance
test specs (V-013) for concrete, pytest-ready failure/success conditions.

## Remediation plan (re-sequenced by round-2 severity — see registry's
"Migration sequencing" for full detail)

1. **Phase 1 (P0)**: V-001, V-002, V-008, V-014's tournament-retrain subset,
   R-001's umbrella-copy remainder.
2. **Phase 2 (P1)**: V-013 (cheapest GOAL-2 fix — call-site update only),
   V-011's residual defect, V-003 (needs an ADR — two options presented, not
   decided), V-006, V-005.
3. **Phase 3 (P2)**: V-018 (port renquant-model's proven CI-boundary-lint
   pattern), V-004, V-015, V-012, V-016, V-014's bulk-script remainder.

No implementation in this PR — audit and registry only, both rounds.
Remediation PRs should reference violation IDs from the registry.

## Methodology (round 2)

- `git -C <repo> fetch origin main -q` + `git -C <repo> grep` / `git -C <repo>
  show origin/main:<path>` against each repo's freshly-fetched `origin/main`
  — never a working tree (several sibling repos are on non-main branches or
  have uncommitted changes; read-only throughout, nothing touched).
- Every entry carries: audited commit SHA, verification date, exact command
  run, exact matched evidence from re-running it today, a path classification
  (active runtime path / test-only / historical shim / documentation-only,
  with tracing shown), a disposition, a rubric-scored severity, and a
  fact-vs-proposed-remediation split (remediation explicitly hedged as one
  option among possibly several, not settled architecture).
- Cross-referenced against a separate, already-merged 2026-07-10 synthesis
  audit (`doc/design/2026-07-10-architecture-compliance-registry.md` + 4 raw
  evidence files under `doc/research/evidence/arch_audit_2026_07/`) for the
  umbrella/dual-home-kernel cluster, which that document covers in more depth
  under a different taxonomy (T1-T7/R0-R7) — treated as a linked evidence
  source, not re-derived, and explicitly distinguished from this document's
  own independent re-verification commands.
