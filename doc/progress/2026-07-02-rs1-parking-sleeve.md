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
