# S3-c package: live_config_fingerprint bound to the first pinned session

STATUS: docs-only; fills the one factual field the #1042 drafts left open,
per their own _HARD_PREREQUISITES.

§4(b): the 2026-08-25 06:25 scheduler session — the FIRST after the
orch#1041/#1044 deploy (orch-run aaf06a2d, 2026-08-24 10:24 PT) — recorded
`strategy_config_fingerprint =
sha256:af2344af61157cd48ed3b4e41a6090bc4ea19227b9969d3ee616f4bb28982800`,
which equals `hash_jsonable` of the PINNED
`.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`
and matches NO other candidate surface (sibling and umbrella configs hash
differently — measured 2026-08-24) [VERIFIED — manifest read + hash
replication, byte-exact method proven against the 08-24 sibling binding].
Session manifest shows mode=shadow, errors=[].

Operator identity/date/expiry placeholders remain the operator's act; the
prerequisite note now records WHEN and HOW the pinned-resolution condition
was satisfied, and that clean-session counting toward S3-c starts from this
session.
