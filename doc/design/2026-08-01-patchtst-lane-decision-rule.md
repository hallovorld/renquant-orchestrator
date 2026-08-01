# A frozen decision rule for the `hf_patchtst` shadow lane

**Status: FROZEN for limb B. Limb A is recorded, not decided here.**
Written 2026-08-01, before any verdict on limb B is computed.

## Why this document exists

The `hf_patchtst` lane has been carried as a live shadow lane while nothing decides its
fate. The standing note is that its apparent margin may come from stale-score inertia
rather than signal. That question is *statistical* and, as of today, **not answerable** —
see limb B. But the lane's status does not actually hang on it, and conflating the two is
what has kept the lane undecided.

So the two limbs are separated deliberately.

## Limb A — governance. Already answered, by a policy that predates this document.

These are deterministic facts, not test statistics. No dependence correction, no
inference, no threshold invented here:

| fact | value | source |
|---|---|---|
| served artifact staleness | **625 d** (624 d on 07-30) | `rq104_shadow_scorer_sentinel --as-of 2026-07-31` `[本次实测 2026-08-01]` |
| shadow staleness limit | **28 d** (`STALENESS_MAX_DAYS`, RFC #210) | `rq104_shadow_scorer_sentinel.py:284` |
| breach factor | **≈ 22×** | derived from the two rows above `[推导]` |
| weekly retrain outcome | **has not acted on 4 consecutive runs**, 3 of them crashes | `rq104_silent_refusal_sentinel --dry-run` `[本次实测]`, see orch#724 |
| sentinel verdict, every session day | `NOT ACTIONABLE / DEGRADED` | as above |

The 28-day limit was set by RFC #210 long before this document; applying it is compliance,
not a threshold chosen after seeing the data.

**A model that has not been refreshed for 625 days against a 28-day policy is not a lane
awaiting evidence — it is a lane out of compliance.** Whether its edge is real is moot
while nothing can refresh it: orch#724 records that the retrain crashes on corpus schema
drift, so the lane cannot be brought into compliance without an upstream fix.

Not decided here, because it is an operator call and a live-surface change: whether to
retire the lane, or fix the retrain (orch#724) and let it re-qualify.

## Limb B — merit. FROZEN NOW, executable only after model#153.

The question: **does `hf_patchtst` carry per-date cross-sectional skill that survives a
dependence-honest null?**

### Why it cannot be run today

`renquant-model#153` measured, on the committed per-date series:

* the real PatchTST per-date IC series has **ρ₁ = 0.8222**, and **ρ₂ = 0.8018 ≫ ρ₁² =
  0.6761** — it is *not* AR(1) and decays more slowly than AR(1);
* its permutation null has **ρ₁ = −0.0623**, i.e. permutation destroys the dependence it
  is meant to calibrate;
* `N/h` as degrees of freedom errs in both directions and is not usable.

So every off-the-shelf yardstick for this arm is currently invalid. Running the test now
would repeat exactly what closed model#124/#128/#135.

### The rule, frozen

Executed **once**, after and only after model#153's inference method is specified and
calibrated, and using that method unchanged:

1. **Statistic**: mean per-date cross-sectional IC of `hf_patchtst` on the `inter142`
   universe, over the full committed series (n = 565).
2. **Null**: the dependence-preserving null specified by model#153 — *not* the existing
   `ic_perm` column, whose ρ₁ ≈ 0 makes its width wrong for this series.
3. **Per-arm**: the dependence correction is estimated for THIS arm's series. A global
   block length or a shared ρ is disallowed, because this arm is the one that is not
   AR(1).
4. **Positive control**: the same procedure must be run on
   `per_date_selftest_selftest_pure_noise_real.csv` and must NOT reject. If the control
   rejects, the procedure is broken and no verdict is read from the real arm.
5. **Comparator, stated in advance**: the co-committed arms' series means are
   `certified_clf 0.0830` and `prod_XGB 0.0907` against PatchTST's **0.0164**
   `[本次实测 2026-08-01]`. These are recorded now so the bar cannot be moved later. They
   are *descriptive* — no claim is made that any of the three is significant.
6. **Decision**:
   * **RETIRE** the lane if the dependence-honest test does not reject at the
     preregistered level;
   * **RETAIN as shadow only** if it rejects *and* limb A is satisfied (artifact inside
     the 28-day limit);
   * **RETAIN pending refresh** if it rejects while limb A is breached — retention is on
     the evidence, deployment still blocked by governance.
   * A rejection never licenses promotion out of shadow; that needs the WF gate, which
     orch#726 shows is separately compromised for the prod lane.

### What would invalidate this rule

Any change to the committed per-date series, the universe, or the horizon after this
freeze. If those change, this document is void and a new one must be frozen before the
test is run.

## Not claimed

That PatchTST has no edge — limb B is explicitly undecided and this document exists so it
stays undecided until it can be decided properly. That 0.0164 < 0.0830 means anything on
its own; three uncalibrated means are not a ranking. That retiring the lane is the right
call — limb A names the compliance breach and hands the decision to the operator.
