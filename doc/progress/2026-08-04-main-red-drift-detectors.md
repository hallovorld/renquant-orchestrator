# 2026-08-04 — two drift detectors were RED on main; both were telling the truth

`main` had two failing tests. Neither is a flaky test and neither needed
silencing — both are drift detectors that fired exactly when they were
supposed to, on changes I landed in the last two days.

## 1. `test_r6_four_surfaces` — the pinned pair moved `xgb` → `blend`

The four role-assignment surfaces are pinned by VALUE so a config switch has to
re-declare them rather than inherit the old row. The 2026-08-04 operator-directed
full-book z-blend switch (s104#88) moved the pinned pair, and the test caught it.

Re-measured `[VERIFIED — 2026-08-04, this session]`:

| surface | `ranking.panel_scoring.kind` |
|---|---|
| `renquant-strategy-104/configs/strategy_config.json` | `blend` |
| `renquant-strategy-104/configs/strategy_config.golden.json` | `blend` |
| `RenQuant/backtesting/renquant_104/strategy_config.json` | `hf_patchtst` |
| `RenQuant/backtesting/renquant_104/strategy_config.golden.json` | `hf_patchtst` |

The shape this file exists to record is UNCHANGED: still two internally-consistent
pairs that disagree across the pinned/umbrella boundary, which is why a guard that
stays on one side passes forever. Only the pinned pair's value moved. Registry row
updated with the old value retained and dated.

## 2. `test_rq104_silent_refusal_sentinel` — the emitter contract's line pins rotted

`emitter_contract.json` pins each watched line to `<script>:<line>` so a stale
citation cannot survive a presence-only check (codex on orch#785). The cost:
any edit ABOVE a watched line reds it. That has now happened twice in two days —
RQ#568 (+24 lines) and RQ#580 (+24 more) — and the second one was sitting red on
main.

Re-captured, five rows and one digest `[VERIFIED — measured off the live wrappers]`:

```
scripts/weekly_wf_promote.sh:287 -> :311   (FALLBACK-PROMOTED, --promote-staged mode)
scripts/weekly_wf_promote.sh:426 -> :450   (WF gate REJECTED)
scripts/weekly_wf_promote.sh:565 -> :589   (Promote FAILED)
scripts/weekly_wf_promote.sh:620 -> :644   (FALLBACK-PROMOTED, Step 4b)
scripts/weekly_wf_promote.sh:624 -> :648   (PASSED)
scripts/weekly_wf_promote.sh sha256 e314a67e76dade67 -> 846cda8492bcebaa
```

No template changed, so no sentinel pattern needed re-verification.

### The re-capture is now a tool, not a hand-edit

Fixing five line numbers by hand is exactly the mechanical re-derivation that gets
done wrong — and it will recur on every wrapper edit. `ops/renquant104/recapture_emitter_contract.py`
re-derives POSITIONS and DIGESTS only, and REFUSES on anything else:

- a template that no longer appears → refuse (real emitter change);
- a template whose emit-site COUNT stops matching the contract's row count →
  refuse, because a new site means the lane can emit from a branch nobody
  classified (this is not hypothetical: the FALLBACK-PROMOTED template legitimately
  has two sites and two rows, and a naive re-capture collapses them);
- templates are never edited.

`--check` reports drift and exits 1 without writing. A new test asserts the live
contract is in sync, so the same failure is now one command away from fixed.

Suites: r6 6 passed · sentinel 31 passed · recapture 6 passed.

## Review round 2 (codex on orch#804)

Codex found the re-capture tool's refusal set incomplete and proved it: with the
emitter DELETED and only a comment left quoting the template, `if template in ln`
treated the comment as an emit site and silently re-pinned to it. A vanished
emitter could re-pin to its own obituary — the exact failure the refusal exists
to prevent.

Fixed: a line counts as an emit site only if it is not a comment, has no `#`
before the template, and has an emitter command (`echo`/`printf`/`notify`) ahead
of it. Five regression tests added, including codex's repro verbatim, a trailing
`#` comment, a grep PATTERN list quoting the same text (the sentinel-adjacent
shape — wrappers grep their own logs for these lines), `printf`/`notify` still
counting, and an anti-regression check that the tightened matcher still resolves
all nine live contracted lines. 11 passed.

## Review round 3 (codex on orch#804)

Codex confirmed round 2 fixed the comment repro, then found two more — one in
each direction, and the FALSE-NEGATIVE is the dangerous one:

1. **A real emitter was rejected** when `#` appeared inside the emitted string:
   `echo "#tag === X ==="`. Refusing a legitimate emitter means the tool can
   never re-capture that line again — permanently worse than the false positive
   it was guarding against. The comment scan is now quote-aware: `#` only starts
   a comment outside quotes.
2. **A dead `echo` inside a here-doc block comment was still accepted**:
   `: <<'BLOCK'` … `echo "=== X ==="` … `BLOCK`. That line never executes.
   Matching is now file-level (`_emit_sites`), tracking here-doc state so bodies
   are skipped, including `<<-DELIM` and quoted delimiters.

`_emit_sites` is deliberately conservative: if a real emitter ever moves INSIDE
a here-doc it under-counts, `recapture` refuses on the count mismatch, and a
human looks. Refusing is the safe direction; silently re-pinning is not.

Six more tests (hash-in-double-quotes, hash-in-single-quotes, a REAL trailing
comment still refused, here-doc block comment refused, a real emitter after the
here-doc closes still found, `<<-'PY'` and `<<"EOF"` delimiters both close).
17 in this file; 5552 passed, 2 skipped across the repo.

## Review round 4 (codex on orch#804)

The here-doc tracker closed on `line.strip() == delimiter`, which is not
shell-correct: `<<EOF` ends ONLY on a line that is exactly the delimiter — `  EOF`
does not close it — and `<<-EOF` permits leading TABS only, never spaces. Codex
verified the shell behaviour against bash and produced a fixture
(`cat <<EOF` / `  EOF` / `echo "=== X ==="` / `EOF`) where the tracker ended the
here-doc early and re-pinned to an echo bash is still swallowing as body.

Closing is now exact, with `<<-` stripping tabs only. Three more tests: an
indented delimiter does not close a plain here-doc; `<<-` closes on tabs but not
on spaces; the delimiter appearing as ordinary body text does not close.
20 tests in this file, and `--check` against the live wrappers exits 0.
