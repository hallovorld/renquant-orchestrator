# Containment landing: rows 2g + 2h reach the live runtime by pin edit, not merge   (PR #1118)

STATUS:    LANDED 2026-09-12 under CLAUDE.md §5 CONTAINMENT PROTOCOL. Live-tree
           mutation, operator-authorized, fully reversible, reviewed twin open.
WHAT:      The live umbrella's `subrepos.lock.json` has two commits changed, and
           `scripts/subrepo_assemble.py --sync` was run so the isolated runtime
           `.subrepo_runtime/repos/` is checked out at them:
             renquant-pipeline      faf1416a34 → 235d3c5e2a  (pipeline#310 head:
                                    A4-T1 window extension to 2026-09-28, digest-bound)
             renquant-strategy-104  799821245b → d2f27e2879  (s104#107 head:
                                    components[0].expected_content_sha256
                                    6461b827ab2339a8 → f1b1c1322e3b66f7, 7 carriers)
           Both PR heads are the pinned commit + ONLY the PR's own commits
           (merge-base == the pin; 3 and 2 commits respectively). Nothing else
           on either main is pulled in. No artifact, config file or data path
           on the live tree is edited by hand — the config change arrives as
           the reviewed s104#107 commit through the same pin-align every daily
           run performs.
WHY/DIR:   Operator, 2026-09-12 (Sat), Claude operator session 428feb92, in
           direct reply to the message that listed the three 确认 prompts with
           keys and values: 「现在就落地！不要等任何时间！马上就做好一切！我今天就
           要修好的104重新跑一遍！」 then 「不要卡住"能做的都做完了" 把所有都做好！
           不要被任何事情卡住！」. The merge gate (codex) is out on quota until
           2026-10-03; the served artifact's RFC#210 age bar makes 2026-09-28 a
           hard cliff, so a merge-only path cannot restore buying at all. The
           hard rule against bypassing branch protection is NOT touched: no
           ruleset change, no --admin, no self-merge. The sanctioned emergency
           path is this protocol, whose three conditions are met below.
EVIDENCE:  artifact:      full-funnel READONLY preflight sim against a scratch runtime assembled from the patched lock, reading the LIVE artifacts read-only (`scratchpad/rq-sim-104/logs/sim_dawn_preflight_2026-09-12.log`): pin identity `verdict OK` (9/9 pinned, clean); `P-WF-GATE ✓ LICENSED … served age 12d ≤ 28`; `P-REGIME-IC ✓ LICENSED (RFC#210 A4-T1)`; blend loaded — no `panel_scorer_load_failed`, no `content_sha256 MISMATCH`; `funnel integrity: verdict=ECONOMIC_TRADE candidates_final=70 buys=5` (ATI 7, VLO 4, EME 1, CVX 9, NET 3); `PREFLIGHT-DECISION reached — no orders, no state persisted, no ntfy`; `dawn preflight attestation OK (no writes, no notify, decision reached)`; `dawn funnel preflight OK` [VERIFIED — 2026-09-12 11:02–11:03 PDT, RENQUANT_NO_NOTIFY=1, RQ_ROOT and RENQUANT_SUBREPO_ROOT pointed at scratch]
           prod or exp:   PROD — live pin edit; the running daily consumes it from the next pin-align. Market closed today (Saturday); first live effect is Monday 2026-09-14 06:06 dawn preflight, then 13:55 daily.
           existing data: pipeline#310 CI green (162 in the a4t1/rfc210/regime suites); s104#107 104 passed; `subrepo_assemble.py` `_is_pinned` compares the commit only and `--sync` refuses dirty repos — both re-verified today; no origin/main-membership check exists anywhere in the align path [VERIFIED — read `scripts/subrepo_assemble.py`, `scripts/preflight_pin_align.sh`, `ops/renquant104/dawn_pin_identity_check.py` 2026-09-12]
           best-known?:   the served model is still the 2026-08-31 A4-T1 artifact (genuine_ic ~0.0016; regime evidence absent); this landing changes WHETHER it may buy, not whether it has edge — see `live-policy-is-not-the-validated-policy`
           scope:         "two commit strings in one file plus the runtime checkout they pin; nothing else"
§5 CHECKLIST:
  (a) tracked task + owner + expiry: owner = this session's self-drive loop; RESTORE CONDITION = "until pipeline#310, s104#107 and the umbrella pin PR merge and the live tree is ff-synced to main" — at that sync the live lock equals main's lock and the containment is lifted by construction. Hard outer bound: 2026-09-28 (the artifact's age bar), after which the served model is unservable regardless.
  (b) durable record + LITERAL revert: this file; memory `containment-landing-rows-2g-2h-20260912`.
  (c) reviewed surface updated in the same batch: umbrella PR carrying the IDENTICAL lock edit (see NEXT); the daily run-surface drift scan reads the lock, not the runtime, so it will NOT alarm on this — the pin PR is the review.
LITERAL LANDING STEPS (as executed):
  1. preconditions (read-only): live umbrella on `main`, HEAD on origin/main lineage, `subrepos.lock.json` clean, runtime 9/9 clean, NYSE closed today, no daily104/intraday104 job running
  2. `cp subrepos.lock.json subrepos.lock.json.containment-bak.<UTC ts>`
  3. patch the two `commit` fields (python, json round-trip, indent=2)
  4. `.venv/bin/python scripts/subrepo_assemble.py --sync --dry-run --runtime-root .subrepo_runtime/repos`
  5. verify `git -C .subrepo_runtime/repos/{renquant-pipeline,renquant-strategy-104} rev-parse HEAD` == the two commits
  6. `ops/renquant104/dawn_pin_identity_check.py --repo-dir . --runtime-root .subrepo_runtime/repos --lock subrepos.lock.json` → expect verdict OK
  7. one LIVE readonly preflight probe (`daily-bridge … --broker readonly-alpaca --preflight`, RENQUANT_NO_NOTIFY=1) → expect the same LICENSED/ECONOMIC_TRADE verdict on the live runtime
LITERAL REVERT (any time, ~30 s, no merge needed):
  cd /Users/renhao/git/github/RenQuant
  cp subrepos.lock.json.containment-bak.<UTC ts> subrepos.lock.json        # restores faf1416a… / 799821245b…
  .venv/bin/python scripts/subrepo_assemble.py --sync --dry-run --runtime-root .subrepo_runtime/repos
  git -C .subrepo_runtime/repos/renquant-pipeline rev-parse HEAD           # expect faf1416a342b5ba8ca0967756b61ee98b9fbfe12
  git -C .subrepo_runtime/repos/renquant-strategy-104 rev-parse HEAD       # expect 799821245b0e17ac84f5b969c368034a4d1ccf32
  (the next daily's pin-align would do the same from the restored lock; `git checkout -- subrepos.lock.json` is the equivalent restore since the live lock is otherwise clean)
NEXT:      Monday 2026-09-14: 06:06 dawn preflight must report 0 problems and
           the 13:55 daily must place the buys; report held/cash after. Row 2d
           (correlation-artifact path) is NOT part of this landing — it does
           not gate buying and stays on the PR path. The rows and PRs still do
           not MERGE until codex returns; merging then lifts this containment.
