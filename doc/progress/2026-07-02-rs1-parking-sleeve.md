# RS-1 parking-sleeve recommendation — research PR

STATUS:   research recommendation under the delegated-decision protocol (operator NOTIFIED;
          docs only; S7's config/implementation PR follows the normal review lane).
REVISION: r1.
WHAT:     `doc/research/2026-07-02-rs1-parking-sleeve.md` — RS-1 deliverable (#231 §6): the
          sleeve vehicle is a **β-budgeted SPY/SGOV split derived from the G* DD≤15% bar**
          (β_max = 0.15/0.25 stress = 0.6; sleeve_spy_frac = (β_max − w_pos)/w_sleeve ⇒ 30%
          SPY / 70% SGOV at today's mix), expressed as a FORMULA that auto-shrinks the SPY
          leg as lane A lifts single-name deployment; existing regime gates (BEAR ⇒ cash)
          unchanged; SGOV-only kept as the floor/override state.
WHY/DIR:  measured (46 sessions, 04-24→07-01): avg cash weight 75.5%, foregone-SPY drag
          2.88pp cumulative ≈ 16%/yr annualized — the mechanical core of the flat-book-vs-
          rally gap. 100% SPY would recover it all but breaches the pre-registered DD bar at
          SPY−25% stress; 100% SGOV locks the relative shortfall in. The β-budget derivation
          makes the tradeoff a computed consequence of an already-agreed bar rather than a
          taste choice; the recorded risk statement + reversal trigger are in §4.
EVIDENCE: reproducible measurement (in-memo method: live_state_snapshots cash/pv ×
          ohlcv/SPY); POC-B lane-A ceiling (~40–43%) for the division of labor; #223 A2
          verified margin regime for same-day re-use; SGOV carry marked verify-at-checkout.
NEXT:     Codex review; S7 implementation PR encodes the formula + the 10-session sweep
          shadow; the reversal trigger enters the weekly KPI dashboard.

ROUND 2 (Codex CHANGES_REQUESTED — regression against merged #228, unjustified sizing,
G* misuse, path-dependent drag, combined-arm gating):

**Findings.** (1) §3 called the SPY sleeve "cash-equivalent," excluding it from QP/exits/
correlation caps — a direct regression against the already-merged `#228` §1.3, which settled
this exact question (SPY is a real ~1.0-beta position and must participate in every real risk
control). (2) The 30/70 split assumed `β_pos = 1.0` and `SGOV beta = 0` (neither measured),
used one stress scenario, and consumed the entire 15% DD budget with zero reserve for
idiosyncratic loss/covariance shift/gaps/slippage/model error — not yet a defensible risk
budget. (3) G* (research#230's proposed end-2028 DD bar) was treated as a preregistered
authorization bar; #230's own text says it is NOT yet preregistered. (4) The "16%/yr
annualized drag" figure extrapolated one realized 46-session rally path into an expected
annual benefit — descriptive path extrapolation, not an expected-value estimate. (5) SGOV
and SPY arms were gated as one combined proposal with no independent authorization/rollback,
and the doc implied a 10-session shadow could authorize live capital exposure.

**Fix.** Rewrote `doc/research/2026-07-02-rs1-parking-sleeve.md` (r2): §1 reports only the
realized period attribution, no forward annualization. §2 keeps the β-budget formula as a
PROVISIONAL planning sketch, explicitly lists its four unclosed gaps (real beta/covariance
measurement, real SGOV rate-risk figure, multi-scenario stress suite, explicit risk buffer)
and states the 30/70 split is not yet a sizing recommendation. §3 replaces "cash-equivalent"
with #228 §1.3's exact settled risk-participation language verbatim (total-book beta, gross/
net exposure, concentration, correlation, drawdown, liquidity, funding — SPY excluded only
from alpha ranking). §4 (new) splits SGOV/SPY into independent gates: SGOV gets a
lighter-weight plumbing-only path; SPY must follow #228 §1.2's full one-change-at-a-time
experiment structure (baseline, immutable sessions, estimand, non-inferiority/risk
thresholds, stop rule, rollback) plus #228 §1.3's pre-registered replay/shadow comparison
before any capital exposure — explicit statement that this RFC proposes/designs only, no
live enablement. §5's risk statement reframed as conditional/not-yet-accepted.

**Evidence:** #228's merged §1.3 text read directly (`doc/design/2026-07-02-104-capability-
program.md`) and its exact risk-participation bullet list reused rather than re-derived;
#230's merged §5 text confirms G107's DD bar is proposed, not preregistered; #228 §1.2's
Lane-A one-change-at-a-time structure reused verbatim for the new SPY-arm gate.
[VERIFIED — this round's own change: #228 §1.3 and §1.2 text confirmed present in current
`origin/main` via direct file read before reuse; #230's G107 "not yet preregistered" wording
matched verbatim against its current merged text; no new numeric claims introduced, only
existing merged text reused and the r1 draft's four unsupported claims removed/reframed.]

**Scope:** doc-only change, no code/tests in this PR (pure research/design memo).

NEXT (updated): Codex re-review; the §2 measurement gaps (real beta/covariance, multi-
scenario stress suite, risk buffer) need a dedicated follow-up before the 30/70 split can be
treated as more than a planning sketch; S7's eventual implementation PR must build against
the corrected §3/§4 framing, not the r1 draft.
