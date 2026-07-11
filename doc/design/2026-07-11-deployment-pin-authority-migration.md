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
  parallel with R1/R6; Stage 3 carries the single narrow umbrella-side
  verification PR, Stage 5 the tombstone; Stage 5
  completes alongside R1. R7's promote-record dual-write plugs into the
  Stage 3/4 CLI as a separate follow-on.

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
2 direct shell readers converts the whole scheduled plane at once — Stage 3
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
  "generation": 41,
  "generated_at": "<iso8601>",
  "repos": {
    "<name>": {
      "remote": "…", "branch": "main", "commit": "<sha>",
      "role": "…", "status": "…"
    }
  },
  "artifact_store": { "repo": "renquant-artifacts", "path": "…" },
  "deployment": {
    "deployed_at": "<iso8601>", "deployed_by": "<agent|operator>",
    "verify": {
      "profile": "readonly-e2e",
      "args": { "min_admits": 1 },
      "exit": 0,
      "evidence_ref": "store://<content-addressed artifact record>"
    },
    "state": "deployed",
    "supersedes_sha256": "<sha256 of prior manifest content>"
  }
}
```

- **PORTABLE — no host paths** (Codex r1 point 5): `repos` entries carry
  repo IDENTITY only (remote + branch + commit + metadata). Where a checkout
  lives on a given host is resolved through that host's **runtime
  inventory** (§5.2), which is verified at read time (inventory path's HEAD
  must equal the manifest commit) and never committed. The identity fields
  are a strict superset of the lock's identity fields → the generated
  mirror (§5.3) is produced losslessly as
  `f(manifest identity, host inventory paths)`.
- **`generation` is a monotonic epoch** (Codex r1 point 3): strictly
  increasing on EVERY manifest mutation — including reverts (a revert is a
  NEW generation asserting prior pin values, never a reuse of an old
  generation). Content hashes make records tamper-evident; the generation
  makes them **replay-evident**: restoring an internally-consistent old
  manifest+mirror backup pair yields matching hashes but a stale
  generation, which every consumer detects against the host's durable
  expected-generation record (§5.2).
- `artifact_store` reuses the #464 binding so the deployment plane and the
  D6-§2a experiment plane express artifact anchoring identically.
- **No free-form shell in the authority document** (Codex r2 point 3):
  `deployment.verify.profile` names an entry in a code-owned ALLOWLIST of
  verification profiles (defined and reviewed in renquant-orchestrator;
  args are structured data validated per profile) — a reviewed manifest
  can never smuggle deployment-side code execution. The lock's legacy
  `test_command` strings likewise do NOT enter the authority document;
  the mirror composes them from a versioned compatibility table in
  orchestrator code (§5.3).
- `deployment.verify.evidence_ref` is a **pinned content-addressed
  artifact record** (`store://` in renquant-artifacts, the #13/#14
  mechanism — full sha256 in its STORE-MANIFEST), never a local log path
  (Codex r2 point 4): the evidence outlives the host.
- `supersedes_sha256` chains records so history is tamper-evident beyond
  git itself.

**Self-pin semantics (no chicken-and-egg):** the manifest DOCUMENT's
authority is renquant-orchestrator `origin/main` (branch-protected,
Codex-gated). The `repos["renquant-orchestrator"].commit` ENTRY pins which
orchestrator commit the RUNTIME executes — a value inside the document, not
the document's own location. The two are independent, exactly as the lock
already pins an orchestrator commit while the lock lives elsewhere.

### 5.2 Machine deployed-state root (neutral, NOT umbrella-anchored)

Per the #461 verdict, the target state cannot be umbrella-anchored (Codex
r1 point 4 — this supersedes the audit A14 "machine state stays
umbrella-anchored" convention **for the pin plane specifically**; A14's
rationale was continuity, not ownership). The host's deployed-state root is
**`~/.renquant/deploy/`** (overridable via `RENQUANT_DEPLOY_STATE_ROOT`;
neutral, host-scoped, gitignored by construction — it is not inside any
repo). It holds:

- `deployment-manifest.json` — the machine's operational copy ("what IS
  deployed on this host right now"); single sanctioned writer = the
  promote CLI. The orchestrator `main` document is its durable, reviewed
  record (§7).
- `runtime-inventory.json` — the per-host repo-name → checkout-path map
  (the paths removed from the durable schema, §5.1). Written by
  `deploy-pin capture`/`apply`; every consumer read verifies the inventory
  path's HEAD against the manifest commit before use.
- `expected-generation.json` — the durable epoch record `{generation,
  manifest_sha256}`, **forward-only**: written atomically (temp +
  `os.replace`) immediately AFTER a successful apply; the writer refuses
  any decrease. Consumers require machine-manifest generation == expected
  generation (less ⇒ stale/replayed pair; greater ⇒ torn apply) — both
  abort with a named error; recovery is the explicit
  `deploy-pin reconcile-generation` flow, which re-verifies the machine
  manifest against orchestrator `origin/main` before moving the record.

  **The epoch's durable anchor is REMOTE, not this file** (Codex r2
  point 1 — a full host-root backup restore rolls manifest, mirror,
  expected-generation, and receipts back TOGETHER, so a local record
  alone cannot witness its own rollback): the recorded manifest on
  orchestrator `origin/main` carries the generation, and that
  branch-protected remote ref is the independent ledger. Enforcement:
  every MUTATION (`apply`, `reconcile-generation`) evaluates the anchored
  TRANSITION PREDICATE for its mutation kind (§7.1 — a record-first apply
  legitimately sees origin/main one generation AHEAD of the machine, so
  the rule is predecessor-exactness, not literal equality) and FAILS
  CLOSED when the anchor is unreachable or the predicate does not hold;
  the daily preflight/doctor evaluates the STEADY-STATE predicate
  (machine == origin/main recorded manifest, same generation) and alarms
  on divergence or anchor-unreachability. Pure
  READ paths remain offline-capable against the local record — with the
  threat model stated honestly: a full host-root rollback in the window
  between network checks, with every alarm ignored, is detected at the
  next anchor comparison (≤ 1 trading session), not instantaneously;
  instantaneous offline rollback-detection would require remote round
  trips on the hot read path and is explicitly out of scope. Local
  content addressing is integrity, not immutability — immutability
  comes from the remote ledger.
- `receipts/` — emergency-lane receipts, written locally BEFORE mutation
  and durably anchored by inclusion (content + sha) in the mandatory
  reconciliation PR (§7) — the git remote is the immutable home; the
  local copy is operational convenience, same threat model as above.

Transitional note: the on-disk umbrella lock remains — as the generated
**mirror for legacy readers only** (§5.3) — until the Stage 5 tombstone;
that is a compatibility artifact under the umbrella path, not machine
state ownership. The bounded migration OFF the umbrella for state is
Stage 1 (the neutral root exists from the first `capture`), not a distant
promise.

### 5.3 The umbrella lock becomes a generated mirror — first mirror write
IS the authority flip

**No mirror is generated before the Stage 4 flip** (Codex r2 point 2: a
generated lock is a derivative; writing one while the lock is still called
authority would create ambiguous dual authority). Read/write semantics,
exactly: pre-flip, the on-disk lock is the authority and the ONLY writer is
the legacy promote path; the Stage-3-armed verification at choke points is
**conditional** — a lock WITHOUT provenance fields is the pre-flip
authority and passes through; a lock WITH provenance fields MUST verify
against the machine manifest (hash + generation) or the consumer aborts.
The first provenance-stamped write, performed by `deploy-pin apply` at the
Stage 4 cutover, is therefore BY CONSTRUCTION the moment authority flips —
there is no instant at which a generated mirror exists while the lock is
authority, and no instant at which a stamped mirror goes unverified.
Fault-injection for the conditional semantics runs against SYNTHETIC
mirrors in scratch copies during Stage 3 (never a production write).

From the flip onward, `RenQuant/subrepos.lock.json` **on disk** is
regenerated from the manifest by the promote CLI — byte-compatible with
today's schema plus two additive provenance fields:

```json
  "generated_from": "renquant-orchestrator deployment manifest (R-PIN)",
  "manifest_sha256": "<sha256 of the source manifest content>"
```

Legacy readers parse it unchanged (they access known keys from `json.loads`;
additive keys are invisible to them). Stages 1–2 require **zero changes to
any of the 19 umbrella readers or 18 launchd jobs**; Stage 3 changes ONLY
the choke points + direct shell readers — and does so to install
verification BEFORE the authority flip (§8/§9), while they still read the
authority lock. For everyone else the mirror is exactly the file they
already read, now with a verifiable pedigree. Legacy-only lock fields the
portable authority no longer carries (`local_path`, `test_command`) are
composed into the mirror from the host runtime inventory (§5.2) plus a
versioned compatibility table in orchestrator code — reviewed code, not
authority-document strings. Note
this matches current operational reality: the on-disk lock already diverges
from the committed lock and production runs from disk; the mirror only makes
the on-disk file machine-written and provenance-stamped instead of
hand-reconciled. Per the Codex directive, the mirror is **never committed**
to the umbrella; the committed lock is frozen and then tombstoned (Stage 5).

## 6. Promote flow: guarantee-preservation map

New orchestrator CLI (working name `renquant-orchestrator deploy-pin`,
implemented as `deploy_pin.py`) replicating `promote_pin.py`
guarantee-for-guarantee ([VERIFIED] against `promote_pin.py` 241L):

| promote_pin.py guarantee | deploy-pin equivalent |
|---|---|
| DRY-RUN by default; nothing written without `--apply` | identical (`bump`/`revert` subcommands, dry-run default) |
| timestamped pre-change backup (`subrepos.lock.json.promote-bak.<ts>`) | backup PAIR: manifest + mirror, same timestamp; lock-side baks keep the same name/glob so `retention_policy.py:96` prunes them unchanged; manifest-side baks added to the retention policy |
| atomic write (temp + parse-validate + `os.replace`) | identical, applied to manifest first, then mirror |
| materialize via `subrepo_assemble.py --sync` | identical (assemble reads the regenerated mirror — no assemble change needed before Stage 5's tombstone; its choke-point verification arms in Stage 3) |
| verify command; default = `check_conviction_admits.py --min-admits 1` (still-buys guard) | identical default; `--verify-cmd` passthrough |
| AUTO-REVERT on sync or verify failure (restore backup + re-sync) | identical, restoring BOTH files (manifest first, then regenerate mirror, then re-sync) and ADVANCING the generation (a revert is a new epoch asserting prior pins — never a replay of an old one, §5.1/§5.2) — a crash mid-revert leaves manifest↔mirror hash divergence, which every consumer entrypoint fails closed on (§8), so a torn state can never be silently consumed |
| always prints the one-command manual revert | identical |
| `revert` subcommand: restore latest backup + re-sync | identical (restores the backup pair) |
| M9/A6 snapshot freshness backstop: after success, regenerate `doc/arch/strategy-104-snapshot.md` to scratch, diff vs committed, non-zero exit if stale; never auto-commits; never reverts a pin for a stale doc alone | invoked UNCHANGED — `check_snapshot_freshness` continues to run against the umbrella tree (also imported by `manual_promote.sh:96` and `weekly_wf_promote.sh:390`, which keep working) |
| pin-advance CI gate (`check_lock_pins_ci_green.py`: no advance to a commit with red/missing checks) | invoked at `bump` time against the CANDIDATE commit before writing anything; gate ports to orchestrator CI in Stage 4 (at the flip) |

`promote_pin.py` itself becomes a **delegating shim** in Stage 4 (prints a
deprecation line, execs `deploy-pin` with mapped args) so every existing
call site and operator habit keeps working. Shim governance: owner =
operator; expiry = Stage 5 completion (mechanical: the Stage 5 grep-zero
tripwire); telemetry = shim-use log line + counter in the daily run bundle;
past expiry the shim FAILS CLOSED (refuses, points to `deploy-pin`).

## 7. Recording discipline (deploy ↔ durable record)

**Default: RECORD-FIRST (merge-before-apply).** r1 proposed
apply-then-record as the default; Codex correctly rejected it — a machine
copy that can differ from `main` for a trading session IS the effective
authority, unreviewed. The normal pin-change flow is therefore:

1. `deploy-pin plan` produces the CANDIDATE manifest (generation N+1) plus
   machine-generated evidence: dry-run parity output, the candidate
   commit's CI-green check (§6), and the diff vs the current manifest. It
   opens the pin-bump PR to renquant-orchestrator.
2. Normal mutual review; merge to `main`. **Nothing has touched the
   machine yet.**
3. `deploy-pin apply` executes ONLY a manifest whose content hash equals
   orchestrator `origin/main`'s current manifest (fetched ref, never a
   local branch) — full §6 flow: backup pair, atomic writes, assemble,
   e2e verify, M9 backstop.
4. On verify FAILURE, auto-revert restores the prior deployed state
   (generation N+2 — reverts advance the epoch, §5.1) and auto-opens the
   revert-recording PR; further `apply` is blocked until `main` and the
   machine reconverge (the tripwire below). `main` briefly asserting a
   state the machine rejected is visible, alarmed, and one-directional —
   never silent.

**Emergency lane (separately privileged, signed, expiring).** Market-hours
incidents (the 06-26/07-01 same-hour pin-fix classes) cannot wait on review
latency. `deploy-pin apply --emergency` is a DISTINCT privilege, not a
faster default:

- requires a **signed authorization artifact** — the #465 pattern reused
  verbatim, not a third invention: token JSON (named incident, operator,
  reason, expiry ≤ 24h, scope = the exact target repo/commit pairs) +
  detached `ssh-keygen -Y` signature verified against the committed
  allowed_signers; the signing key is operator-held and unavailable to any
  agent. **Arming prerequisite (Codex r2 point 4): the emergency lane is
  DISABLED until the operator's REAL public key is committed** — the lane's
  verifier hard-rejects any allowed_signers entry carrying the PLACEHOLDER/
  fixture label (and the #465 test-fixture principal names), with a
  dedicated rejection test; fixture keys exist for tests only and can never
  authorize a production apply;
- stages a **local integrity record** (append-only under
  `~/.renquant/deploy/receipts/`, content-addressed) BEFORE mutating
  anything — immutable only once anchored by inclusion in the mandatory
  reconciliation PR (the git remote is the durable home; the local file
  shares the §5.2 host threat model);
- auto-opens the **reconciliation PR** immediately after apply (manifest
  content + token + receipt + verify evidence);
- reconciliation SLA = 1 trading session; past it, or if a second
  emergency apply would stack on an unreconciled first, `deploy-pin`
  refuses ALL further applies (normal and emergency) until reconverged.
  Trading itself is not halted for a reconciliation lag — the deployed
  state was e2e-verified at apply time; the block applies to new
  MUTATIONS of pin state.
- **Codex rejection of a reconciliation PR** = a standing audit failure:
  applies stay blocked until the operator reverts the deployed pin
  (`deploy-pin revert --apply` + revert-recording PR) or resolves the
  objection. Record and deployment must reconverge in one direction; the
  tripwire holds until they do.

The **recording-SLA tripwire** (daily preflight + `make doctor`) compares
machine manifest ↔ orchestrator `origin/main` manifest ↔ expected
generation on every run, reporting divergence from the first second
regardless of which lane produced it.

## 7.1 Epoch transition contract (the formal state machine)

State: `local = (manifest_local, sha_local, gen_local)` — the machine copy +
its content hash + generation, with `expected-generation.json` holding
`(gen_local, sha_local)`; `main = (manifest_main, sha_main, gen_main)` — the
recorded manifest at orchestrator `origin/main` (fetched ref). Every
mutation evaluates its predicate ATOMICALLY against a single fetched
snapshot of `main`; predicate failure = fail closed, no partial writes.

| mutation | permitted iff (ALL of) | writes | remote evidence required |
|---|---|---|---|
| **normal apply** (record-first) | anchor reachable; `gen_main == gen_local + 1`; `manifest_main.supersedes_sha256 == sha_local`; candidate executed = `manifest_main` byte-exact | machine manifest := `manifest_main`; expected-generation := `(gen_main, sha_main)` after successful verify | the merged pin-bump PR IS the evidence (already on main) |
| **emergency apply** (token lane) | anchor reachable; valid signed token whose scope covers the exact repo/commit deltas; candidate built locally with `generation == gen_local + 1` and `supersedes_sha256 == sha_local` | same as normal apply, from the local candidate; local integrity record staged FIRST | reconciliation PR (candidate + token + receipt + verify evidence) opened immediately; SLA per §7 |
| **failed-verify revert** (auto) | triggered only by a failed verify inside an apply; revert candidate has `generation == gen_current + 1`, `supersedes_sha256 == sha_current`, pin values = pre-apply state | machine manifest := revert candidate; expected-generation advances | auto-opened revert-recording PR; applies blocked until merged |
| **reconcile-generation** (manual recovery) | anchor reachable; machine manifest content hash equals SOME manifest recorded in origin/main history; operator invocation | expected-generation := that record's `(gen, sha)` — forward-only relative to the current record | the matching origin/main commit is cited in the command output and the next doctor report |

Rejected by construction: generation skips (`gen_main > gen_local + 1` —
someone recorded past this machine: applies halt until reconciled);
rollback to any `gen ≤ gen_local`; a candidate whose declared
`supersedes_sha256` differs from the machine's actual `sha_local` (the
machine is not the state the reviewer approved a transition FROM); any
mutation with the anchor unreachable. READ paths never mutate and use the
steady-state predicate (§5.2) for alarming only.

## 8. The transition invariant

> **Single-authority, fail-closed divergence.** At every instant of every
> stage, exactly ONE document is defined as the pin authority, and **no
> consumer reads a DERIVED pin document without verifying it against that
> authority** — hash AND generation AND materialized-checkout HEADs — and
> FAILS CLOSED on any mismatch: abort with a named error, alert, never
> fall back to a stale or alternative pin source. A consumer that cannot
> yet verify is only ever permitted to read the AUTHORITY itself, never a
> derivative. The deployed-state vs durable-record divergence (§7) exists
> only in the two bounded, alarmed cases (failed-verify revert;
> emergency lane) and is never silent.

**Authority and verification, by stage — the honest matrix (Codex r1
point 2: the invariant must hold BEFORE the flip, or the stage must say
"shadow only"):**

| stage | authority | legacy umbrella readers | orchestrator readers | manifest/mirror status |
|---|---|---|---|---|
| 1 | on-disk lock | read authority directly (no derivative exists) | read authority directly | manifest = **unverified shadow record**, consumed by nothing |
| 2 | on-disk lock | read authority directly | dual-read: lock (authoritative) + manifest (compared, report-only → fail-closed after N=5) | manifest = verified shadow for orchestrator paths only |
| 3 | on-disk lock | **choke-point verification INSTALLED AND ARMED, conditional** (§5.3: unstamped lock = authority, pass through; stamped lock MUST verify) — no production mirror exists yet; fault-injection on synthetic mirrors | fail-closed dual-read | NO mirror; CLI in parity/drill mode |
| 4 | **manifest** (the flip) | first provenance-stamped mirror write IS the flip event (§5.3); from that instant every choke-point read verifies hash + generation | manifest-first | lock = generated, verified mirror |
| 5 | manifest | tombstoned committed lock; grep-zero tripwire | manifest only | mirror retired with the last legacy reader |

The flip is a single, named, verified cutover event inside Stage 4 (§9),
and verification capability precedes it by a full stage — at no point does
any reader consume a derivative it cannot verify.

Divergence handling matrix (all fail-closed once armed):

| divergence | detector | consequence |
|---|---|---|
| mirror content ≠ manifest (hash) | every choke-point read; daily preflight | abort consumer, alert; only `deploy-pin` re-apply/revert may rewrite the mirror |
| manifest generation ≠ expected-generation record | every choke-point read; daily preflight | stale/replayed pair (less) or torn apply (greater) — abort + named recovery (`deploy-pin reconcile-generation`, §5.2) |
| materialized `.subrepo_runtime` clone HEAD ≠ manifest commit | `subrepo_pin_guard` (existing, re-pointed) | existing strict-pin behavior, unchanged semantics |
| machine manifest ≠ orchestrator main manifest | recording-SLA tripwire (§7) | report from first second → block further applies past SLA / on stacking |
| local epoch ≠ origin/main recorded generation, or anchor unreachable | every MUTATION (fail-closed) + daily preflight/doctor (alarm) | the remote-ledger rollback witness (§5.2) — applies refuse; reads alarm within ≤ 1 session |
| committed umbrella lock ≠ anything | none needed after Stage 5 tombstone | committed lock carries no pin data; any residual parser fails loudly on the tombstone schema |

## 9. Staged rollout (each stage individually shippable and revertible)

**Stage 1 — schema + capture + FIRST DURABLE RECORD (S; orchestrator-only;
zero consumer change).**
Deliverables: manifest schema + loader/verifier (reusing the §2.3
`shadow_ab_runner` conventions, lifted into a shared module both paths
import — not a third hand-copy; the fingerprint-triple lesson); the
neutral state root `~/.renquant/deploy/` with the runtime inventory and
the forward-only expected-generation record (§5.2 — machine state leaves
the umbrella at THIS stage, not later);
`deploy-pin capture` command that reads the DEPLOYED truth — the on-disk
lock AND the actual `.subrepo_runtime` clone HEADs, failing on any
disagreement between them — and emits the PORTABLE manifest (identity
only, §5.1) plus the host inventory; the first manifest
committed via orchestrator PR, **recording today's §2.2 deployed state
durably for the first time**, with `deployment.verify.evidence_ref`
pointing at a content-addressed record of the 07-10/11 readonly-e2e
verification evidence sealed into renquant-artifacts `store://` (the
#13/#14 mechanism) — never a local log path.
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

**Stage 3 — verification choke points ARMED + CLI in shadow (M; ONE
umbrella PR + orchestrator CLI). Authority does NOT flip here.**
Deliverables:
(i) full `deploy-pin` per §6/§7 (plan/apply/revert/capture/
reconcile-generation, record-first flow, emergency lane, SLA tripwire) —
operated in parity/drill mode only; `promote_pin.py` stays native;
(ii) generation-record wiring + mirror-COMPOSITION code (exercised only
against scratch copies; no production mirror write before the flip, §5.3);
(iii) the single narrow umbrella PR, per Codex's "narrow, generated,
independently verified" instruction: the 3 choke-point modules + the 3
direct shell readers (§4.2) gain mirror↔manifest hash+generation
verification at entry — **installed and armed one full stage BEFORE the
authority flip** (Codex r1 point 2), while they still read the authority
lock; doctor/contract/reporting readers re-pointed through
`subrepo_paths`.
Gate: choke-point verification proven by fault injection on SYNTHETIC
stamped mirrors in scratch copies (hand-edited mirror, stale-pair restore,
torn generation, unstamped-lock pass-through — each must produce the named
outcome); green `daily_104` + `weekly_wf_promote` with the conditional
verification armed against the real (unstamped) lock. Rollback: env-flag
the verification off; CLI touches nothing real in this stage.

**Stage 4 — authority flips (M; the named cutover event).**
Pre-flip gates (all mechanical, evidenced in the Stage 4 PR):
(i) **parity harness** — for the current state and for a candidate bump,
`promote_pin.py` dry-run and `deploy-pin` dry-run must plan byte-identical
lock content (behavior invariance / kernel-identity: same resolved pins);
(ii) **auto-revert drill** — forced verify-failure on a scratch copy must
restore the backup pair, advance the generation, and re-sync;
(iii) **stale-pair restore drill** — restoring an old manifest+mirror
backup pair must be REJECTED by the generation check at first consumer
touch (the Codex r1 point-3 replay test, automated);
(iv) M9 snapshot backstop demonstrably invoked (scratch render) in both
bump and revert paths;
(v) Stage 3 verification live in production for ≥ 3 green sessions;
(vi) **host-root restore drill** — restoring a full scratch state-root
backup (manifest + mirror + epoch + receipts together) must be refused at
the next mutation by the remote-anchor comparison (§5.2) and alarmed by
the preflight;
(vii) **anchor-unreachable drill** — mutation with origin/main unreachable
must fail closed; read path must alarm-and-continue per the stated threat
model;
(viii) **fixture-signer rejection test** — an emergency token signed by
the test/PLACEHOLDER key must be rejected with the dedicated error; the
lane stays disabled until the real operator key lands (§7).
The **cutover**: first record-first `deploy-pin apply` on a real pin bump,
after which the manifest is authority and the lock is the verified mirror;
`promote_pin.py` becomes the delegating shim; `check_lock_pins_ci_green.py`
ports to orchestrator CI.
Post-cutover gate: first real bump e2e-verified green with its pin-bump PR
having merged FIRST (record-first proof). Rollback: shim disable is one
line; the mirror IS a valid legacy lock; reverting re-instates lock
authority explicitly (a named un-flip, alarmed, never silent).

**Stage 5 — umbrella tombstone + consumer completion + shim retirement
(S/M, rolling; interacts with R1).**
Deliverables: the committed `subrepos.lock.json` replaced by a TOMBSTONE
(schema `{"schema_version": 2, "kind": "tombstone", "authority":
"renquant-orchestrator:deploy/deployment-manifest.json"}` — old parsers
fail loudly on the missing `subrepos` key rather than reading stale pins;
`.gitignore` gains the generated on-disk mirror); remaining reporting
readers flipped; R0-style tripwire test pinned in the umbrella (grep-zero:
no file outside `subrepo_paths.py` opens a pin source directly);
`promote_pin.py` shim expiry enforced (fail-closed per §6 governance);
orchestrator `repos.py:33` default flipped from the umbrella path to the
manifest, removing the last hardcode. R1's launchd cutovers independently
shrink the umbrella-script consumer set; R-PIN is DONE when the tripwire
holds and the shim is retired — a mechanical condition, not a declaration.

No stage flips more than one thing; every gate is mechanical; every stage
has a stated rollback that does not require the previous stage to be undone.

## 10. Failure modes considered

- **Torn write during apply/revert** → §6: manifest-first ordering + hash
  verification at every consumer entry; a torn pair is unreadable, not
  misreadable.
- **Stale-machine restore (backup restores an old lock)** → the mirror's
  `manifest_sha256` no longer matches the machine manifest → fail-closed at
  first consumer touch; recovery is `deploy-pin` re-apply from the manifest.
- **Replayed backup PAIR (old manifest + its matching mirror restored
  together — internally hash-consistent)** → generation < the forward-only
  expected-generation record → fail-closed at first consumer touch
  (Codex r1 point 3; automated as the Stage 4 pre-flip stale-pair restore
  drill and fault-injected again in Stage 3's gate).
- **Torn apply (crash between manifest write and generation-record
  write)** → manifest generation > expected record → fail-closed with the
  named `deploy-pin reconcile-generation` recovery (§5.2), which re-verifies
  against orchestrator `origin/main` before moving the record.
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
- **No relocation of `.subrepo_runtime` materialized CLONES** — R-PIN moves
  pin-plane STATE to the neutral root (§5.2); relocating the materialized
  checkouts themselves is R1/R2 territory.
- **The umbrella repo is not deleted or emptied** (LONG ledger #9); it
  remains the machine anchor and rollback source, minus pin authority.

## 12. Open questions for review

1. §7 is record-first by default (per r1 review); the emergency lane
   reuses the #465 signed-token pattern with a 1-session reconciliation
   SLA. Is the lane's scope (exact repo/commit pairs) and the
   all-applies-blocked stacking rule sufficient, or should emergency
   applies additionally be rate-limited (e.g. one unreconciled incident
   max, which the stacking rule already implies)?
2. Stage 5 tombstone vs keeping a frozen legacy lock with a warning field:
   tombstone chosen because a frozen-but-parseable lock IS the silent-stale
   hazard this design exists to kill. Confirm.
3. Should the record-first pin-bump PR (and the emergency-lane
   reconciliation PR) auto-merge on Codex approval (it is a
   generated, evidence-carrying diff) or always wait for operator eyes?
   Proposed: normal mutual-review flow, no special-casing.
