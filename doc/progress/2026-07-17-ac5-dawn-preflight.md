# GOAL-5 AC5 (D2): dawn readonly-funnel preflight

STATUS: delivered
WHAT: `ops/renquant104/dawn_funnel_preflight.sh` runs the FULL inference
funnel read-only (readonly-alpaca broker, pinned strategy config — the
exact 07-16 recovery invocation) at 06:05 PT (deploy/ plist template,
weekdays), then `dawn_funnel_analyze.py` alerts via liveness_common on the
killer classes that have actually taken dailies down: contract failures
(07-14/15), panel config mismatch, ModuleNotFound/ImportError (#524
class), pin-drift refusals, any Traceback, and a funnel that never reaches
a decision line. ~8h lead before the 13:55 daily.
WHY/DIR: GOAL-5 P0 AC5 machine-side half; the CI half (pin import-integrity
sweep) is the companion umbrella PR.
EVIDENCE: analyzer tests 7/7 (healthy-clean + one per killer class +
truncation). Zero orders by construction (readonly broker).
NEXT: launchd install of the template + manifest addition = operator-gated
landing (same protocol as the AC1/AC2 sentinels).
