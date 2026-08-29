# Workstream: fractional enablement chain (S-FRAC stage 3 / strategy-104#55, #56)

STATUS:   step 5 (pager on the reviewed launchd surface) in PREPARATION —
          orch#1077 r2: pinned-run plist + installer manifest guard only; the
          manifest entry, install and test-fire are DEFERRED to one landing
          PR. `execution.fractional_shares.enabled` and
          `execution.software_stops.enabled` both remain `false` in the
          pinned strategy-104 config
          `[VERIFIED — .subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json:700-705, 2026-08-29]`.
GOAL:     flip fractional under its own LONG-ledger row only after (a) the
          umbrella broker adapter implements `is_fractionable` + the
          no-submit classifier, (b) software stops arm per their stage-3
          packet (registry writer live at the neutral root, pager declared +
          installed + test-fired with measured latency, SLA decision, operator
          sign-off of the machine-death bound), (c) the one-bit flip PR.
          `[VERIFIED — doc/research/2026-08-24-goal1-closeout.md staged plan item 2]`
EVIDENCE: pager plist `deploy/com.renquant.stops-liveness.plist` runs the
          wrapper from the PINNED run checkout; `install_stops_pager.sh`
          refuses (exit 4) an unmanifested or disagreeing plist; the drift
          scan's resolver now inspects a manifested `scripts/` wrapper.
          NOT in the manifest yet (Codex on #1077: a manifested-but-missing
          job pages the ops topic daily = standing false positive).
          SLA NOT SATISFIED: envelope ~18-28 min after the first missed
          sell-only pass (B=30, C=12, I=10) vs design page <=15 min.
          `[DERIVED — doc/progress/2026-07-11-stops-liveness-pager-package.md:654-664 formula, values re-read 2026-08-29]`
NEXT:     OPEN DECISION (operator): (a) strategy-104 config PR lowering
          `max_staleness_minutes` (ledger row; B<=17 at I=10, B<=22 at I=5),
          or (b) explicit exception accepting the envelope per the design.
          THEN the landing PR: manifest entry (scanner-emitted) + `install
          --apply` + `test-fire STALE` with recorded latency, gated on the
          registry writer (orch seeder PR in flight) + `-run` sync. Until
          both land the job is NOT eligible to install and is NOT step-5
          evidence.
CONSTRAINT: never install from an agent session without the landing grant;
          never hand-edit `ops/launchd_manifest.json` outside review; the
          plist's topic/interpreter/data-root are reviewed arming-time
          configuration (Codex r2 on #460, #481 rounds 5-8) — no ambient env.
