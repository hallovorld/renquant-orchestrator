# Progress: the mechanical half of the pre-push checklist

STATUS:   delivered (tool + 17 tests, dogfooded against this repo). Not wired
          into a hook — that is a machine landing and needs an operator grant.
          Hand-runnable: `python3 tools/pre_push_check.py`.

WHAT:     `tools/pre_push_check.py`. Four GATES — authoring branch is not
          `main`/`master`; branch base is current; the diff contains no
          unintended deletions or whole-file rewrites; the progress doc passes
          the contract. Plus repo placement as INFO, which never blocks.
          The progress-doc contract is IMPORTED from
          `renquant_orchestrator.agent_workflows`, not reimplemented, with a
          test asserting the two are the same function object so they cannot
          drift into a second opinion.

WHY/DIR:  Every contract check in `agent_workflows` operates on a PR dict
          fetched from GitHub — it answers "is this PR compliant" AFTER the
          push. Measured 2026-07-29, five separate defects in one session all
          happened BEFORE that point and each was mechanically detectable at
          the time:

            1. a branch edited in the PRIMARY checkout on `main`;
            2. a branch whose base had moved, so its diff would have DELETED a
               file another PR merged in the meantime;
            3. a one-entry JSON edit that reserialized the whole file
               (270+/270-) — breaks nothing, makes review impossible;
            4. a progress doc using `EVIDENCE (§4(b)):`, which the checker's
               `^EVIDENCE:` match does not accept;
            5. model-evaluation research committed to the orchestrator instead
               of `renquant-model`.

          Reviewers caught all five. That is the expensive way to catch a
          category error `git` can answer in a second. The operator's
          complaint about defect volume is what prompted this; a checklist I
          promised to follow is not a mechanism, which is the distinction
          CLAUDE.md opens by making.

          Placement (5) is deliberately INFO, not a gate. Whether a change
          belongs in a repo depends on what the code MEANS; a regex guessing
          at it would either miss the real cases or block correct ones.
          Labelling a guess as enforcement would repeat the exact error the
          rest of this tool exists to correct.

EVIDENCE: artifact: `tools/pre_push_check.py` +
                    `tests/test_pre_push_check.py`, this branch on
                    `renquant-orchestrator` @ origin/main 1a65397d.
  prod or exp:      PROD agent tooling, READ-ONLY. Plain git queries; mutates
                    no checkout, installs no hook, writes nothing.
  existing data:    Yes — each test builds a real git repo reconstructing one
                    of the five incidents, so the tool is pinned against what
                    actually happened rather than against my description of
                    it. Dogfooded this session: run against the PRIMARY
                    orchestrator checkout it reported `[BLOCK] branch:
                    authoring on protected branch 'main'` — the live instance
                    of incident 1, still sitting there — and against this
                    branch it reported the missing progress doc before this
                    file existed.
  best-known?:      For the four mechanical classes, yes. NOT claimed: that
                    this catches every pre-push error, or that placement is
                    decided.
  scope:            `renquant-orchestrator` tools + tests. No pin advanced, no
                    umbrella change, no live surface mutated, no hook installed.

SCOPE/LIMITS:
          The whole-file-rewrite heuristic fires when a diff removes >=50 lines
          and re-adds >=90% of that count. It will not notice a 20-line file
          reformatted, and it can fire on a legitimate large rewrite — it says
          so in the message rather than asserting a defect. `--skip-progress-doc`
          exists for branches that legitimately carry none.

VERIFICATION:
          17 tests pass, one per reconstructed incident plus the negative case
          for each (a feature branch, a current base, a targeted edit, a
          compliant doc). Live dogfood output recorded above.

NEXT:     Wiring this as a pre-push hook is a machine landing and needs an
          operator grant; until then it is a hand-run tool, which means it
          still depends on me running it. That gap is real and worth naming:
          the mechanism is only half-built until it runs without my choosing to.
