# GOAL-5 P0 — the guard that stops the known sell-only failure mode is disabled in the deployed job

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-5 (P0), daily-run reliability

## The measurement

`daily_104.sh:113–120`, read verbatim:

```bash
if ! PROD_STRATEGY_CONFIG="$(renquant_strategy_config "$SUBREPO_ROOT" strategy_config.json)"; then
    if { [ "${RENQUANT_STRICT_SUBREPO_PATHS:-0}" = "1" ] || [ "${RENQUANT_OPS_FAIL_CLOSED:-0}" = "1" ]; } \
        && [ "${RQ_DAILY_RUNNER:-multirepo}" != "umbrella" ]; then
        echo "ERROR: pinned renquant-strategy-104 strategy_config.json unavailable" | tee -a "$LOG"
        exit 1
    fi
    PROD_STRATEGY_CONFIG="$REPO_DIR/backtesting/renquant_104/strategy_config.json"
fi
```

Both flags default to `0`. Checked in **every** place either could be set
`[本次实测 2026-07-31]`:

| where | result |
|---|---|
| `com.renquant.daily104.plist` → `EnvironmentVariables` | only `PATH` and `RENQUANT_SEC_UA` |
| `daily_104.sh` | **reads** the flags at line 114; never assigns |
| `scripts/subrepo_env.sh` | **reads** them at lines 68/71; never assigns |

```
NOT ARMED com.renquant.daily104.plist  [checked]
0 of 1 declared job(s) arm the fail-closed guard
```

## Why it matters — and this half is not mine

Twin-registry **R5** (`doc/arch/twin-implementation-registry.md`) records that the two
configs are **inverted**: the pinned one makes `xgb` primary, the umbrella one makes a
PatchTST checkpoint primary. So the fallback does not merely choose a different file — it
**swaps which model decides the book**, to a checkpoint measured at 625 days stale against
a 28-day limit, whose scores are intrinsically all-negative and therefore admit no name at
all. R5 cites `RenQuant#546` for the resulting silent sell-only book.

**And the fallback is silent.** There is an `echo` on the abort path and **none** on the
fallback path. The substitution leaves no log line, so *"did this happen?"* is not
answerable after the fact from the run log.

## What is claimed, and what is not

**Claimed:** the guard that would stop a known, documented failure mode is **disabled** in
the deployed job.

**Not claimed:** that the resolver is currently failing, and therefore **not** that the
stale checkpoint is deciding the book today. That needs a separate measurement against a
separate artifact, and it has not been made. The tool prints that refusal and a test
asserts it prints it — because "the guard is off" reads very easily as the stronger
statement, and only one of the two has been measured.

## The remedy is a production change and is NOT taken here

Arming the guard means editing an installed launchd job — a live run surface. Under the
containment protocol that requires a tracked task with owner and expiry, a durable record
of the literal revert steps, and the reviewed surface (`ops/launchd_manifest.json`)
updated in the same batch. **None of that is done in this PR, and the plist is untouched.**

What this PR ships is the **detector**, so the state stops being invisible:
`ops/failclosed_env_check.py`, exit 1 while any declared job is unarmed.

## Design notes that are load-bearing

- **A read is not an assignment.** `${VAR:-0}` and `[ "$VAR" = "1" ]` are reads. Counting
  them as arming would report every script that merely *mentions* the flag as having set
  it — the fail-open version of this very check, and `daily_104.sh` only ever reads.
- **`"0"` is present-but-off**, and does not arm.
- **Either flag arms it**, because the shell condition is an `OR`.
- **An uninstalled job is a failure, not a pass** — otherwise uninstalling the job is the
  cheapest way to make this check green.
- **A sourced env helper is inspectable too**, or a legitimately armed job would report
  unarmed.
- An **unparseable** plist does not vanish from the denominator; `plutil` is the fallback
  parser, since two annotated plists contain `--` inside an XML comment that `plistlib`
  refuses while launchd loads them fine.

14 tests. Suite: **5045 passed, 2 skipped** — run before the push.

---

## CORRECTION 2026-08-01 — the script path armed on ANY assignment, including `=0`

Reviewed `[codex on orch#695]`: *"The script path treats any assignment as armed,
regardless of its value. A program or sourced helper that exports
`RENQUANT_OPS_FAIL_CLOSED=0` therefore reports ARMED while the job still takes the
fallback path. This is a fail-open false positive and disagrees with the plist branch's
explicit value check."*

Correct, and the sharpest part is the **disagreement**: the plist branch already required
`== "1"`. **One check answered two different ways depending on which half saw the flag** —
so a script setting it to `0` would have flipped this job's verdict to ARMED while the
plist showing `"0"` was correctly rejected.

**Three outcomes now, where there was one:**

| assignment | verdict |
|---|---|
| literal `1`, quoted or not | **arms** |
| literal `0`, or anything else | does **not** arm |
| dynamic — `$OTHER`, a command substitution | **INDETERMINATE**, treated as **not** arming |

A value this checker cannot evaluate must not be read as the safe one. **The last
assignment wins**, matching shell semantics: an early `=1` followed by a later `=0` leaves
the guard off. Every non-arming assignment is reported with its rendered value, so a
reader sees *why*, not just *no*.

**The live result is unchanged: 0 of 1 jobs arm the guard.** Neither flag is assigned
anywhere, so this correction changes no measured conclusion — it removes a way the check
could have said the opposite.

18 tests (was 14): `=0` in four spellings (bare, exported, double- and single-quoted);
dynamic assignment; last-assignment-wins in both orders; and an explicit test that the
**script and plist halves agree** on a zero.

Suite: **5095 passed, 2 skipped**.
