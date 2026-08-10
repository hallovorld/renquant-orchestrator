# qp re-enable evidence prereg — freeze candidate (orch#954)

STATUS:    design freeze candidate; binds at merge; no computation run
           beyond the two committed pre-freeze power calcs.

WHAT:      doc/design/2026-08-10-qp-reenable-evidence-prereg.md — the
           05-23 recorded condition operationalized: selection-level WF
           alpha (eight embargoed v2-CUTS folds, N=1,357 days) of the
           served recipe (blend replayed per fold; momentum leg from
           its frozen params fingerprint) surviving the DESIGNED
           admission gate computed per fold; bar 0.0337σ/day ≈ 6.9%/yr
           gross with CI excluding 0 and a ≥700-day power floor;
           verdict PASS/FAIL/POWER_INSUFFICIENT; PASS ⇒ a reviewed
           strategy-104 knob PR. Contains an explicit REINTERPRETATION
           of the recorded condition (portfolio-significance is
           untestable: MDE 41-82%/yr — computed, committed) flagged
           for review as such.

WHY/DIR:   The three locks (orch#943/#945) leave qp_min_invested_pct=0
           as the operative cash lock with a recorded evidence
           condition. This prereg makes that condition runnable at
           policy-grade power without waiting on the #942 serving fork
           (the gate predicate is the designed mechanism per fold;
           decision basis: served BULL_CALM entry-rank Spearman
           0.0023/n=104 = full miss). Gate-starvation is a publishable
           finding, not a silent skip.

EVIDENCE:  artifact:      doc/design/2026-08-10-qp-reenable-evidence-prereg.md +
                          doc/research/data/2026-08-10-qp-power-calc.py +
                          doc/research/data/2026-08-10-qp-power-selection.py
                          [VERIFIED — both calcs run 2026-08-10 on
                          pre-2026 data only; numbers quoted in-doc]
           prod or exp:   design only; no confirmatory computation
           existing data: orch#943/#945 (locks), #948-#950 (fidelity),
                          #951/#953 (diagnostic, non-inheritable),
                          #954 thread (full decision trail)
           best-known?:   yes — §2 states the untestability result and
                          the reinterpretation; §6 the non-inheritance
                          and single-configuration rules
           scope:         one design doc + this progress doc + the two
                          committed power calcs; runner = separate PR
                          bound to §7 after merge

TESTS:     none — design doc; power calcs exit 0.

NEXT:      codex review of the freeze candidate (including the
           reinterpretation); then the runner PR per §7 (model-side
           internals in renquant-model, join-only here).
