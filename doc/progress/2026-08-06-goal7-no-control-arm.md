# The momentum component has no control arm, so "is it contributing" has no data path   (PR)

STATUS:   delivered — measurement only. No code ships, no production surface touched.

WHAT:     Records that neither marginal arm needed to decompose prod's blend is being
          served: **panel-alone is not configured at all**, and **momentum-alone is
          configured but has no run database**. Prod itself was the panel-alone control
          until the 2026-08-04 promotion consumed it.

WHY/DIR:  GOAL-7. orch#870 ended with *"the live question is now 'is it contributing,
          and what would make us take it out' — and that has no owner today."* This
          measures why: the question is not merely unowned, it is **unanswerable from
          served data**, because the arm you would difference against does not exist.

EVIDENCE:
artifact:      `RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/*.json`
               (all 11 lane configs) and `RenQuant/data/runs.alpaca*.db`
prod or exp:   prod — these are the served lane configs and their live run databases.
existing data: orch#869 mapped the fleet as a clf × momentum factorial and found the
               `fast` momentum level empty. It did not check for the (no clf, no
               momentum) cell. orch#863/#864 established the 08-04 promotion made
               `_mom` a copy of prod and its shadow leg a self-comparison.
best-known?:   yes for arm PRESENCE — read from every lane config and every run DB on
               disk. Not a contribution estimate; see the limits below.
scope:         this is the 11 served lane configs under
               `.subrepo_runtime/repos/renquant-strategy-104/configs/` plus every
               `data/runs.alpaca*.db`, **prod**, and it is a claim about which ARMS
               EXIST — not a comparison against any existing best. There is no
               `<X>=<ic>` to cite here precisely because the arm that would produce
               one (panel-alone) is the arm this doc reports as absent. No IC,
               Sharpe or contribution figure is asserted anywhere in this PR.

          **Every lane containing the panel scorer also contains something else**
          `[VERIFIED — this session, 2026-08-06]`:

          | config | kind | components |
          |---|---|---|
          | `strategy_config.json` (PROD) | blend | panel_ltr **+ momentum_residual** |
          | `shadow_blend` | blend | panel_ltr **+ clf** |
          | `shadow_blend_momentum` | blend | panel_ltr + momentum_residual |
          | `shadow_blend_rb_mom` / `rb_fast` | blend | panel_ltr + clf + momentum |
          | `shadow` / `shadow_a` / `shadow_b` | hf_patchtst | **a different model** |
          | `shadow_momentum` | momentum_residual | **momentum alone** |

          The three decomposition arms:

          | arm | configured? | serving? |
          |---|---|---|
          | panel alone | **NO** | — |
          | momentum alone (`shadow_momentum`) | yes | **NO run database exists** |
          | panel + momentum (PROD) | yes | yes, 250 scored runs since 07-28 |

          Prod was the panel-alone control until 2026-08-04. Its own config records the
          switch: *"prod primary scorer switched to the z(prod)+z(slow momentum) blend"*.

NEXT:     Answering "is momentum contributing" requires serving one of the two missing
          arms — a panel-alone shadow lane is the cheaper one, since the artifact is
          already pinned and served as prod's `component[0]`. That is a
          `renquant-strategy-104` config addition (repo boundary), not actioned here.

## What this does NOT establish

- **Not that momentum is unhelpful.** No contribution was estimated in either
  direction. The finding is that the estimate cannot currently be formed.
- **Not that the promotion was wrong.** Prod ceasing to be the control is a
  consequence of promoting the blend, which was an explicit operator decision.
- **Not that `shadow_momentum` is broken.** It is configured and has no run DB; I did
  not determine whether it is unscheduled, disabled, or failing. That distinction
  matters for the fix and is unmeasured here.
