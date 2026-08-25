# S3-c package: the pinned-config prerequisite is SATISFIED

STATUS: docs-only; the same-day completion note #1060 promised.

§4(b): the 2026-08-25 06:25 scheduler session COMPLETED cleanly [VERIFIED —
post-close manifest read at 13:58 PT]: strategy_config_fingerprint =
sha256:af2344af… (the pinned config's hash), errors=[], mode=shadow,
kill_switch=false, last tick 15:49:30 ET. Path identity rests on the
deployed wrapper's fail-closed `--verify-file` resolution (#1044), not on
hash uniqueness (the sibling has carried identical bytes since returning
to main). The _DRAFT marker now distinguishes prerequisite from readiness [codex r1]:
outstanding are (1) the S3-b ladder criterion (>=10 paired shadow sessions,
zero causality violations, no crash/skip days) — current counts: scheduler
lane 1 clean, serving lane 0 (reset by #1063) — and only then (2) the
operator identity/date/expiry/allowlist fields. The old
shadow_sessions_clean: 13 binds to sibling-config evidence and does not
stand in. Clean-session counting toward S3-c starts
today for the scheduler lane; the serving lane counts from its first
session under the 150s replay constant (orch#1063).
