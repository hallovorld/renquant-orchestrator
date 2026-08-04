# 2026-08-04 — emitter contract re-capture after RQ#568 (state-aware reject notify)

## What moved and why

RenQuant#568 (merged 13d0d06c) inserted the reject-disposition block into
`scripts/weekly_wf_promote.sh` below the REJECTED echo at :426, shifting three
contracted line locations recorded in `ops/renquant104/emitter_contract.json`:

| template | old | new |
|---|---|---|
| `=== weekly_wf_promote PASSED …` | :600 | :624 |
| `=== weekly_wf_promote FALLBACK-PROMOTED (rfc210) …` (scheduled) | :596 | :620 |
| `Promote FAILED — production may still be…` | :541 | :565 |

Unchanged: REJECTED `:426` (the wrapper emits that template VERBATIM on both
disposition paths by design — calm and alarm alike) and the promote-staged
FALLBACK-PROMOTED at `:287`. Wrapper sha pin: `3b1655ecf7ca7096` →
`e314a67e76dade67` (shasum read back from the merged content).

## The deliberately temporary local drift window

The machine-local source-location guard
(`tests/test_rq104_silent_refusal_sentinel.py::test_local_wrapper_still_emits_the_contracted_lines`)
reads the LIVE tree's wrapper, which still carries the pre-#568 script until
the deploy batch runs. During that window this branch's contract is "ahead" of
the deployed wrapper and the guard is RED on this machine — that is the
designed transition signal, not a defect. Closure: merge this PR + deploy
batch (live-tree pull of RQ#568/#569 + orchestrator-run sync), then re-run the
guard suite and record the green in the grants log. CI is unaffected (the live
tree is absent there; the guard skips loudly).

## Verification

- Re-located all three templates in the merged wrapper by grep line-number
  read-back; the two unchanged lines verified still at :426/:287.
- Post-deploy: guard suite re-run recorded in the session grants log
  (transition window closed same day).
