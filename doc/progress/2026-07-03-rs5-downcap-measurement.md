# RS-5 / M7 down-cap panel measurement — fallback-panel execution

STATUS:   research measurement executed (read-only); docs + evidence + runner committed.
WHAT:     executed the frozen RS-5 spec (doc/design/2026-07-02-rs5-downcap-panel-spec.md,
          freeze point = PR #250 merge 23dc9ff3, 2026-07-02T14:14:07-07:00) on the
          FALLBACK panel (local survivor-conditioned bar store x current VTWO/R2000
          membership), because Norgate's primary constituency-by-date panel is
          trial/POC-first per RS-3 r2/r3 and no trial has run. Runner
          scripts/rs5_downcap_measurement.py loads the prereg contract at startup and
          refuses to run on any parameter deviation (spec §7 duty; 0 deviations at run).
VERDICT:  M7 = INCONCLUSIVE (fallback panel; primary pending) — the spec-mandated
          outcome for this branch: NEITHER a GO NOR a NO-GO computed on the fallback
          panel is decision-grade and NEITHER may feed D3 (spec §2/§5, round-2
          symmetric rule). Gate arithmetic was computed and reported in full as the
          pipeline-feasibility demonstration; exploratory readings are in the research
          memo. Pipeline feasibility: PASS (end-to-end in ~36s on a 1,671-name store
          intersection, ~600 names/date after the frozen floors; n=2,482 clean dates).
CONTROLS: S-REL P0 — positive control (planted ~0.1 effect) detected on all 3 seeds;
          true-null control not detected AND the per-family KILL branch fires on it,
          all 3 seeds; committed unit tests additionally cover the contract
          refuse-on-tamper branch, floors, buckets, placebo construction.
EVIDENCE: doc/research/evidence/2026-07-03-rs5-downcap/ (manifest with input SHA-256s +
          code sha + evidence-boundary block + disclosed deviations D1-D12 + reopening
          conditions; per-date IC series sufficient to recompute every bootstrap;
          results incl. all seeds and sensitivity cuts). `[VERIFIED — full run rerun from
          the committed runner (828edbe) against the committed prereg contract (0
          deviations), 1449/1449 repo tests + 10 new unit tests green, controls pass on
          all 3 seeds, 2026-07-03 this session]`
WHY/DIR:  D3 (Term BR's only remaining route per the alpha-frontier synthesis addendum)
          consumes M7's verdict; this run makes the M7 machinery real and pins the
          decision-grade path to one remaining step: the Norgate trial -> primary panel
          -> re-measure under the SAME frozen thresholds (no re-freeze).
NEXT:     Norgate Windows/VM + plugin POC + 3-week trial acceptance test (spec §6 item 1,
          4 pass/fail criteria incl. delisting-proceeds joinability) — procurement is
          ask-first; D3 synthesis memo cites this run as INCONCLUSIVE-pending-primary,
          not as any directional evidence.
