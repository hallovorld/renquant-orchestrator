# Workstream: fractional enablement chain (S-FRAC stage 3 / strategy-104#55, #56)

STATUS:   step 5 (pager on the reviewed launchd surface) PREPARED, not
          installed — this PR. `execution.fractional_shares.enabled` and
          `execution.software_stops.enabled` both remain `false` in the
          pinned strategy-104 config
          `[VERIFIED — .subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json:700-705, 2026-08-29]`.
GOAL:     flip fractional under its own LONG-ledger row only after (a) the
          umbrella broker adapter implements `is_fractionable` + the
          no-submit classifier, (b) software stops arm per their stage-3
          packet (registry writer live at the neutral root, pager scheduled,
          page test-fired with measured latency, operator sign-off of the
          machine-death bound), (c) the one-bit flip PR.
          `[VERIFIED — doc/research/2026-08-24-goal1-closeout.md staged plan item 2]`
EVIDENCE: pager job `com.renquant.stops-liveness` now runs the wrapper from
          the PINNED run checkout and is declared in `ops/launchd_manifest.json`
          (digest produced by `scan_launchd_plists`, not typed); installer
          refuses a plist that disagrees with the manifest. Alert-latency
          envelope stays ~18-28 min after the first missed sell-only pass
          (B=30 max_staleness, C=12 cadence, I=10 StartInterval) vs the
          design's page <=15 min — NOT met; the drill measures D and the
          operator either tightens B or signs off the envelope.
          `[DERIVED — doc/progress/2026-07-11-stops-liveness-pager-package.md:655-664 formula, values re-read 2026-08-29]`
NEXT:     (1) writer migration: sell-only loop stamps the registry at
          `~/.renquant/runtime/software-stops/` (renquant-execution + R-PIN
          landing); until then `install --apply` is refused by the registry
          guard and the daily drift scan reports the job manifested-but-
          missing — the designed reminder. (2) after merge + `-run` sync:
          `scripts/install_stops_pager.sh install --apply` (ask-first landing),
          then `test-fire STALE` and record delivery + response latency in a
          dated progress doc. (3) operator sign-off row for the envelope.
CONSTRAINT: never install from an agent session without the landing grant;
          never hand-edit `ops/launchd_manifest.json` outside review; the
          plist's topic/interpreter/data-root are reviewed arming-time
          configuration (Codex r2 on #460, #481 rounds 5-8) — no ambient env.
