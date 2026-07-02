# S11 live-tree inventory — audit PR

STATUS:   research/audit record (read-only; no git mutation in any live/working checkout).
REVISION: r1.
WHAT:     `doc/research/2026-07-02-s11-live-tree-inventory.md` — the S11 deliverable: every
          live-tree dirt item classified and ticketed or resolved. Headline: the adapter-save
          NameError fix is ALREADY durable (verified umbrella origin/main:runner.py:1785
          ships self._config) — the stale memory claim ("origin/main still ships the
          NameError") is corrected; the local diff is residue on a checkout that is BEHIND
          origin/main. Re-stamp artifact dirt → ticketed to M6/R2 (fingerprint unification).
          Data churn → normal. Backtesting working-copy residue → content already merged
          upstream (#54 etc.); cleanup is a landing action outside this loop's lane.
WHY/DIR:  #231 Term PROCESS / floor tier-2: the undisciplined floor is unbounded until
          live-tree dirt is inventoried; S11's AC ("diff empty or fully ticketed") is met by
          this audit. The one standing risk is documented for the lander: the checkout is
          behind origin/main WITH overlapping dirt — naive pull conflicts, naive
          reset/checkout is the 06-25 incident; the safe-landing drill doc remains R7's open
          deliverable.
EVIDENCE: read-only git status/diff/show outputs quoted in the memo (2026-07-02).
NEXT:     Codex review; lander executes the sync per the standing-risk note; R7's drill doc
          is the remaining open slice.
