# Twin-parity re-pin: readonly_broker after umbrella #538

Date: 2026-07-28
PR: chore/twin-parity-repin-readonly-broker

`make test` failed on `test_live_twin_parity_manifest_current`:
`diverged_pin:readonly_broker` — the umbrella side
(`RenQuant/live/broker_readonly.py`) changed in the reviewed+merged
umbrella #538 (`edc6d61 feat(live): shadow_blend rail — parameterized
readonly tag + daily Step 5`) and the orchestrator's pinned divergence
hash was not re-pinned alongside.

This PR re-pins via `scripts/check_twin_parity.py --write-manifest`
(one hash line changed; new sha `75373e85f627d3b5…`). Verified the
umbrella-side delta is exactly the #538 tag parameterization — no other
edits to the file since the previous pin. Suite after re-pin:
twin-parity 14/14 pass, full `make test` green.
