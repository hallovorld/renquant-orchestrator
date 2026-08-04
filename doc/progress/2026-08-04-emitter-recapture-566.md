# 2026-08-04 — emitter contract re-capture for RQ#566 (the paired half)

STATUS:    the declared paired follow-up of RQ#566, captured from MERGED
           live bytes (the #774 lesson: never from branch bytes)
WHAT:      ops/renquant104/emitter_contract.json — weekly wrapper sha
           3b1655ecf7ca7096 (RQ#566 merged 71ba96f3b, live-pulled before
           capture); line moves: PASSED->600, Promote FAILED->445,
           REJECTED->426 (the "production unchanged" refusal; the :388
           "consulting the fallback" transition line is INFO, not a
           contract line). FALLBACK-PROMOTED becomes DUAL-SOURCE: the
           byte-identical template fires from the scheduled Step 4b path
           (:596) AND the new --promote-staged operator mode (:287) —
           two entries, same template, same action semantics, so the
           sentinel counts an operator-mode promotion as the ACTION it
           is (this morning's manual promotion predated the mode and is
           covered by the grants trail instead).
EVIDENCE:  capture tool output against the merged live wrapper (session
           log); silent-refusal sentinel + contract fixture suites 57
           passed against the re-captured contract.
NEXT:      merge -> orch-run checkout sync so Step 4b's consumer check
           and the local drift test both see the refreshed contract.
