# Deployment-pin authority migration: umbrella lock → renquant-orchestrator (R-PIN)

STATUS: DESIGN ONLY — no implementation, no migration execution in this PR.
DATE: 2026-07-11
SCOPE: ownership + migration plan for the deployment-pin authority
(`subrepos.lock.json` and its consumers). Registers as remediation stage
**R-PIN** in the architecture-compliance roadmap
(`doc/design/2026-07-10-architecture-compliance-registry.md`).

## 1. Bottom line

The umbrella's `subrepos.lock.json` is today the single deployment-pin
authority for the entire production system, and Codex has mechanically closed
the only channel that made that state auditable (recording pin bumps as
umbrella PRs). Consequence, live right now: **the deployed pin state has no
durable record anywhere** — 7 of 9 deployed pins differ from the last
committed lock ([VERIFIED] §2.2). This design moves pin authority into a
**deployment manifest owned, versioned, and PR-reviewed in
renquant-orchestrator**, keeps the umbrella as a pure consumer via a
generated, provenance-stamped mirror, preserves every `promote_pin.py`
guarantee (dry-run → apply → e2e-verify → auto-revert, promote-bak rollback,
M9 snapshot backstop), and lands in five verified stages with no big-bang.
Stage 1 alone — additive, zero consumer change — gives today's
deployed-but-unrecorded state its first durable record.

## 2. Why now

### 2.1 Codex blocked recording deployment state in the umbrella

Umbrella PR #460 (closed), Codex review verbatim:

> Do not merge. This is the deprecated umbrella, while the required
> architecture is multi-repo. More critically, a purported lock-only
> reconciliation carries a very large unrelated backtesting/data/artifact
> diff after the merge commit, so it is not auditable as a pin update. Close
> this PR. Move any still-required deployment pin consumer into the
> designated multi-repo deployment/run-manifest owner as a narrow, generated,
> independently verified change; the umbrella must not regain runtime
> artifact or deployment ownership.

Umbrella PR #461 (the clean two-file redo, also closed), verbatim:

> Closing: a clean two-file diff does not solve the ownership problem. This
> still makes the deprecated umbrella the daily deployment-pin authority.
> Move the active run-manifest/pin consumer to renquant-orchestrator (the
> pinned-subrepo orchestration owner) or a dedicated multi-repo deployment
> manifest, with the migration verified before any consumer switch. Do not
> record further current deployment state in the umbrella lock.

This design is the direct answer to that verdict: renquant-orchestrator is
the pinned-subrepo orchestration owner (its declared repo role, and the
lock's own role string for it: "pinned-subrepo daily orchestration + run
bundles"), so the deployment manifest lands here.

### 2.2 The unrecorded-state gap is live today [VERIFIED 2026-07-11]

Committed umbrella lock (origin/main) vs the deployed on-disk lock the 18
launchd jobs actually consume:

| repo | committed (umbrella main) | deployed (on disk) | drift |
|---|---|---|---|
| renquant-common | `df620a6ecc35` | `f5cb6ab2cf4e` | YES |
| renquant-strategy-104 | `0e5d989137b6` | `0e5d989137b6` | — |
| renquant-model | `775804dbb0bc` | `84a3c1864f19` | YES |
| renquant-pipeline | `2b0eb0257b88` | `289b919908fc` | YES |
| renquant-execution | `c41639840b2c` | `42e5d7d72251` | YES |
| renquant-backtesting | `8f6700ab3558` | `8f6700ab3558` | — |
| renquant-base-data | `0678958ec2f5` | `fef604bff2f2` | YES |
| renquant-artifacts | `c09d66f8dd09` | `c71edf7fa6e7` | YES |
| renquant-orchestrator | `e8fe46206025` | `d4d278631d30` | YES |

Every deployed bump was readonly-e2e-verified at apply time (the promote
flow's verify step), so the DEPLOYMENT is sound — but its RECORD is only an
uncommitted file on one machine plus `promote-bak` siblings. A disk failure,
an errant checkout (the 2026-06-25 near-miss class), or a stale-lock restore
would silently lose the production pin state. Recording it in the umbrella is
now review-blocked by design; recording it nowhere is unacceptable. The only
consistent resolution is a new authority outside the umbrella.

### 2.3 The target pattern is already proven (D6-§2a)

The shadow-AB experiment already runs on an orchestrator-owned run manifest
with exactly the semantics this design generalizes
(`src/renquant_orchestrator/shadow_ab_runner.py`, merged orchestrator #460 +
#464):

- `load_run_manifest` — schema-checked named-repo map `{name → {path,
  commit}}`, fail-closed on missing/malformed entries.
- `verify_run_manifest` — verify-before-consume: every repo checkout must
  exist, HEAD must match the manifest commit, working tree must be CLEAN;
  any failure aborts the session-pair with neither arm invoked.
- `artifact_store` binding (#464) — the manifest declares the pinned
  artifact store; schema-validated at load, directory-existence fail-closed
  at precheck, recorded in the sealed bundle, and threaded so precheck and
  consumption resolve through EXACTLY the same anchors.

R-PIN promotes this pattern from one experiment path to the deployment
authority itself. Schema conventions, verification discipline, and the
fail-closed posture are reused, not reinvented.

## 3. Fit with the architecture-compliance registry

- **T2 (umbrella is load-bearing, P0→P1)** — the lock and its 18-plist
  consumer web is T2's pin-plane core. R-PIN removes the authority half; R1
  (launchd cutover) removes the consumer half over time. Independent but
  mutually reinforcing: every R1 leg cut over to `renquant-orchestrator
  run-job` is one fewer umbrella lock consumer for R-PIN Stage 5.
- **T4 (registry/record ownership bypassed)** — the deployment record joins
  promotion records in moving out of the umbrella. Boundary kept clean:
  the **deployment manifest answers "what is deployed"** (this design);
  **renquant-artifacts answers "why it was promotable"** (promotion
  evidence, R7's dual-write). No overlap.
- **Revision of audit A §3 disposition, on the record:** the audit listed
  pins/assemble/promote-pin/rollback-baks as "correctly umbrella-owned …
  healthy", and the registry's §3 note excluded promote_pin/rollback history
  from migration. That assessment covered the MECHANICS (which are healthy
  and are preserved wholesale here) and pre-dates the Codex ownership
  verdict on #460/#461 (2026-07-11). This design revises the OWNERSHIP
  disposition only: the mechanics move house intact; nothing about them is
  rebuilt. This is recorded here explicitly so the registry and this design
  do not silently contradict each other.
- **Kernel-identity invariant (registry, Codex round 1): R-PIN is NOT a
  kernel cutover.** The migration changes where pins are READ from, never
  what they RESOLVE to. Per-stage acceptance (§8) requires the resolved pin
  set to be byte-identical across each flip. Any stage failing that check is
  an R2-class change and is out of scope by definition.
- **Shim governance:** every transitional mechanism introduced here (the
  `promote_pin.py` delegating shim, the generated mirror, the recording-SLA
  override) declares owner / expiry / telemetry / fail-closed retirement per
  the registry's temporary-migration-mechanism governance.
- **Sequencing:** after R0 (tripwires exist; the R0 twin-parity harness
  pattern is reused for the mirror-divergence tripwire); Stages 1–2 can run
  parallel with R1/R6; Stage 4 is the single umbrella-side PR; Stage 5
  completes alongside R1. R7's promote-record dual-write plugs into the
  Stage 3 CLI as a separate follow-on.

## 4. Consumer inventory (audit T2, verified 2026-07-11)

### 4.1 The 18 launchd jobs (`RenQuant/scripts/launchd/*.plist`)

All 18 invoke umbrella `scripts/*` ([VERIFIED] by plist ProgramArguments).
Lock consumption classified by grep over each invoked script (direct = opens
`subrepos.lock.json` itself; machinery = resolves pins via
`subrepo_paths.py` / `subrepo_pin_guard.py` / `subrepo_assemble.py` /
`preflight_pin_align.sh` / strict-paths env / pinned `.subrepo_runtime`):

| launchd job | invokes | lock consumption |
|---|---|---|
| daily104 | `daily_104.sh` | **DIRECT** + machinery |
| weekly-wf-promote | `weekly_wf_promote.sh` | **DIRECT** + machinery |
| conditional-retrain104 | `conditional_retrain_104.sh` | machinery |
| intraday104 | `intraday_sell_104.sh` | machinery |
| retrain-alpha158-linear | `retrain_alpha158_linear.sh` | machinery |
| screen-watchlist | `screen_watchlist.py` | machinery |
| weekly-apy104 | `weekly_apy_check.py` | machinery |
| weekly-retrain-patchtst | `weekly_retrain_patchtst.sh` | machinery |
| weekly-tournament-retrain | `weekly_tournament_retrain.sh` | machinery |
| retrain-panel104 | `retrain_panel.sh` | compat no-op → chains weekly-wf-promote |
| daily-analyst-ratings | `daily_analyst_ratings_refresh.sh` | none |
| daily-analyst-ratings-finnhub | `daily_analyst_ratings_finnhub_refresh.sh` | none |
| daily-iv-snapshot | `daily_iv_snapshot.sh` | none |
| daily-news-sentiment | `daily_news_sentiment_refresh.sh` | none |
| monthly-calibrator-refresh | `monthly_calibrator_refresh.sh` | none |
| monthly-meta-label-retrain | `monthly_meta_label_retrain.sh` | none |
| preopen-cancel-gate | `preopen_cancel_gate.sh` | none |
| weekly-fundamental-refresh | `weekly_fundamental_refresh.sh` | none |

Migration consequence: **only 2 of 18 jobs read the lock directly; 8 more
reach it through 3–4 choke-point modules.** Flipping the choke points
(`subrepo_paths.py`, `subrepo_pin_guard.py`, `subrepo_assemble.py`) plus the
2 direct shell readers converts the whole scheduled plane at once — Stage 4
is one umbrella PR, not eighteen.

### 4.2 Umbrella direct lock readers (19 files, [VERIFIED] grep)

Choke points (mutation/resolution/verification/materialization):
`promote_pin.py`, `subrepo_paths.py`, `subrepo_pin_guard.py`,
`subrepo_assemble.py`. Direct shell readers: `daily_104.sh`,
`preflight_pin_align.sh`, `weekly_wf_promote.sh`. Reporting/doctor/contract
readers: `system_doctor.py`, `subrepo_doctor.py`,
`check_lock_pins_ci_green.py` (pin-advance CI gate),
`render_strategy_104_snapshot.py` (M9), `daily_multirepo.py`,
`live_multirepo.py`, `refresh_subrepo_lock.py`, `sync_subrepo_docs.py`,
`orchestrator_bridge_bootstrap.py`, `subrepo_daily_contract.py`,
`subrepo_ops_contract.py`, `check_ops_deployment_ready.py`.

### 4.3 renquant-orchestrator readers of the umbrella lock

`repos.py:33` (`DEFAULT_MANIFEST` hardcodes the umbrella lock path),
`live_bridge.py:224,248`, `runtime_paths.py:262`,
`shadow_ab_runner.py:1096` (`resolve_experiment_pins`), `cli.py` repos
command, `retention_policy.py` (promote-bak retention — keeps working
unchanged). These flip to the manifest in Stage 2 (dual-read) — they are
already orchestrator-owned code, so no umbrella PR is needed for them.

## 5. Target architecture

### 5.1 The deployment manifest (single pin authority)

A JSON document **committed in renquant-orchestrator** at
`deploy/deployment-manifest.json` — versioned, PR-reviewed, protected by the
same mechanical CODEOWNERS/Codex gate as all orchestrator changes. Schema v1
extends the proven run-manifest conventions (§2.3):

```json
{
  "schema_version": 1,
  "kind": "deployment-manifest",
  "generated_at": "<iso8601>",
  "repos": {
    "<name>": {
      "remote": "…", "branch": "main", "commit": "<sha>",
      "local_path": "…", "role": "…", "test_command": "…", "status": "…"
    }
  },
  "artifact_store": { "repo": "renquant-artifacts", "path": "…" },
  "deployment": {
    "deployed_at": "<iso8601>", "deployed_by": "<agent|operator>",
    "verify": { "cmd": "…", "exit": 0, "evidence_ref": "<run-bundle/log ref>" },
    "state": "deployed",
    "supersedes_sha256": "<sha256 of prior manifest content>"
  }
}
```

- `repos` is a strict superset of today's lock entries → the generated
  mirror (§5.3) can be produced losslessly.
- `artifact_store` reuses the #464 binding so the deployment plane and the
  D6-§2a experiment plane express artifact anchoring identically.
- `deployment.verify` makes the e2e-verify evidence part of the record —
  what #460/#461 could never carry.
- `supersedes_sha256` chains records so history is tamper-evident beyond
  git itself.

**Self-pin semantics (no chicken-and-egg):** the manifest DOCUMENT's
authority is renquant-orchestrator `origin/main` (branch-protected,
Codex-gated). The `repos["renquant-orchestrator"].commit` ENTRY pins which
orchestrator commit the RUNTIME executes — a value inside the document, not
the document's own location. The two are independent, exactly as the lock
already pins an orchestrator commit while the lock lives elsewhere.

### 5.2 Machine deployed-state copy

The live machine keeps its operational copy at
`RenQuant/.subrepo_runtime/deployment-manifest.json` (the existing
gitignored runtime-state anchor — consistent with the audit A14 convention
that machine state stays umbrella-ANCHORED even when umbrella-DISOWNED; no
new state root). Single sanctioned writer: the Stage 3 promote CLI. This
copy answers "what IS deployed on this host right now"; the orchestrator
`main` document is its durable, reviewed record (recording discipline §7).

### 5.3 The umbrella lock becomes a generated mirror

During transition, `RenQuant/subrepos.lock.json` **on disk** is regenerated
from the manifest by the promote CLI — byte-compatible with today's schema
plus two additive provenance fields:

```json
  "generated_from": "renquant-orchestrator deployment manifest (R-PIN)",
  "manifest_sha256": "<sha256 of the source manifest content>"
```

Legacy readers parse it unchanged (they access known keys from `json.loads`;
additive keys are invisible to them). This means Stages 1–3 require **zero
changes to any of the 19 umbrella readers or 18 launchd jobs** — the mirror
is exactly the file they already read, now with a verifiable pedigree. Note
this matches current operational reality: the on-disk lock already diverges
from the committed lock and production runs from disk; the mirror only makes
the on-disk file machine-written and provenance-stamped instead of
hand-reconciled. Per the Codex directive, the mirror is **never committed**
to the umbrella; the committed lock is frozen and then tombstoned (Stage 4).

## 6. Promote flow: guarantee-preservation map

New orchestrator CLI (working name `renquant-orchestrator deploy-pin`,
implemented as `deploy_pin.py`) replicating `promote_pin.py`
guarantee-for-guarantee ([VERIFIED] against `promote_pin.py` 241L):

| promote_pin.py guarantee | deploy-pin equivalent |
|---|---|
| DRY-RUN by default; nothing written without `--apply` | identical (`bump`/`revert` subcommands, dry-run default) |
| timestamped pre-change backup (`subrepos.lock.json.promote-bak.<ts>`) | backup PAIR: manifest + mirror, same timestamp; lock-side baks keep the same name/glob so `retention_policy.py:96` prunes them unchanged; manifest-side baks added to the retention policy |
| atomic write (temp + parse-validate + `os.replace`) | identical, applied to manifest first, then mirror |
| materialize via `subrepo_assemble.py --sync` | identical (assemble reads the regenerated mirror — no assemble change needed before Stage 4) |
| verify command; default = `check_conviction_admits.py --min-admits 1` (still-buys guard) | identical default; `--verify-cmd` passthrough |
| AUTO-REVERT on sync or verify failure (restore backup + re-sync) | identical, restoring BOTH files (manifest first, then regenerate mirror, then re-sync) — a crash mid-revert leaves manifest↔mirror hash divergence, which every consumer entrypoint fails closed on (§8), so a torn state can never be silently consumed |
| always prints the one-command manual revert | identical |
| `revert` subcommand: restore latest backup + re-sync | identical (restores the backup pair) |
| M9/A6 snapshot freshness backstop: after success, regenerate `doc/arch/strategy-104-snapshot.md` to scratch, diff vs committed, non-zero exit if stale; never auto-commits; never reverts a pin for a stale doc alone | invoked UNCHANGED — `check_snapshot_freshness` continues to run against the umbrella tree (also imported by `manual_promote.sh:96` and `weekly_wf_promote.sh:390`, which keep working) |
| pin-advance CI gate (`check_lock_pins_ci_green.py`: no advance to a commit with red/missing checks) | invoked at `bump` time against the CANDIDATE commit before writing anything; gate ports to orchestrator CI in Stage 4 |

`promote_pin.py` itself becomes a **delegating shim** in Stage 3 (prints a
deprecation line, execs `deploy-pin` with mapped args) so every existing
call site and operator habit keeps working. Shim governance: owner =
operator; expiry = Stage 5 completion (mechanical: the Stage 5 grep-zero
tripwire); telemetry = shim-use log line + counter in the daily run bundle;
past expiry the shim FAILS CLOSED (refuses, points to `deploy-pin`).

## 7. Recording discipline (deploy ↔ durable record)

Two models were considered:

- **(a) Record-first (merge-before-apply):** the pin-bump PR merges to
  orchestrator main BEFORE the machine applies. Cleanest ownership story,
  but it puts Codex review latency synchronously into the production deploy
  path — unacceptable for market-hours incident bumps (the 06-26/07-01
  incident classes needed same-hour pin fixes), and auto-revert would leave
  main asserting a state that deploy verification just rejected, requiring
  a symmetric revert PR anyway. Rejected as the default.
- **(b) Apply-then-record, bounded and fail-closed (CHOSEN):** `deploy-pin
  --apply` completes the full §6 flow on the machine, then AUTOMATICALLY
  opens the recording PR to renquant-orchestrator (generated diff: new
  manifest content incl. `deployment.verify` evidence). The gap between
  deployed state and merged record is permitted only within a bounded
  window, and is alarmed the whole time.

Enforcement for (b) — this is the part that makes the gap non-silent:

1. **Recording-SLA tripwire** (daily preflight + `make doctor`): compare the
   machine manifest against orchestrator `origin/main`'s. Divergence is
   REPORTED from the first second; if it persists past 1 trading session,
   or if a second unrecorded promote would stack on an unmerged first, the
   tripwire **blocks further promotes** (deploy-pin refuses `--apply`) and
   alerts the operator. Trading itself is not halted for a recording lag —
   the deployed state was e2e-verified at apply time, and halting the book
   over paperwork would violate the production-protection rule; the block
   applies to new MUTATIONS of pin state.
2. **Codex rejection of a recording PR** = a post-hoc audit failure:
   promotes stay blocked until the operator either reverts the deployed pin
   (`deploy-pin revert --apply`, then the recording PR records the revert)
   or resolves the objection. The record and the deployment must reconverge
   in one direction or the other; the tripwire holds until they do.

This is strictly stronger than the status quo (unbounded, unrecordable gap)
and strictly weaker in latency cost than (a). Codex reviewers: this is the
single most review-worthy decision in the design.

## 8. The transition invariant

> **Single-authority, fail-closed divergence.** At every instant of every
> stage, exactly ONE document is defined as the pin authority. Every other
> pin document in existence (the generated umbrella-lock mirror, the
> machine deployed-state copy, any backup) is a derived artifact carrying
> the authority content's sha256. Every consumer entrypoint re-verifies
> derived-vs-authority hashes and materialized-checkout HEADs before use
> and FAILS CLOSED on any mismatch — abort with a named error, alert,
> never fall back to a stale or alternative pin source. The deployed-state
> vs durable-record gap (§7) is bounded to one trading session and is
> alarmed from the first second; it can never be silent.

Authority by stage: Stages 1–2, the on-disk umbrella lock remains authority
(manifest is a verified shadow); Stage 3 onward, the manifest is authority
(lock is the generated mirror). The flip is a single, named, verified
cutover event inside Stage 3 (§9), not an emergent condition.

Divergence handling matrix (all fail-closed once armed):

| divergence | detector | consequence |
|---|---|---|
| mirror content ≠ manifest (hash) | every choke-point read; daily preflight | abort consumer, alert; only `deploy-pin` re-apply/revert may rewrite the mirror |
| materialized `.subrepo_runtime` clone HEAD ≠ manifest commit | `subrepo_pin_guard` (existing, re-pointed) | existing strict-pin behavior, unchanged semantics |
| machine manifest ≠ orchestrator main manifest | recording-SLA tripwire (§7) | report → block further promotes past SLA |
| committed umbrella lock ≠ anything | none needed after Stage 4 tombstone | committed lock carries no pin data; any residual parser fails loudly on the tombstone schema |

## 9. Staged rollout (each stage individually shippable and revertible)

**Stage 1 — schema + capture + FIRST DURABLE RECORD (S; orchestrator-only;
zero consumer change).**
Deliverables: manifest schema + loader/verifier (reusing the §2.3
`shadow_ab_runner` conventions, lifted into a shared module both paths
import — not a third hand-copy; the fingerprint-triple lesson);
`deploy-pin capture` command that reads the DEPLOYED truth — the on-disk
lock AND the actual `.subrepo_runtime` clone HEADs, failing on any
disagreement between them — and emits the manifest; the first manifest
committed via orchestrator PR, **recording today's §2.2 deployed state
durably for the first time**, with `deployment.verify.evidence_ref`
pointing at the 07-10/11 readonly-e2e verification evidence.
Gate: capture output matches on-disk lock AND clone HEADs exactly
(read-only re-verification in PR evidence); `make test` green.
Rollback: delete a file no one consumes yet. Risk: none (additive).
**This stage alone closes the current unrecorded-state gap** — from then
on, "what is deployed" has a reviewed, versioned answer even while all
consumers still read the lock.

**Stage 2 — dual-read shadow verification (S/M; orchestrator-only).**
Orchestrator's own readers (§4.3: `repos.py`, `live_bridge.py`,
`runtime_paths.py`, `shadow_ab_runner.resolve_experiment_pins`) gain
manifest-aware dual-read: resolve from the lock (still authority), ALSO
resolve from the manifest, compare, and emit a divergence counter into the
run bundle (shadow mode: report-only).
Gate: **N=5 consecutive green sessions with zero divergence events**, then
flip these readers to fail-closed on divergence. Rollback: flag off
dual-read. Risk: low (read-only comparison on orchestrator code paths).

**Stage 3 — promote-flow cutover; authority flips (M; orchestrator CLI +
umbrella shim).**
Deliverables: full `deploy-pin` per §6; `promote_pin.py` delegating shim;
mirror generation + provenance fields; recording-PR automation + SLA
tripwire (§7). The **cutover event**: first `deploy-pin bump --apply` on a
real pin, after which the manifest is authority and the lock is mirror.
Pre-arming gates (all mechanical, evidenced in the Stage 3 PR):
(i) **parity harness** — for the current state and for a candidate bump,
`promote_pin.py` dry-run and `deploy-pin` dry-run must plan byte-identical
lock content (behavior invariance / kernel-identity: same resolved pins);
(ii) **auto-revert drill** — forced verify-failure on a scratch copy of the
lock+manifest pair must restore both and re-sync;
(iii) **backup-pair restore drill** — `deploy-pin revert` from the bak pair;
(iv) M9 snapshot backstop demonstrably invoked (scratch render) in both
bump and revert paths.
Post-cutover gate: first real bump e2e-verified green + its recording PR
merged within SLA. Rollback: the shim delegation is removable; the lock
mirror IS a valid legacy lock — reverting to promote_pin.py-native operation
is a one-line shim disable with zero consumer impact.

**Stage 4 — umbrella becomes a pure consumer (M; ONE umbrella PR).**
Deliverables in a single reviewable umbrella change, per Codex's "narrow,
generated, independently verified" instruction:
(i) the 3 choke-point modules + 3 direct shell readers (§4.2) resolve pins
manifest-first (env `RENQUANT_DEPLOYMENT_MANIFEST` → machine manifest path,
default on) and verify mirror↔manifest hash at entry (fail-closed);
(ii) the committed `subrepos.lock.json` is replaced by a TOMBSTONE (schema
`{"schema_version": 2, "kind": "tombstone", "authority": "renquant-orchestrator:deploy/deployment-manifest.json"}`
— old parsers fail loudly on the missing `subrepos` key rather than reading
stale pins; `.gitignore` gains the generated on-disk mirror);
(iii) `check_lock_pins_ci_green.py` retires umbrella-side (its port having
landed in orchestrator CI in Stage 3);
(iv) doctor/contract/reporting readers re-pointed through `subrepo_paths`.
Gate: one full green `daily_104` session + one green `weekly_wf_promote`
run on read-through resolution, resolved pin set byte-identical to
pre-flip (kernel-identity check). Rollback: revert the umbrella PR; the
mirror file still on disk is a valid lock for the old readers.
Note: this umbrella PR REMOVES umbrella authority — squarely aligned with
the #461 verdict — and is the only umbrella-side change in the whole plan.

**Stage 5 — consumer completion + shim retirement (S, rolling; interacts
with R1).**
Deliverables: remaining reporting readers flipped; R0-style tripwire test
pinned in the umbrella (grep-zero: no file outside `subrepo_paths.py`
opens a pin source directly — the same mechanical-done-gate pattern as the
twin-parity manifest); `promote_pin.py` shim expiry enforced (fail-closed
per §6 governance); orchestrator `repos.py:33` default flipped from the
umbrella path to the manifest, removing the last hardcode. R1's launchd
cutovers independently shrink the umbrella-script consumer set; R-PIN is
DONE when the tripwire holds and the shim is retired — a mechanical
condition, not a declaration.

No stage flips more than one thing; every gate is mechanical; every stage
has a stated rollback that does not require the previous stage to be undone.

## 10. Failure modes considered

- **Torn write during apply/revert** → §6: manifest-first ordering + hash
  verification at every consumer entry; a torn pair is unreadable, not
  misreadable.
- **Stale-machine restore (backup restores an old lock)** → the mirror's
  `manifest_sha256` no longer matches the machine manifest → fail-closed at
  first consumer touch; recovery is `deploy-pin` re-apply from the manifest.
- **Two writers (someone hand-edits the lock)** → same hash mismatch; the
  design removes the hand-edit affordance the 2026-06-23 postmortem already
  condemned, now mechanically.
- **Orchestrator repo unavailable at read time** → runtime consumers never
  need the network: they read the MACHINE manifest + mirror; only recording
  (§7) and `capture`/`bump` provenance need the remote, and they fail
  closed without touching deployed state.
- **The orchestrator checkout consulted for the manifest sits on a feature
  branch** (today: the working checkout is on `pr-148`) → recording and
  authority comparisons run against `origin/main` refs, never a local
  branch; the machine manifest is written only by `deploy-pin`, not read
  from any dev checkout.

## 11. Non-goals

- **No implementation or migration execution in this PR** — design only.
- **No pin VALUE changes** — the migration never alters what is deployed;
  every stage is behavior-invariant on resolved pins (§3 kernel-identity).
- **No launchd cutover** (R1), **no kernel cutover** (R2), **no broker/
  training migration** (R3/R4) — R-PIN only moves the pin plane's authority.
- **No crypto (GOAL-2) or model-scope coupling** — the manifest schema adds
  no crypto- or model-specific fields; sleeves ride the same repo pins.
- **No promotion-evidence store** — that is R7 (renquant-artifacts);
  `deployment.verify.evidence_ref` REFERENCES evidence, it does not house it.
- **No new state roots on the machine** — runtime state stays
  umbrella-anchored per the existing convention (§5.2).
- **The umbrella repo is not deleted or emptied** (LONG ledger #9); it
  remains the machine anchor and rollback source, minus pin authority.

## 12. Open questions for review

1. §7's apply-then-record with a 1-trading-session SLA vs record-first: is
   the bounded window acceptable to Codex as the default, given the
   incident-latency argument? (The SLA constant is a config, not a design
   commitment.)
2. Stage 4 tombstone vs keeping a frozen legacy lock with a warning field:
   tombstone chosen because a frozen-but-parseable lock IS the silent-stale
   hazard this design exists to kill. Confirm.
3. Should the Stage 3 recording PR auto-merge on Codex approval (it is a
   generated, evidence-carrying diff) or always wait for operator eyes?
   Proposed: normal mutual-review flow, no special-casing.
