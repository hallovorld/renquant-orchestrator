# Workstream: intraday protective-action governor (#26)

STATUS:   primitive shipped (PR #390), flag-off, unwired; wiring parked.
GOAL:     rate-limit / cooldown / per-session caps on intraday protective sells.
NEXT:     operator chooses policy values; then wire into the intraday SellOnlyPipeline
          behind the flag; shadow-validate before enabling. Matters once trading resumes.
EVIDENCE: the intraday SellOnlyPipeline currently has no throttle on protective sells.
          `[VERIFIED — intraday_sell_104.sh / kernel review]`
