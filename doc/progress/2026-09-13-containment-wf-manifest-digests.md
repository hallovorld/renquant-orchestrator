# Containment: the live WF manifest carries RenQuant#639's digests   (2026-09-13)

STATUS:    LANDED 2026-09-13 13:21:36 PDT on the live umbrella tree under CLAUDE.md §5
           CONTAINMENT, on the operator's explicit grant (reply 「2」 to the two-option
           report at ~12:4x PDT, option 2 = "copy #639's manifest onto the live path,
           backup + revert + record, reviewed twin = #639"). NOT merged; lifts when
           RenQuant#639 merges and the live tree is synced.
WHAT:      One file: `backtesting/renquant_104/artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json`
           origin/main blob 515e1cc02f13 → RenQuant#639's blob 5251c58454ec
           (sha256 e7335d15c86c0ae8): +86 lines, `artifact_sha256` and
           `calibrator_sha256` on all 43 entries, nothing else. Backup next to it:
           `…calibrated.json.containment-bak.20260913T202136Z` (untracked). The 86 corpus files
           #639 also commits were verified byte-identical on the live tree BEFORE
           landing (86/86 by `git hash-object`), so no corpus scorer or calibrator
           was written.
           §5 checklist: (a) owner = the unattended orchestrator session / its loop;
           expiry = "until RenQuant#639 is merged and the live tree synced" (hard
           outer bound: none needed — the digests are the merged content);
           (b) this record + memory `containment-wf-manifest-digests-20260913`
           with the literal revert below; (c) reviewed surface = RenQuant#639
           (identical manifest bytes; +tests +workflow), open since 2026-09-04.
WHY/DIR:   The weekly promote gate's WF SIMULATION crashed on every candidate since
           2026-09-01: `ManifestUriResolutionError … requires a stamped
           artifact_sha256 digest (compatibility window closed 2026-09-01)` —
           `kernel/manifest_uri_resolver.ARTIFACT_DIGEST_REQUIRED_AFTER` closed on a
           manifest the 2026-07-18 stamping pass never touched. Candidates
           09-01/02/03/05/06/10/11/13 all carry `wf_reason = "3/3 sim cuts failed
           execution"`, `cuts[*].returncode = 1`, and the wrapper reported each as
           a calm `WEEKLY-REJECT (prod fresh — no action)`. The fixes (#639, #641)
           are blocked behind the codex review quota until 2026-10-03. The operator
           ordered the WF path fixed (「wf设置有问题！解决好！」) and, given the
           one-file scope, chose the containment over waiting.
EVIDENCE:  preflight:  full 3-cut WF gate run on these exact bytes in a scratch copy
                       of the strategy dir (`scratchpad/wf-proof`, live untouched),
                       2026-09-13 12:09–12:18 PDT: 3/3 cuts returncode 0, three
                       round-trip ledgers, trade_contract PASS (20 rows); verdict FAIL
                       on substance — Sharpe +0.515/+0.487/+0.714 vs SPY
                       +0.715/+0.749/+1.778 (mean +0.572 vs +1.081, 0/3), monotonicity
                       FAIL (BULL_CALM n=18), placebo FAIL — the same shape as the
                       last successful live sim on 08-23 [VERIFIED]
           landing:    backup blob 515e1cc02f13 ✓; live blob after copy 5251c58454ec ✓;
                       `stamp_wf_manifest_digests.py --check` on the LIVE manifest:
                       43 entries, 0 problems; the exact post-window loader call
                       `resolve_manifest_uri(…, require_digest=True)` resolves 86/86
                       scorer + calibrator URIs against the live corpus; the backup
                       (unstamped) manifest still raises the window-closed error
                       [VERIFIED 2026-09-13 13:21 PDT]
           git view:   the manifest is now the 87th dirty tracked file under
                       artifacts/sim + walkforward_gbdt_prod_recipe_v2 (86 were the
                       pre-existing Step-3.5 stamps that #639 commits); one untracked
                       backup. The daily run-surface drift scan cannot see this
                       (it reads umbrella git metadata as files) — orchestrator#1122
                       adds pin-lineage alarms for the runtime repos, not for umbrella
                       artifacts; the reminder is this record and the session loop.
           smell:      `stamp_walkforward_fingerprints.py` (Step 3.5) writes the
                       scorer's ABSOLUTE path into each calibrator
                       (`metadata.scorer_artifact`), so calibrator digests are
                       checkout-location-dependent; idempotent in situ, rewrote all 43
                       calibrators in the relocated scratch copy. Follow-up, not here.
           scope:      "one manifest file on the live tree gains the digests #639
                       carries; no corpus bytes, no config, no pin, no job changed"
NEXT:      Proof of effect = the next WF gate run (conditional-retrain104 weekdays
           13:10, anomaly-gated; retrain-panel104 Sun 10:00) must stamp
           `cuts[*].returncode = 0` and a real verdict. Lift: merge #639 (+#641),
           then sync the live tree — git will refuse to overwrite the 87 dirty
           tracked files even though their bytes equal the merged ones, so:
           `git stash push -- backtesting/renquant_104/artifacts/sim backtesting/renquant_104/artifacts/walkforward_gbdt_prod_recipe_v2`
           → `git pull --ff-only` → `git hash-object <manifest>` == merged blob →
           `git stash drop`. Landing action: ask-first.
           LITERAL REVERT (~5 s):
           `cp /Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json.containment-bak.20260913T202136Z /Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts/sim/walkforward_manifest_gbdt_prod_recipe_v2.calibrated.json`
           and confirm `git hash-object` prints 515e1cc02f13….
