# S-REL V6 step 1 — Phase −1 intraday-alpha verdict evidence recommitted to main (durability)

DATE:     2026-07-03
SCOPE:    S-REL audit item V6, step 1 ONLY (durability recommit), per
          `doc/design/2026-07-03-s-rel-experiment-reliability.md` §V6 — "recommit
          the phase −1 memo + script + evidence from PR #199's branch as a
          docs/evidence PR (no re-litigation — archival)". Step 2 (the full
          adversarial recompute) is a SEPARATE later step and was deliberately
          NOT performed here. No data recomputation; read-only recovery.
STATUS:   DONE — archival recommit; verification status stays PROVISIONAL.

## Why (the durability gap)

The Phase −1 verdict — measured σ_oc ≈ 152 bps (std; robust 114–115) and a NEGATIVE
intraday open→close directional net-edge band (−6.4 bps @ IC 0.03 / −3.4 bps @ IC 0.05
vs breakeven σ_oc = cost/IC ≈ 367/220 bps) → soft NO-GO on intraday directional alpha,
pivot to the execution-timing residual — lived ONLY on the closed-unmerged PR #199
branch. Meanwhile merged plans on main actively rely on it:

- H2 execution roadmap non-goals (`doc/design/2026-07-02-h2-execution-roadmap.md`);
- unified 107 master plan **L3 row** — "conditional timing residual ONLY (phase −1
  NO-GO not re-litigated)" (`doc/design/2026-07-02-unified-107-master-plan.md:109`);
- design-review amendment **A4.2** — Stage-2 estimand pinned to the conditional timing
  residual because of it (`doc/design/2026-07-01-104-105-design-review-amendments.md`).

A standing verdict that merged documents rely on must have its evidence on main.

## What was recovered (source: branch `research/renquant105-phase-minus-1`, commit `dcd18b98`)

Recovered byte-identical from PR #199's preserved branch (PR closed unmerged
2026-06-27T20:03Z because renquant105 was repointed — the measurement was never
disputed):

- `doc/research/2026-06-27-renquant105-phase-minus-1-results.md` — the measured memo
  (σ_oc distributions, breadth, coverage, cost, net-edge band, pre-registered STOP/GO).
  Recommitted with a PROVENANCE header block prepended (origin PR, durability
  rationale, standing-verdict reading, PROVISIONAL status, reopening conditions);
  original content untouched.
- `doc/progress/2026-06-27-renquant105-phase-minus-1.md` — the original progress
  record (one-line recommit pointer prepended; otherwise unchanged).
- `scripts/research_phase_minus_1_feasibility.py` — the read-only measurement harness
  (byte-identical).
- `tests/test_research_phase_minus_1_feasibility.py` — 18 network-free pure-function
  tests locking thresholds + decision logic (byte-identical).

**Evidence-JSON note:** no standalone evidence JSON was ever committed on the branch
(the script's `--json` output was not persisted in #199); the measured evidence is the
tables embedded in the memo §§2–7. Nothing was recomputed to fabricate one — that is
V6 step 2's job under adversarial control, not this recommit's.

## Standing-verdict reading (unchanged, restated for the index)

The memo's in-document §7 verdict is "GO to M0" — an exact application of the
now-superseded intraday-105 STOP/GO table, which did not gate on net-edge. The
STANDING verdict on main (A4.2 / L3 / H2 non-goals / VERDICTS V6 row) is the §6
finding promoted to operative: **soft NO-GO on intraday open→close directional
alpha**; L3 is restricted to the conditional timing residual. Reopening conditions
(standing): measured cost below breakeven, or evidenced IC far above the 0.03–0.05
band — either one arrives as a NEW frozen prereg, never a re-pitch.

## VERDICTS.md row update — PENDING #265 (rebase discipline)

`doc/research/VERDICTS.md` is introduced by the still-open S-REL design PR #265, so
this PR does NOT touch it (no conflicting copy on main). After #265 merges, its V6 row
("evidence NOT on main … durability recommit FIRST") should be amended — via #265's
rebase or an immediate follow-up — to:

| Date | ID / source | Verdict | Evidence boundary (one phrase) | Verification | Reopening condition |
|---|---|---|---|---|---|
| 2026-06-28 | Phase −1 intraday directional alpha — `2026-06-27-renquant105-phase-minus-1-results.md` (recommitted from closed PR #199 by the V6 step-1 durability PR) | **NO-GO (soft)** — net edge −6.4 bps @ IC 0.03 / −3.4 @ IC 0.05 vs 220–367 bps breakeven; killed intraday directional alpha; L3 restricted to the timing residual | σ_oc ≈ 152 bps std (robust 114–115); 142-name survivorship universe; 11 bps cost prior; relied on by merged plans (H2 non-goals, L3 row, A4.2) | **PROVISIONAL** — V6 step-1 durability DONE; step-2 adversarial recompute pending | Measured cost below breakeven or evidenced IC far above the 0.03–0.05 band — either is a NEW frozen prereg, never a re-pitch |

## Guardrails honoured

Fresh worktree on `fix/v6-phase-minus-1-durability` off `origin/main`; zero git
operations in `/Users/renhao/git/github/RenQuant` or any primary checkout; all reads
read-only (`git show` from the preserved branch); no network data fetch, no script
execution against market data; the recommitted network-free unit tests were run once
to confirm main's CI stays green.
