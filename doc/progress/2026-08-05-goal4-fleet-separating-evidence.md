# GOAL-4: the fleet's first measured number — 9 of 35 lane-days separate from prod

STATUS:   delivered (first measurement; not a kill or a green light — a premise check).
WHAT:     measures the cheap half of the ensemble premise (do fleet lanes disagree with prod)
          over 7 dates x 5 lanes = 35 lane-days: 9 `DIVERGED`, 4 `RAN_AND_SCORED_NOTHING`, 2
          `SAME_TOP_K_AS_PROD`, 20 `NO_RUN_ON_THIS_DATE` (expected — 4 lanes stood up 08-04/08-05).
WHY/DIR:  GOAL-4 (multi-model ensemble) — an ensemble needs components that disagree with the
          primary AND are individually skilled; this measures only disagreement and finds `_mom`
          is not a component at all (ρ=0.9998 vs prod, 10/10 top-k overlap, 1.5% residual variance
          after an affine fit) while `_mom_fast`/`_rb_fast` have never emitted a score (2/2
          `RAN_AND_SCORED_NOTHING`, confirming orch#845 from the serving side).
EVIDENCE: evidence bundle `doc/evidence/2026-08-05-fleet-divergence-bundle.json`
          (sha256 b44939485b2d3469cb4f57bd6cfd6bc51d0cba307ada078ab10cd814b64e9ff8), cited instead
          of the mutable sqlite DB the probe reads from; the probe refused
          (`PROD_BASELINE_UNAVAILABLE`) on a zsh word-splitting bug in the first run rather than
          silently reporting "0 of 35 separate", which would have been a shell-quoting artifact,
          not a finding. `[VERIFIED — this session, probe run over 7 dates x 5 lanes this session]`
NEXT:     orch#845 (the two dark lanes) now has serving-side evidence and can be closed by a fix;
          inspect `_mom`'s inputs before treating it as a component (if it is prod's feature set
          plus a near-zero-weight momentum leg, it needs a weight, not a rebuild); skill remains
          unmeasured and is the actual gate — extending the bundle daily is cheap, forward returns
          are what would convert `DIVERGED` into a reason to ensemble anything.

## Bottom line

An ensemble needs components that (a) disagree with the primary and (b) are
individually skilled. This measures **only (a)** — the cheap half — because (a)
is necessary, and if it fails there is nothing to ensemble regardless of skill.

Over the 7 dates where prod and any fleet lane both scored `[VERIFIED — this session]`:

| lane-day state | n | share |
|---|---:|---:|
| `NO_RUN_ON_THIS_DATE` | 20 | 57 % |
| **`DIVERGED`** | **9** | **26 %** |
| `RAN_AND_SCORED_NOTHING` | 4 | 11 % |
| `SAME_TOP_K_AS_PROD` | 2 | 6 % |
| **total** | **35** | |

**9 of 35 lane-days produced separating evidence.** The 20 `NO_RUN` cells are
mostly the four lanes stood up 08-04/08-05 and are *expected*, not a defect —
they are reported rather than dropped so the 26 % is never read as 26 % of a
mature fleet.

Evidence bundle: `doc/evidence/2026-08-05-fleet-divergence-bundle.json`
(sha256 `b44939485b2d3469cb4f57bd6cfd6bc51d0cba307ada078ab10cd814b64e9ff8`).
The probe reads a **mutable** sqlite, so the bundle — not the DB — is the record
this document cites.

## Per lane

| lane | days | state | median ρ vs prod | median top10∩ | median affine resid |
|---|---:|---|---:|---:|---:|
| `alpaca_shadow_blend` | 7 | `DIVERGED` ×7 | 0.9289 | 6.0/10 | 3.2985 |
| `alpaca_shadow_blend_mom` | 7 | `SAME_TOP_K` ×2, no-run ×5 | **0.9998** | **10.0/10** | **0.0149** |
| `alpaca_shadow_blend_rb_mom` | 7 | `DIVERGED` ×2, no-run ×5 | 0.9226 | 7.5/10 | 0.5253 |
| `alpaca_shadow_blend_mom_fast` | 7 | **`SCORED_NOTHING` ×2**, no-run ×5 | — | — | — |
| `alpaca_shadow_blend_rb_fast` | 7 | **`SCORED_NOTHING` ×2**, no-run ×5 | — | — | — |

### Two findings that matter more than the headline

**1. `_mom` is not an ensemble component — it is prod.**
ρ = **0.9998**, top-10 overlap **10/10**, affine residual ratio **0.0149**. After
fitting an affine transform to prod's scores, **1.5 % of the variance is left**.
Averaging a series with an affine transform of itself returns the same ranking;
whatever this lane contributes to a blend, it is not diversity. It should not be
counted as a component until its inputs are shown to differ.

**2. `_mom_fast` and `_rb_fast` have never emitted a score.**
Both are `RAN_AND_SCORED_NOTHING` on **2 of 2** dates they ran — a run row exists,
no candidate carries a `panel_score`. This confirms **orch#845** (both point at
`artifacts/momentum_fast/`, which does not exist) from the serving side rather
than from the config side. They run daily, exit clean, and produce nothing.

That is the *deployed-but-dark* failure again: two lanes have been consuming a
scheduled slot and reporting success while contributing zero evidence, and no
alarm distinguishes them from a lane that ran and legitimately found nothing.

## What this does NOT establish

- **Nothing here is about skill.** `DIVERGED` means *different*, not *better*.
  A lane that disagrees with prod and is wrong is worse than no lane. Every ρ
  above is a rank correlation between two score sets, with no forward return in
  it.
- **7 dates, and only 2 for four of the five lanes.** No claim about a lane's
  behaviour beyond the dates in the bundle. The `_mom` ρ = 0.9998 rests on **2
  lane-days** — enough to justify inspecting its inputs, not enough to conclude
  it is permanently degenerate.
- **The prod baseline itself is unvalidated.** Per the standing GOAL-4 anchor,
  the prod recipe measured `genuine_ic = +0.00079` and the WF gate admits on
  recipe hash without scoring the candidate. Divergence *from* a baseline with no
  established edge is not evidence of edge in either direction.

## Method note — a refusal that paid for itself

The first run of this probe passed all 7 dates as a single string (zsh does not
word-split unquoted expansions). The probe returned
`PROD_BASELINE_UNAVAILABLE` with the detail *"reporting the lanes as 'no
separating evidence' would publish a missing control as a finding"* — the
refusal added in orch#826 — instead of an empty, plausible-looking zero.

Had it not refused, this document would have opened with **"0 of 35 lane-days
separate from prod"**, which is a far more dramatic claim than the true one and
would have been entirely an artifact of my shell quoting.

## Next

1. **orch#845** — the two dark lanes now have serving-side evidence; that issue
   can be closed by a fix, not by argument.
2. **Inspect `_mom`'s inputs** before it is treated as a component. If its
   feature set is prod's plus a momentum leg with near-zero weight, the ρ is
   explained and the lane needs a weight, not a rebuild.
3. **Skill is still unmeasured** and remains the gate. Extending the bundle
   daily is cheap; forward returns are what convert `DIVERGED` into a reason to
   ensemble anything.
