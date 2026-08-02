# 2026-08-02 — sentinel: config check reads the PIN; arming window for never-reported lanes

STATUS: complete (two fixes + 6 tests; both proven on the machine before and after)

WHAT: (1) `default_strategy_config()` claimed "the PINNED config" but resolved
the DEV SIBLING checkout (`<github>/renquant-strategy-104/configs/...`) — a
mutable tree, measured behind the lock. Resolution now prefers
`RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
(the pin-materialised clone the daily run serves), sibling as dev-machine
fallback, env override first as before. (2) A lane DECLARED in config that has
NEVER written a health record is in its ARMING window — the patrol's
look-back predates the declaration — and now reports "ARMED — awaiting first
record" (printed, rc 0) instead of a manufactured FEED DARK. Bounded by the
observable arming instant (the config file's mtime = pin arrival on this
machine): after ARMING_DARK_SESSIONS (5) post-arming live-run sessions with
still no record ever, the lane falls through to the full patrol and alarms.

WHY/DIR: GOAL-1. Both defects measured live on 2026-08-02, minutes after the
RenQuant#555 sync: the patrol reported the retired `previous_primary` lane as
declared and the momentum lane as undeclared (stale sibling; the pin said the
opposite — the wrong-object class of RenQuant#553), and after fixing that, it
paged FEED DARK for the momentum lane over 2026-07-30/31 — sessions that
PRE-DATE the lane's declaration. A first grace design (count any 5 historical
live-run sessions) was measured to exhaust instantly on a daily-run machine
and was replaced by the mtime-anchored count in the same sitting.

EVIDENCE:
- artifact: this PR's diff; three live read-only sentinel runs on the machine
  (before: stale-sibling readout + manufactured DARK; after: ARMED 0/5 with
  arrival date 2026-08-02, no false page; clf DEGRADED unchanged both sides)
- prod or exp: sentinel module + tests only; live runs were read-only
- existing data: sentinel suite 91 passed (3 resolver tests + the revised
  arming-window transition test with its grace-exhausted twin); full suite
  5456 passed / 0 failed after merging main
- best-known?: yes — every behavior above read from the machine, not asserted
- scope: `default_strategy_config`, the arming branch in `_patrol_lane`, the
  `config_path` plumb-through, `ARMING_DARK_SESSIONS`; watch registry,
  classification, ack semantics untouched

NEXT: none for this fix. Monday's daily run writes the momentum lane's first
health record; the ARMED line disappears on its own. The clf coverage_frac>1
streak stays tracked in orch#727.

## Review round 1: the arming anchor was mutable

Blocking, and correct. The deadline was keyed to the config file's **mtime**, which
every `subrepo_assemble --sync` and every re-materialisation refreshes. This PR's own
comment called that *"bounded and honest"*. It is neither: routine syncs reset the
grace indefinitely, so a declared-but-never-reporting lane stays INFO forever — the
silent death this sentinel exists to prevent, restored through the door marked
"grace".

**mtime is a property of the filesystem OPERATION.** The declaration's arrival is a
property of the CONTENT, and git already records it. `lane_declared_since()` reads the
date the lane's name first entered the config from git history:

* re-materialisation replays the same commits, so the date does not move;
* an unrelated config edit does not move it either — the search is for the commit that
  introduced *this lane's* name, not the file's last touch.

Measured on the real runtime checkout
(`RenQuant/.subrepo_runtime/repos/renquant-strategy-104`):
`topdecile_clf_blend_leg` → **2026-07-26**, `momentum_residual_v0_shadow` →
**2026-08-02**, an undeclared name → **None**
`[VERIFIED — direct call, 2026-08-02]`.

**An unestablishable anchor grants NO grace.** If the date cannot be read — no git, not
a checkout, name absent — the lane falls through to the full patrol. An unknown anchor
buying unbounded silence is the defect being fixed, not a gentler version of it.

| claim | value | provenance |
|---|---|---|
| module tests | 93 passed, 2 skipped (4 new) | [VERIFIED — `pytest -q tests/test_rq104_shadow_scorer_sentinel.py`] |
| all 4 are load-bearing | all fail against the mtime-anchored version | [VERIFIED — `git show HEAD:…` over the fix, re-run] |
| repeated re-syncs cannot extend it | 3 rewrites + `os.utime`, anchor unchanged; the test also asserts the mtime really moved, or it would prove nothing | [VERIFIED — in the test] |

The regression uses a real `git init` repo rather than a mock, because the anchor **is**
git history — mocking git would test the mock.

Round 3 (review): the `-S` first-hit anchor backdated a removed-then-
re-declared lane to its ORIGINAL arrival (instantly exhausting the new
incarnation's grace) and could match unrelated text. `lane_declared_since`
now parses the config at each revision (newest→oldest, capped at 50) and
returns the most recent absent→present transition of
`ranking.panel_scoring.shadow_models[].name`; unparseable revisions carry no
evidence. Two regressions with explicit distinct commit dates: re-declared
lane arms at the re-declaration (07-01→removed 07-05→re-declared 07-10 ⇒
07-10); a narrative mention outside shadow_models does not backdate. Stale
mtime wording in the arming comment replaced.
