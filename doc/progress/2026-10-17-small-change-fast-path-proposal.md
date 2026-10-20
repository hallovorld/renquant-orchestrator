# 2026-10-17 — PROPOSAL: a written "small-change fast path" (operator-requested; NOT in force until the operator approves this PR)

STATUS:   proposal, awaiting the operator's own approval. Nothing here changes any ruleset, CODEOWNERS or
          CI; this PR is the written policy that LONG rows 1 and 7 require before any exception exists.
WHAT:     Defines which PRs may merge without a codex review, how eligibility is decided MECHANICALLY
          (not by the author), what stays under full review, and what the operator must change in GitHub
          settings for it to take effect.
WHY/DIR:  Operator, 2026-10-15/17: "我想要的就是永久的'小改动免审'快速通道". Codex review is a monthly-quota
          resource (one burst, next reset 2026-11-02); a 2-line alert-wording PR (#1132) waited on it.
          Rows 1 and 7 forbid the author from creating this exception ("it must be a documented written
          policy the operator creates"), so the agent drafts and the operator ratifies.
EVIDENCE: n/a — policy proposal; no model/data claim.
NEXT:     operator approves/merges this PR as `haorensjtu-dev`, then performs the settings change in §4.

## 1. Eligibility — all must hold, decided by a CI check, not by the author

A PR is FAST-PATH-ELIGIBLE iff a required check `fast-path-eligibility` (to be added in a follow-up PR; absent
check ⇒ nobody is eligible) computes ALL of:

1. Every changed path matches the allow-list: `doc/**`, `**/*.md`, `tests/**` (tests only, no source),
   and — for notification/log text only — files listed in `ops/fast_path_text_only.json` whose diff is
   restricted to string literals inside `notify`/`rq_notify`/`log.*` calls (checked by an AST/regex diff).
2. NO changed path matches a protected pattern: `data/**`, `**/strategy_config*.json`, `**/artifacts/**`,
   `subrepos.lock.json`, `ops/launchd_manifest.json`, `ops/renquant104/sentinel_acks.json`,
   `doc/memory/long-term-agreements.md`, `.github/**`, `CODEOWNERS`, any `*.plist`, any ruleset/policy file
   (including this one), and every PROD_PATH_RULES pattern in `agent_workflows.py`.
3. Diff size ≤ 40 changed lines and ≤ 3 files.
4. Required CI (`test`, `progress-doc`) is green at the head; a progress doc is present (row 6 is NOT waived).
5. The PR carries label `fast-path` AND the check recomputed eligibility at the CURRENT head (a new push
   re-evaluates; eligibility never carries over).

Anything that changes behaviour (exit codes, thresholds, gates, queue logic, trading paths) is never eligible,
however small. "Small" is a path/size fact, not a judgement.

## 2. What the fast path waives, and what it does not

Waived: the codex APPROVE requirement (row 7's mechanical gate) for eligible PRs only.
NOT waived: green CI, the progress doc (row 6), the `merged by …` audit marker before merge, label
`agent:claude`, single-identity commits, post-merge ancestor-of-main verification, and the `-run`/umbrella
sync being a separate ask-first action. Codex still reviews every eligible PR AFTER merge when quota allows
(`post-merge-review` queue); a post-merge CHANGES_REQUESTED opens a revert-or-fix PR within one loop cycle.

## 3. Safeguards

* Rate limit: at most 3 fast-path merges per rolling 24 h per repo; the 4th requires full review.
* Mechanical audit: each fast-path merge posts `fast-path merge: eligibility check <run url>` and appends a
  row to `doc/memory/fast-path-ledger.md`; the weekly drift scan alarms if a merged PR lacks that row.
* Kill switch: deleting the `fast-path-eligibility` required-check bypass (§4) or the label disables it at once.
* Review of the policy itself: edits to this file are protected (§1.2) and always need full review.

## 4. What the OPERATOR must do for it to take effect (the agent will not touch rulesets)

1. Approve + merge this PR as `haorensjtu-dev`.
2. Add the follow-up PR that implements the `fast-path-eligibility` workflow (agent drafts; full review once).
3. In repo settings, edit ruleset `main-protection` (id 17346602) in `renquant-orchestrator` ONLY: add a bypass
   for the merging actor that applies solely when the `fast-path-eligibility` check is green, or switch the
   required-review rule to "required unless check passes" if GitHub supports it for your plan; otherwise use a
   merge-queue/auto-merge workflow owned by `haorensjtu-dev`. Do not disable the ruleset or `enforce_admins`.
4. Amend LONG rows 1 and 7 to cite this policy (separate, fully reviewed PR).
5. Roll out to other repos only after 2 weeks of clean audit in orchestrator.

## 5. Open choices for the operator

* Allow-list breadth: docs+tests only (safest) vs. also text-only ops notifications (as in #1132).
* Rate limit: 3/day vs. 5/day.
* Whether `agent:claude` PRs and `agent:codex` PRs share the lane (recommended: yes, same rules).
