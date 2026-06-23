# trade-review skill — design PR

STATUS:   design for review (no scripts yet). Per operator: describe → discuss → PR to Codex → then implement.
WHAT:     proposes a `trade-review` skill — an independent multi-lens (portfolio + technical + analyst +
          fundamental) review of the model's orders / live book, returning keep/trim/cut + target weights.
WHY/DIR:  the WF/conviction gates are model-internal. The 2026-06-23 XGB deploy showed the model can size
          backwards vs forward upside, buy technically broken names, over-concentrate, and sit 78% cash —
          none caught by its own gates. An external PM-style cross-check catches these before/after trading.
EVIDENCE: live example (2026-06-23, XGB orders): top-3 positions (CRWD/PANW/CSCO, 73% of long book) had
          +5–10% analyst upside while the bottom-3 (AMZN/NFLX/ZM, 26%) had +27–56%; NFLX bought at a 52-week
          low / RSI 17; CRWD+PANW = 53% in two ρ≈0.84 names; 78% cash. `[VERIFIED — Alpaca technicals +
          WebSearch analyst targets, 2026-06-23 this session]`
SCOPE:    this PR = design doc + draft SKILL.md only. Implementation (the two scripts + analyst step) is a
          follow-up PR after the design is reviewed.
NEXT:     resolve the 5 design decisions + 4 open questions (doc/design/2026-06-23-trade-review-skill.md),
          then implement Phase 1 (WebSearch + Alpaca), then evaluate wiring it into the daily pipeline.
