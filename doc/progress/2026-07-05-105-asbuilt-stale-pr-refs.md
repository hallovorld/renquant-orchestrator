# fix stale 105 as-built PR references

STATUS:   fixed and pushed.
WHAT:     `doc/design/renquant-105-as-built.md`'s Status section cited PR #333 ("pending
          review") for the session runner and software stops deliveries.
WHY/DIR:  #333 was closed and superseded by #335 earlier this session; the as-built doc
          went stale relative to the actual merge history. An as-built doc citing a closed,
          unmerged PR as the delivery record is a false fact.
EVIDENCE: `gh pr view 333 --repo hallovorld/renquant-orchestrator` → state CLOSED, mergedAt
          null; `gh pr view 335 --repo hallovorld/renquant-orchestrator` → state MERGED.
          `[VERIFIED — gh pr view, this session]`
NEXT:     none — one-line factual correction, no follow-up required.
