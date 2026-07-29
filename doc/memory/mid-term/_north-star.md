# NORTH STAR (MID tier)

> Last updated 2026-07-28 (agent proposal; operator confirms). Previous: 2026-06-17.

**daily-full trades again, driven by a model with genuine positive real cross-sectional
IC that passes the WF gate — then raise *live* return (payoff, not hit-rate).**
Canonical plan: PR #150. Each active workstream below is one file in this folder.

Open workstreams: `model-edge.md` · `serving-reliability.md` · `win-rate-payoff.md`
· `intraday-governor.md` · `agent-control.md`.

**2026-07-28 addition — `serving-reliability.md`.** The north star assumes that once a
model has edge it will actually drive the funnel. One day of work found four independent
defects where a served model's opinion never reached the decision line and the run
reported a normal "no trade" anyway (unsatisfiable freshness SLA; over-specified frame
cache; raw-vs-probability unit mismatch; umbrella kernel fork lag). Edge that cannot
reach the order path is worth zero, and its absence is currently indistinguishable from
a model declining to trade — so this is a peer of `model-edge.md`, not a subtask of it.
