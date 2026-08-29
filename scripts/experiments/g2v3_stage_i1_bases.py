"""GOAL-2v3 Stage I-1 harness — base models B0..B3 + life screen, AS PREREGISTERED.

Implements, literally, the "Stage I-1 — preregistration of the base models"
section of doc/design/2026-08-27-goal2v3-intraday-granularity.md (declared
2026-08-28) plus Amendment A1's grid/label/block conventions, reusing the
Stage I-0 GATE_RUN bundle (doc/research/data/2026-08-29-g2v3-i0-gate-run/,
PR #1083) for eligibility-after-drift, the K5 regime construction and the
session/episode block structure.  Every frozen number lives in a module-level
constant so a reviewer (and tests/test_g2v3_stage_i1_harness.py) can check them
against the spec without reading the code paths.

Two entry points:
  python scripts/experiments/g2v3_stage_i1_bases.py            # synthetic smoke (default)
  python scripts/experiments/g2v3_stage_i1_bases.py --dev-run  # the real development run
The `--dev-run` path FAILS CLOSED (exit code 2) unless `load_gate_authorization`
can load the immutable Stage I-0 gate bundle and verify it against the frozen
ACCEPTED_GATE_BUNDLE block below: run_status GATE_RUN, gate_verdict PASS, the
reviewed frozen source commit (resolvable in this repository and containing the
hashed census script + design doc), the seed / script / design / input-manifest
hashes, and the report + audit file hashes on disk.  The 2026-08-27
DEVELOPMENT_ONLY audit is NOT accepted as authorization and is no longer read.
The `--dev-run` configuration is built ONLY from the frozen constants plus the
authorization object (dev_run_config); the private `_smoke_config` hook (tiny
folds / lower IC name floor / synthetic paths) is never reachable from `--dev-run`.

Every report carries a `provenance` block (source commit + clean-tree status,
run_id, exact invocation, UTC start/end from this process's clock, gate-bundle
hashes, hashes of the strategy config / sector maps / SPY daily input consumed,
the full frozen-parameter block including the frozen interpretations, and the
aggregate consumed-bar manifest) that `validate_i1_provenance` rebuilds from the
inputs on disk.

Interpretations where the spec text needed a concrete reading are listed in
INTERPRETATIONS below and copied verbatim into the report.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import gzip
import hashlib
import json
import math
import os
import pathlib
import platform
import re
import subprocess
import sys
import tempfile
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# --------------------------------------------------------------------------
# FROZEN CONSTANTS (the preregistration; do not edit — a change is a new attempt)
# --------------------------------------------------------------------------
H = 13                                   # primary horizon in 10-min bars (spec §3 + I-1)
SLOTS = 39                               # canonical RTH 10-min grid (A1)
SCREEN_SLOTS = tuple(range(H, 2 * H))    # bar-times t = 13..25 (A1: close[t-13], close[t], close[t+13])
DEV_START, DEV_END = "2020-08-01", "2024-06-30"   # development window (spec §2)

SEED_BASE = 20260828
XGB_PARAMS = dict(objective="reg:squarederror", max_depth=3, n_estimators=300,
                  learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                  min_child_weight=20, tree_method="hist", random_state=20260828, n_jobs=8)
ROW_CAP = 4_000_000                      # per-fit training-row cap; sampled WITHOUT replacement
BASE_CODES = {"B0": 0, "B1": 1, "B2": 2, "B3": 3}
MIN_SECTOR_ROWS = 50_000                 # B2: sectors under this (per fold) fold into OTHER
OTHER_SECTOR = "OTHER"
B3_SLOW_SESSIONS = 60                    # slow leg: 60 completed sessions strictly before D
B3_FAST_LAG_SLOTS = SLOTS                # fast leg: same canonical slot one session earlier (t-39)
K5_REGIMES = ("BEAR", "BULL_CALM", "BULL_VOLATILE", "CHOPPY")
B3_LABELS = ("S+F+", "S+F-", "S-F+", "S-F-")   # (slow, fast) sign states; sorted() order is the state_index order

# folds: (train_end, oof_start, oof_end) — forward-chaining, expanding train, 6-month OOF
FOLDS: Tuple[Tuple[str, str, str], ...] = (
    ("2021-12-31", "2022-01-01", "2022-06-30"),
    ("2022-06-30", "2022-07-01", "2022-12-31"),
    ("2022-12-31", "2023-01-01", "2023-06-30"),
    ("2023-06-30", "2023-07-01", "2023-12-31"),
    ("2023-12-31", "2024-01-01", "2024-06-30"),
)
PURGE_BARS = H                           # 13-bar purge gap at the train/OOF boundary

MIN_NAMES_PER_IC = 100                   # A1: each bar-time IC from >=100 names
MIN_PAIRS = 8                            # fail-closed rho1 estimator below this (spec §3)
LIFE_BAR_T = 1.0                         # block-t >= 1.0 overall, on dependence-adjusted units
SECONDARY_HORIZONS = (1, 3, 39)          # DIAGNOSTIC ONLY — never gating

VZ_TRAILING_SESSIONS = 60                # vz denominator window (spec F)
VZ_MIN_PRESENT = 48                      # interpretation: >=80% of 60 present (the frozen eligibility fraction)
B1_STATE_LAG_SESSIONS = 1                # interpretation: B1 state = K5 regime as-of the PRIOR close

FEATURE_NAMES = ("r1", "r3", "r13", "rv13", "rng13", "vz", "gap", "slot", "m13", "sec13", "rel13")

INTERPRETATIONS = [
    "All bar returns (r1, r3, r13, m13, sec13, label) are LOG returns; rel13 = r13 - sec13 in log units. "
    "gap, vz and rng13 use the spec's literal arithmetic formulas.",
    "rv13 = sqrt(sum of squared 1-bar log returns over the 13 bars t-12..t); NaN unless closes t-13..t are all present.",
    "rng13 window = 13 bars t-12..t on high/low; NaN if any high/low is missing or max high == min low.",
    "vz denominator = mean of the PRESENT same-slot volumes over the 60 sessions strictly before D; NaN when fewer than "
    "48 (80%, the frozen eligibility coverage fraction) are present. A literal all-60-present rule would void the feature "
    "on the thin IEX feed.",
    "gap uses the prior session's LAST present RTH close (the census's IEX session-close convention) and requires the "
    "slot-0 open of D; prior session = previous entry of the census session list.",
    "B1 state for session D = the K5 regime computed at the prior session's close (regime.shift(1), the pure upsample "
    "of the post-close 104 regime series; no same-day close information, consistent with the B3 'as-of prior close' "
    "rule). Regime EPISODES for the screen use the census's unshifted same-day mapping so block structure is identical "
    "to the I-0 artifact.",
    "B2: names absent from config sector_map are assigned to OTHER (the spec's catch-all) rather than dropped; small "
    "sectors fold into OTHER per fold; OTHER is itself never re-folded.",
    "A conditioned state with zero training rows in a fold fits no model and its OOF rows are unscored (abstain), never "
    "re-routed to another state.",
    "The 13-bar purge is implemented literally (training label-end bar + 13 <= first OOF observation bar) and is "
    "satisfied by construction on the A1 grid (within-session labels; first OOF row at slot 13).",
    "Secondary horizons: h=1 and h=3 are scored DIAGNOSTICALLY by ranking the h=13-trained prediction against the "
    "within-session forward 1-/3-bar log label at the same bar-times; h=39 is NOT computed (no within-session 39-bar "
    "forward window exists on the 39-slot grid).",
    "s0 = -r13 (the A1 proxy) is scored on the same OOF rows as a naive reference; it is not a base and not gated.",
    "A bar-time IC whose Spearman is undefined (constant predictions) is treated as missing, so that session forms no block.",
]

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "doc/research/data/2026-08-29-g2v3-i1"

# --------------------------------------------------------------------------
# THE GATE this harness is bound to: the immutable Stage I-0 GATE_RUN bundle.
# Every value is copied from doc/research/data/2026-08-29-g2v3-i0-gate-run/provenance.json
# (PR #1083). `--dev-run` refuses to start unless the bundle on disk agrees with EVERY
# field here AND the frozen commit is resolvable in this repository with these blobs.
# A change to any value is a re-binding and needs its own review.
# --------------------------------------------------------------------------
ACCEPTED_GATE_BUNDLE = dict(
    dir="doc/research/data/2026-08-29-g2v3-i0-gate-run",
    report_file="g2v3_stage_i0_report.json",
    audit_file="g2v3_stage_i0_audit.json.gz",
    provenance_file="provenance.json",
    run_id="i0-gate-20260829-f3d5bf7b",
    frozen_source_commit="f3d5bf7bd75ffa9c0fb59f8c3bfa98fa509e8779",
    run_status="GATE_RUN",
    gate_verdict="PASS",
    gate_h=13,
    gate_window=("2020-08-01", "2024-06-30"),
    seed_list_path="doc/research/data/2026-08-27-g2v3-i0/g2v3_seed.txt",
    seed_list_sha256="cd6f3ed7ab1f353b21154ecb0cba4b27811927854f5a8666e62bfd86c7d9a3cc",
    seed_list_count=2144,
    census_script_path="scripts/experiments/g2v3_stage_i0_census.py",
    census_script_sha256="8e6ddd6e361edcf8f6fdc0d8b02f53ee8af5418943fa081c84459f3b2386eada",
    design_doc_path="doc/design/2026-08-27-goal2v3-intraday-granularity.md",
    design_doc_sha256="21678a53c593ead945193566bed4ea30c1e6f364dbfde5da8d5c49539b3808f6",
    input_manifest_aggregate_sha256="a878f1caeaee863cc06c2f9b3ab0d6eba4389d656a4b4dabd731a1844cdfd4d9",
    input_manifest_count=2124,
    report_sha256="da41a706f31b3f39b9ccc9631b93a76a6cb994c8877f112ce49989916634cf44",
    audit_sha256="dd5127d7326919b777acd0a6bf819dcc158c9cd02a44cd76ef7ca71fa844f3a9",
)
GATE_DIR = REPO / ACCEPTED_GATE_BUNDLE["dir"]
GATE_AUDIT = GATE_DIR / ACCEPTED_GATE_BUNDLE["audit_file"]      # the ONLY census audit --dev-run may consume
MANIFEST_METHOD = ("sha256 of the UTF-8 text formed by joining, with '\\n' and no trailing newline, the lines "
                   "'<ticker> <sha256>' for tickers in sorted() order")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^i1-(dev|smoke)-\d{8}-([0-9a-f]{8}|nogit)$")
_TS = "%Y-%m-%dT%H:%M:%SZ"


class GateNotAuthorized(RuntimeError):
    """The Stage I-0 gate bundle is missing, tampered, not GATE_RUN/PASS, or not the bundle this harness is bound to."""


@dataclasses.dataclass(frozen=True)
class GateAuthorization:
    """What `load_gate_authorization` hands to --dev-run: the verified identity of the gate bundle."""
    bundle_dir: pathlib.Path
    report_path: pathlib.Path
    audit_path: pathlib.Path
    provenance_path: pathlib.Path
    run_id: str
    frozen_source_commit: str
    gate_verdict: str
    report_sha256: str
    audit_sha256: str
    provenance_sha256: str
    input_manifest_aggregate_sha256: str
    input_manifest_count: int
    bear_n_eff_adj: Optional[float]

    def as_record(self) -> dict:
        return dict(dir=str(self.bundle_dir), run_id=self.run_id, frozen_source_commit=self.frozen_source_commit,
                    gate_verdict=self.gate_verdict, report_sha256=self.report_sha256, audit_sha256=self.audit_sha256,
                    provenance_sha256=self.provenance_sha256,
                    input_manifest_aggregate_sha256=self.input_manifest_aggregate_sha256,
                    input_manifest_count=self.input_manifest_count, bear_n_eff_adj=self.bear_n_eff_adj)


def sha256_file(p: pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def sha256_json(obj) -> str:
    """sha256 of the canonical JSON (sorted keys, no whitespace) of a JSON-able object."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def manifest_aggregate(hashes: Dict[str, str]) -> str:
    """The gate bundle's aggregate method (provenance.json input_manifest.aggregate_method), reused verbatim."""
    text = "\n".join(f"{t} {hashes[t]}" for t in sorted(hashes))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _dig(obj, *keys):
    for k in keys:
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _verify_gate_bundle_files(repo_root: pathlib.Path) -> GateAuthorization:
    """Every FILE-level check of the gate bundle against ACCEPTED_GATE_BUNDLE (no git). Raises GateNotAuthorized
    with the first disagreement. `load_gate_authorization` adds the git binding on top; this helper exists so
    tests can exercise the file checks on tmp copies of the bundle."""
    g = ACCEPTED_GATE_BUNDLE
    repo_root = pathlib.Path(repo_root)
    bundle = repo_root / g["dir"]
    report_p, audit_p, prov_p = bundle / g["report_file"], bundle / g["audit_file"], bundle / g["provenance_file"]

    def refuse(why: str):
        raise GateNotAuthorized(f"Stage I-0 gate bundle {g['dir']}: {why}")

    if not bundle.is_dir():
        refuse("bundle directory missing")
    for p in (report_p, audit_p, prov_p):
        if not p.is_file():
            refuse(f"{p.name} missing")
    try:
        report = json.loads(report_p.read_text(encoding="utf-8"))
    except ValueError as exc:
        refuse(f"{report_p.name} unparseable ({exc})")
    if not isinstance(report, dict):
        refuse(f"{report_p.name} is not a JSON object")
    # --- the verdict, read from the report itself (a development audit is not authorization)
    if report.get("run_status") != g["run_status"]:
        refuse(f"report run_status {report.get('run_status')!r} != {g['run_status']!r} "
               f"(a DEVELOPMENT_ONLY / development audit is not authorization)")
    if report.get("gate_verdict") != g["gate_verdict"]:
        refuse(f"report gate_verdict {report.get('gate_verdict')!r} != {g['gate_verdict']!r}")
    if report.get("h") != g["gate_h"]:
        refuse(f"report h {report.get('h')!r} != {g['gate_h']!r}")
    # --- provenance.json field by field against the constants
    try:
        prov = json.loads(prov_p.read_text(encoding="utf-8"))
    except ValueError as exc:
        refuse(f"{prov_p.name} unparseable ({exc})")
    if not isinstance(prov, dict):
        refuse(f"{prov_p.name} is not a JSON object")
    expected = {
        "run_id": (_dig(prov, "run_id"), g["run_id"]),
        "frozen_source_commit": (_dig(prov, "frozen_source_commit"), g["frozen_source_commit"]),
        "report_run_status": (_dig(prov, "report_run_status"), g["run_status"]),
        "gate_verdict": (_dig(prov, "gate_verdict"), g["gate_verdict"]),
        "frozen_parameters.h": (_dig(prov, "frozen_parameters", "h"), g["gate_h"]),
        "frozen_parameters.window.start": (_dig(prov, "frozen_parameters", "window", "start"), g["gate_window"][0]),
        "frozen_parameters.window.end": (_dig(prov, "frozen_parameters", "window", "end"), g["gate_window"][1]),
        "seed_list.path": (_dig(prov, "seed_list", "path"), g["seed_list_path"]),
        "seed_list.sha256": (_dig(prov, "seed_list", "sha256"), g["seed_list_sha256"]),
        "seed_list.count": (_dig(prov, "seed_list", "count"), g["seed_list_count"]),
        "code.census_script.path": (_dig(prov, "code", "census_script", "path"), g["census_script_path"]),
        "code.census_script.sha256": (_dig(prov, "code", "census_script", "sha256"), g["census_script_sha256"]),
        "code.census_script.commit": (_dig(prov, "code", "census_script", "commit"), g["frozen_source_commit"]),
        "code.design_doc.path": (_dig(prov, "code", "design_doc", "path"), g["design_doc_path"]),
        "code.design_doc.sha256": (_dig(prov, "code", "design_doc", "sha256"), g["design_doc_sha256"]),
        "code.design_doc.commit": (_dig(prov, "code", "design_doc", "commit"), g["frozen_source_commit"]),
        "input_manifest.aggregate_sha256": (_dig(prov, "input_manifest", "aggregate_sha256"),
                                            g["input_manifest_aggregate_sha256"]),
        "input_manifest.count": (_dig(prov, "input_manifest", "count"), g["input_manifest_count"]),
        "outputs.report.path": (_dig(prov, "outputs", "report", "path"), g["report_file"]),
        "outputs.report.sha256": (_dig(prov, "outputs", "report", "sha256"), g["report_sha256"]),
        "outputs.audit.path": (_dig(prov, "outputs", "audit", "path"), g["audit_file"]),
        "outputs.audit.sha256": (_dig(prov, "outputs", "audit", "sha256"), g["audit_sha256"]),
    }
    for key, (got, want) in expected.items():
        if got != want:
            refuse(f"provenance {key} = {got!r}, this harness is bound to {want!r}")
    if _dig(prov, "clean_tree") is not True:
        refuse(f"provenance clean_tree = {_dig(prov, 'clean_tree')!r}, the gate run must come from a clean tree")
    # --- the files on disk against the constants (the provenance's own claims are not trusted)
    report_sha = sha256_file(report_p)
    if report_sha != g["report_sha256"]:
        refuse(f"{report_p.name} sha256 on disk {report_sha[:12]}.. != bound {g['report_sha256'][:12]}.. (tampered)")
    audit_sha = sha256_file(audit_p)
    if audit_sha != g["audit_sha256"]:
        refuse(f"{audit_p.name} sha256 on disk {audit_sha[:12]}.. != bound {g['audit_sha256'][:12]}.. (tampered)")
    seed_p = repo_root / g["seed_list_path"]
    if not seed_p.is_file():
        refuse(f"seed list {g['seed_list_path']} missing")
    if sha256_file(seed_p) != g["seed_list_sha256"]:
        refuse(f"seed list {g['seed_list_path']} sha256 on disk != bound {g['seed_list_sha256'][:12]}..")
    n_seed = sum(1 for line in seed_p.read_text(encoding="utf-8").splitlines() if line.strip())
    if n_seed != g["seed_list_count"]:
        refuse(f"seed list has {n_seed} names, bound count is {g['seed_list_count']}")
    try:
        with gzip.open(audit_p, "rt", encoding="utf-8") as fh:
            audit = json.load(fh)
    except (OSError, ValueError) as exc:
        refuse(f"{audit_p.name} unreadable ({exc})")
    hashes = audit.get("bar_store_sha256") if isinstance(audit, dict) else None
    if not isinstance(hashes, dict) or not hashes:
        refuse(f"{audit_p.name} carries no bar_store_sha256 map")
    if not isinstance(audit.get("eligible_membership_post_drift"), dict):
        refuse(f"{audit_p.name} carries no eligible_membership_post_drift")
    agg = manifest_aggregate(hashes)
    if agg != g["input_manifest_aggregate_sha256"] or len(hashes) != g["input_manifest_count"]:
        refuse(f"input manifest recomputed from the audit = {agg[:12]}.. over {len(hashes)} files, bound "
               f"{g['input_manifest_aggregate_sha256'][:12]}.. over {g['input_manifest_count']}")
    bear = _dig(report, "by_regime", "BEAR", "n_eff_adj")
    return GateAuthorization(
        bundle_dir=bundle, report_path=report_p, audit_path=audit_p, provenance_path=prov_p,
        run_id=g["run_id"], frozen_source_commit=g["frozen_source_commit"], gate_verdict=g["gate_verdict"],
        report_sha256=report_sha, audit_sha256=audit_sha, provenance_sha256=sha256_file(prov_p),
        input_manifest_aggregate_sha256=agg, input_manifest_count=len(hashes),
        bear_n_eff_adj=(float(bear) if isinstance(bear, (int, float)) else None))


def _git(repo_root: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True)


def load_gate_authorization(repo_root: pathlib.Path = None) -> GateAuthorization:
    """FAIL-CLOSED authorization for --dev-run. Returns a GateAuthorization only when the bundle under
    `repo_root` passes every file check in `_verify_gate_bundle_files` AND the frozen source commit is
    resolvable in that repository AND the census script + design doc blobs at that commit hash to the
    bound values. Anything else raises GateNotAuthorized with the specific reason."""
    repo_root = pathlib.Path(repo_root if repo_root is not None else REPO)
    auth = _verify_gate_bundle_files(repo_root)
    g = ACCEPTED_GATE_BUNDLE
    commit = g["frozen_source_commit"]
    try:
        r = _git(repo_root, "cat-file", "-e", commit + "^{commit}")
    except OSError as exc:
        raise GateNotAuthorized(f"cannot run git in {repo_root} to verify the frozen commit ({exc})")
    if r.returncode != 0:
        raise GateNotAuthorized(f"frozen source commit {commit[:8]} is not resolvable in {repo_root} "
                                f"(a bundle copy outside the reviewed repository is not authorization)")
    for key in ("census_script", "design_doc"):
        blob = _git(repo_root, "show", f"{commit}:{g[key + '_path']}")
        if blob.returncode != 0:
            raise GateNotAuthorized(f"{g[key + '_path']} does not exist at {commit[:8]}")
        got = hashlib.sha256(blob.stdout).hexdigest()
        if got != g[key + "_sha256"]:
            raise GateNotAuthorized(f"{key} at {commit[:8]} hashes to {got[:12]}.., bound {g[key + '_sha256'][:12]}..")
    return auth
SPY_DAILY = pathlib.Path("/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet")
STRATEGY_CONFIG = pathlib.Path(
    "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json")
SPY = "SPY"


# --------------------------------------------------------------------------
# run configuration
# --------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class RunConfig:
    bar_store: pathlib.Path
    census_audit: pathlib.Path
    spy_daily: pathlib.Path
    sector_map: Dict[str, str]
    sector_etf_map: Dict[str, str]
    out_dir: pathlib.Path
    run_status: str                          # "DEV_RUN" | "SMOKE"
    folds: Tuple[Tuple[str, str, str], ...] = FOLDS
    min_names: int = MIN_NAMES_PER_IC
    dev_start: str = DEV_START
    dev_end: str = DEV_END
    row_cap: int = ROW_CAP
    gate: Optional[GateAuthorization] = None            # REQUIRED for DEV_RUN (run_stage_i1 refuses otherwise)
    strategy_config: Optional[pathlib.Path] = None      # the file the sector maps were read from (hashed)


def dev_run_config(auth: GateAuthorization) -> RunConfig:
    """The ONLY way the --dev-run path builds its configuration: frozen constants + real paths + the gate
    authorization from `load_gate_authorization`. The census audit is the GATE bundle's audit, nothing else."""
    if not isinstance(auth, GateAuthorization):
        raise GateNotAuthorized("dev_run_config needs the GateAuthorization returned by load_gate_authorization()")
    store = os.environ.get("G2V3_BAR_STORE", "")
    if not store or not pathlib.Path(store).is_dir():
        sys.exit("set G2V3_BAR_STORE to the fetched 10-min bar directory (one parquet per ticker)")
    cfg = json.load(open(STRATEGY_CONFIG))
    return RunConfig(bar_store=pathlib.Path(store), census_audit=auth.audit_path, spy_daily=SPY_DAILY,
                     sector_map=dict(cfg["sector_map"]), sector_etf_map=dict(cfg["sector_etf_map"]),
                     out_dir=OUT_DIR, run_status="DEV_RUN", gate=auth, strategy_config=STRATEGY_CONFIG)


def _smoke_config(bar_store, census_audit, spy_daily, sector_map, sector_etf_map, out_dir,
                  folds, min_names, dev_start, dev_end, strategy_config=None, gate=None) -> RunConfig:
    """PRIVATE smoke hook: the only entry that accepts fold/threshold overrides. Never used by --dev-run."""
    return RunConfig(bar_store=pathlib.Path(bar_store), census_audit=pathlib.Path(census_audit),
                     spy_daily=pathlib.Path(spy_daily), sector_map=dict(sector_map),
                     sector_etf_map=dict(sector_etf_map), out_dir=pathlib.Path(out_dir), run_status="SMOKE",
                     folds=tuple(tuple(f) for f in folds), min_names=int(min_names),
                     dev_start=dev_start, dev_end=dev_end, gate=gate,
                     strategy_config=(pathlib.Path(strategy_config) if strategy_config else None))


# --------------------------------------------------------------------------
# census artifact + bar store (A1 canonical grid, census conventions)
# --------------------------------------------------------------------------
def load_census_audit(path: pathlib.Path) -> dict:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        return json.load(fh)


def session_list(audit: dict, dev_start: str, dev_end: str) -> List[str]:
    """The census's all_sessions (keys of eligible_membership_post_drift), clipped to the dev window."""
    return sorted(s for s in audit["eligible_membership_post_drift"] if dev_start <= s <= dev_end)


def eligibility_matrix(audit: dict, sessions: Sequence[str], names: Sequence[str]) -> np.ndarray:
    """(S, N) bool: name eligible on session after BOTH drift layers — read from the census, never recomputed."""
    nidx = {n: i for i, n in enumerate(names)}
    elig = np.zeros((len(sessions), len(names)), dtype=bool)
    mem = audit["eligible_membership_post_drift"]
    for si, s in enumerate(sessions):
        for n in mem.get(s, ()):
            j = nidx.get(n)
            if j is not None:
                elig[si, j] = True
    return elig


def load_panel(path: pathlib.Path, sessions: Sequence[str]) -> Optional[Dict[str, np.ndarray]]:
    """One ticker parquet (ts/open/high/low/close/volume, UTC) -> dict of (S, 39) float64 grids.

    Grid convention is the census's: ET, RTH [09:30, 16:00), slot = ((h*60+m) - 570)//10, position IS time,
    NaN = missing. Sessions outside `sessions` are ignored. Returns None when no session overlaps.
    """
    df = pd.read_parquet(path, columns=["ts", "open", "high", "low", "close", "volume"])
    if df.empty:
        return None
    ts = pd.to_datetime(df["ts"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    df = df.assign(session=et.dt.strftime("%Y-%m-%d"),
                   slot=((et.dt.hour * 60 + et.dt.minute) - 570) // 10)
    rth = (et.dt.time >= _dt.time(9, 30)) & (et.dt.time < _dt.time(16, 0))
    df = df[rth & (df["slot"] >= 0) & (df["slot"] < SLOTS)]
    sidx = {s: i for i, s in enumerate(sessions)}
    df = df[df["session"].map(sidx).notna()]
    if df.empty:
        return None
    si = df["session"].map(sidx).to_numpy(dtype=int)
    sl = df["slot"].to_numpy(dtype=int)
    out = {}
    for col in ("open", "high", "low", "close", "volume"):
        g = np.full((len(sessions), SLOTS), np.nan)
        g[si, sl] = df[col].to_numpy(dtype=float)
        out[col] = g
    return out


# --------------------------------------------------------------------------
# market context: K5 regime (census formula), B1 state, B3 macro state, m13, sec13
# --------------------------------------------------------------------------
def k5_regime_daily(spy_close: pd.Series) -> pd.Series:
    """The census's frozen K5 formula on SPY official daily closes (same-day; used for EPISODES)."""
    spy = spy_close.astype(float)
    trend = spy > spy.rolling(200).mean()
    vol = spy.pct_change().rolling(20).std()
    volhi = vol > vol.rolling(252, min_periods=60).median()
    regime = pd.Series("BEAR", index=spy.index, dtype=object)
    regime[trend & ~volhi] = "BULL_CALM"
    regime[trend & volhi] = "BULL_VOLATILE"
    regime[~trend & ~volhi] = "CHOPPY"
    return regime


def regime_per_session(regime_daily: pd.Series, sessions: Sequence[str], lag_sessions: int) -> np.ndarray:
    idx = pd.to_datetime(list(sessions))
    r = regime_daily.shift(lag_sessions) if lag_sessions else regime_daily
    return r.reindex(idx).ffill().to_numpy(dtype=object)


def b3_slow_state(spy_daily_close: pd.Series, sessions: Sequence[str]) -> np.ndarray:
    """sign(close[D-1]/close[D-61] - 1) over the 60 completed sessions strictly before D; zero => +1; <61 => NaN."""
    dates = np.asarray(spy_daily_close.index.values, dtype="datetime64[D]")
    closes = spy_daily_close.to_numpy(dtype=float)
    out = np.full(len(sessions), np.nan)
    for si, s in enumerate(sessions):
        p = int(np.searchsorted(dates, np.datetime64(s, "D"), side="left"))   # closes strictly before D
        if p < B3_SLOW_SESSIONS + 1:
            continue
        a, b = closes[p - 1], closes[p - B3_SLOW_SESSIONS - 1]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        out[si] = 1.0 if (a / b - 1.0) >= 0 else -1.0
    return out


def b3_fast_state(spy_close_grid: np.ndarray) -> np.ndarray:
    """(S, 39) sign(close[s, t] / close[s-1, t] - 1): same canonical slot one session earlier; zero => +1; missing => NaN."""
    out = np.full(spy_close_grid.shape, np.nan)
    cur, prev = spy_close_grid[1:], spy_close_grid[:-1]
    ok = np.isfinite(cur) & np.isfinite(prev)
    ratio = np.where(ok, cur / np.where(ok, prev, 1.0) - 1.0, np.nan)
    out[1:] = np.where(ok, np.where(ratio >= 0, 1.0, -1.0), np.nan)
    return out


def trailing_log_return(close_grid: np.ndarray, k: int) -> np.ndarray:
    """(S, 39) log(close[t]/close[t-k]) within session; NaN when either close is missing or t < k."""
    lc = np.log(close_grid)
    out = np.full(lc.shape, np.nan)
    out[:, k:] = lc[:, k:] - lc[:, :-k]
    return out


# --------------------------------------------------------------------------
# feature set F + labels, per name
# --------------------------------------------------------------------------
def name_features(panel: Dict[str, np.ndarray], ctx: dict, sec13_grid: Optional[np.ndarray]) -> dict:
    """All (S, 39) feature grids for one name; NaN on any missing bar inside a window (no imputation)."""
    close, high, low, vol, opn = panel["close"], panel["high"], panel["low"], panel["volume"], panel["open"]
    S = close.shape[0]
    lc = np.log(close)
    r1 = trailing_log_return(close, 1)
    r3 = trailing_log_return(close, 3)
    r13 = trailing_log_return(close, H)
    # rv13: sqrt(sum of the 13 squared 1-bar log returns t-12..t); needs closes t-13..t
    sq = r1 ** 2
    rv13 = np.full(close.shape, np.nan)
    for t in range(H, SLOTS):
        win = sq[:, t - H + 1:t + 1]
        rv13[:, t] = np.where(np.isfinite(win).all(axis=1), np.sqrt(win.sum(axis=1)), np.nan)
    # rng13 over 13 bars t-12..t
    rng13 = np.full(close.shape, np.nan)
    for t in range(H - 1, SLOTS):
        lo = low[:, t - H + 1:t + 1]
        hi = high[:, t - H + 1:t + 1]
        mn, mx = lo.min(axis=1), hi.max(axis=1)          # NaN propagates: any missing bar => NaN
        den = mx - mn
        okw = np.isfinite(mn) & np.isfinite(mx) & np.isfinite(close[:, t]) & (den > 0)
        rng13[:, t] = np.where(okw, (close[:, t] - mn) / np.where(okw, den, 1.0), np.nan)
    # vz: volume_t / mean same-slot volume over the 60 sessions strictly before D, - 1
    vz = np.full(close.shape, np.nan)
    for s in range(S):
        lo_s = max(0, s - VZ_TRAILING_SESSIONS)
        if s - lo_s < VZ_MIN_PRESENT:
            continue
        win = vol[lo_s:s]
        cnt = np.isfinite(win).sum(axis=0)
        mean = np.where(cnt >= VZ_MIN_PRESENT, np.nansum(win, axis=0) / np.maximum(cnt, 1), np.nan)
        vz[s] = np.where(mean > 0, vol[s] / np.where(mean > 0, mean, 1.0) - 1.0, np.nan)
    # gap: open[slot 0] / prior session's last present close - 1 (broadcast over the session)
    gap = np.full(close.shape, np.nan)
    last_close = np.full(S, np.nan)
    for s in range(S):
        fin = np.where(np.isfinite(close[s]))[0]
        if len(fin):
            last_close[s] = close[s, fin[-1]]
    for s in range(1, S):
        if np.isfinite(opn[s, 0]) and np.isfinite(last_close[s - 1]):
            gap[s, :] = opn[s, 0] / last_close[s - 1] - 1.0
    slot = np.broadcast_to(np.arange(SLOTS, dtype=float), close.shape)
    m13 = ctx["m13"]
    sec13 = sec13_grid if sec13_grid is not None else np.full(close.shape, np.nan)
    rel13 = r13 - sec13
    # labels: forward within-session log returns (dropped when truncated => NaN here)
    y13 = np.full(close.shape, np.nan); y13[:, :SLOTS - H] = lc[:, H:] - lc[:, :SLOTS - H]
    y1 = np.full(close.shape, np.nan); y1[:, :SLOTS - 1] = lc[:, 1:] - lc[:, :SLOTS - 1]
    y3 = np.full(close.shape, np.nan); y3[:, :SLOTS - 3] = lc[:, 3:] - lc[:, :SLOTS - 3]
    return dict(r1=r1, r3=r3, r13=r13, rv13=rv13, rng13=rng13, vz=vz, gap=gap, slot=slot,
                m13=m13, sec13=sec13, rel13=rel13, y13=y13, y1=y1, y3=y3)


def build_rows(cfg: RunConfig, audit: dict, sessions: List[str], log=print) -> dict:
    """Assemble the (name, session, slot) observation table over eligible names; t in 13..25 only (A1 rule)."""
    store = cfg.bar_store
    audited = audit["bar_store_sha256"]
    names_eligible = sorted({n for s in sessions for n in audit["eligible_membership_post_drift"].get(s, ())})
    etfs = sorted({v for v in cfg.sector_etf_map.values()})
    needed = sorted(set(names_eligible) | set(etfs) | {SPY})
    # --- store identity: every consumed file must be the file the gate census audited (fail closed).
    # The consumed-bar manifest is the store itself hashed NOW; a file absent from the audit or hashing
    # differently from the audit's per-file value is refused — the dev run must consume the audited store.
    mismatched, unaudited, missing, actual = [], [], [], {}
    for n in needed:
        p = store / f"{n}.parquet"
        if not p.exists():
            missing.append(n)
            continue
        actual[n] = sha256_file(p)
        if n not in audited:
            unaudited.append(n)
        elif actual[n] != audited[n]:
            mismatched.append(n)
    if mismatched or unaudited:
        sys.exit(f"bar store differs from the gate census's audited store: {len(mismatched)} hash mismatches "
                 f"(e.g. {mismatched[:5]}), {len(unaudited)} files absent from the audit (e.g. {unaudited[:5]}); "
                 f"refusing to run on an unaudited store")
    if SPY in missing:
        sys.exit("SPY 10-min bars missing from the bar store")
    consumed = {SPY: actual[SPY]}                       # every file this run READS, hashed at run time
    # --- market context
    spy_daily = pd.read_parquet(cfg.spy_daily, columns=["close"])["close"]
    spy_daily.index = pd.to_datetime(spy_daily.index)
    spy_daily = spy_daily.sort_index()
    regime_daily = k5_regime_daily(spy_daily)
    spy_panel = load_panel(store / f"{SPY}.parquet", sessions)
    ctx = dict(
        regime_episode=regime_per_session(regime_daily, sessions, 0),
        regime_b1=regime_per_session(regime_daily, sessions, B1_STATE_LAG_SESSIONS),
        b3_slow=b3_slow_state(spy_daily, sessions),
        b3_fast=b3_fast_state(spy_panel["close"]),
        m13=trailing_log_return(spy_panel["close"], H),
    )
    sec13_by_sector: Dict[str, Optional[np.ndarray]] = {}
    for sector, etf in cfg.sector_etf_map.items():
        p = store / f"{etf}.parquet"
        if etf in missing or not p.exists():
            sec13_by_sector[sector] = None                     # ETF absent => sec13 NaN for that sector
            continue
        panel = load_panel(p, sessions)
        consumed[etf] = actual[etf]
        sec13_by_sector[sector] = trailing_log_return(panel["close"], H) if panel else None
    # --- per-name rows
    elig = eligibility_matrix(audit, sessions, names_eligible)
    b1_codes = np.array([K5_REGIMES.index(r) if r in K5_REGIMES else -1 for r in ctx["regime_b1"]], dtype=np.int16)
    b2_labels = sorted(set(cfg.sector_map.values()) | {OTHER_SECTOR})
    cols = {k: [] for k in ("name", "session", "slot")}
    feats, labels, states = [], [], {"b1": [], "b2": [], "b3": []}
    tslice = np.array(SCREEN_SLOTS)
    for j, n in enumerate(names_eligible):
        p = store / f"{n}.parquet"
        if not p.exists():
            continue
        consumed[n] = actual[n]
        panel = load_panel(p, sessions)
        if panel is None:
            continue
        sector = cfg.sector_map.get(n)
        f = name_features(panel, ctx, sec13_by_sector.get(sector) if sector else None)
        close = panel["close"]
        exists = (np.isfinite(close[:, tslice - H]) & np.isfinite(close[:, tslice])
                  & np.isfinite(close[:, tslice + H]) & elig[:, j][:, None])
        si, ti = np.where(exists)
        if len(si) == 0:
            continue
        tt = tslice[ti]
        cols["name"].append(np.full(len(si), j, dtype=np.int32))
        cols["session"].append(si.astype(np.int32))
        cols["slot"].append(tt.astype(np.int16))
        feats.append(np.stack([f[k][si, tt] for k in FEATURE_NAMES], axis=1).astype(np.float32))
        labels.append(np.stack([f["y13"][si, tt], f["y1"][si, tt], f["y3"][si, tt]], axis=1).astype(np.float32))
        states["b1"].append(b1_codes[si])
        states["b2"].append(np.full(len(si), b2_labels.index(sector if sector else OTHER_SECTOR), dtype=np.int16))
        slow, fast = ctx["b3_slow"][si], ctx["b3_fast"][si, tt]
        ok3 = np.isfinite(slow) & np.isfinite(fast)
        # B3_LABELS order: index = 2*(slow<0) + (fast<0)  ->  S+F+, S+F-, S-F+, S-F-
        b3 = np.where(ok3, 2 * (slow < 0).astype(int) + (fast < 0).astype(int), -1).astype(np.int16)
        states["b3"].append(b3)
        if (j + 1) % 200 == 0:
            log(f"  rows: {j + 1}/{len(names_eligible)} names", flush=True)
    if not feats:
        sys.exit("no observations built — check the bar store / census audit alignment")
    rows = dict(
        name=np.concatenate(cols["name"]), session=np.concatenate(cols["session"]),
        slot=np.concatenate(cols["slot"]), X=np.concatenate(feats), Y=np.concatenate(labels),
        b1=np.concatenate(states["b1"]), b2=np.concatenate(states["b2"]), b3=np.concatenate(states["b3"]),
        state_labels={"B0": ["ALL"], "B1": list(K5_REGIMES), "B2": b2_labels, "B3": list(B3_LABELS)},
        names=names_eligible, sessions=sessions, regime_episode=ctx["regime_episode"],
        consumed_sha256=consumed, missing_files=missing,
        sec13_available={s: (g is not None) for s, g in sec13_by_sector.items()},
    )
    rows["s0"] = -rows["X"][:, FEATURE_NAMES.index("r13")]          # the A1 proxy, naive reference
    return rows


# --------------------------------------------------------------------------
# folds, purge, row cap, fitting
# --------------------------------------------------------------------------
def fold_masks(rows: dict, sessions: List[str], fold: Tuple[str, str, str]) -> Tuple[np.ndarray, np.ndarray]:
    train_end, oof_start, oof_end = fold
    pos = rows["session"]
    train = pos <= (np.searchsorted(sessions, train_end, side="right") - 1)
    oof = (pos >= np.searchsorted(sessions, oof_start, side="left")) & \
          (pos <= (np.searchsorted(sessions, oof_end, side="right") - 1))
    return apply_purge(rows, sessions, train, oof), oof


def apply_purge(rows: dict, sessions: List[str], train: np.ndarray, oof: np.ndarray) -> np.ndarray:
    """Literal 13-bar purge: a training label may end no later than PURGE_BARS bars before the first OOF observation.

    Bars are numbered continuously (session_position * 39 + slot). On the A1 grid this is satisfied by
    construction (within-session labels, first OOF row at slot 13) — kept explicit so the boundary is checked.
    """
    if not oof.any():
        return train
    bar = rows["session"].astype(np.int64) * SLOTS + rows["slot"].astype(np.int64)
    first_oof_bar = int(bar[oof].min())
    label_end = bar + H
    return train & (label_end + PURGE_BARS <= first_oof_bar)


def fit_seed(fold_index: int, base_code: int, state_index: int) -> int:
    return SEED_BASE + 1000 * fold_index + 100 * base_code + state_index


def cap_rows(idx: np.ndarray, row_cap: int, seed: int) -> Tuple[np.ndarray, bool]:
    """Global (unstratified) subsample WITHOUT replacement to exactly row_cap rows when the frame exceeds it."""
    if len(idx) <= row_cap:
        return idx, False
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(idx, size=row_cap, replace=False)), True


def fit_predict(X_tr: np.ndarray, y_tr: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    import xgboost as xgb
    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(X_tr, y_tr)
    return model.predict(X_te) if len(X_te) else np.zeros(0, dtype=np.float32)


def b2_state_map(b2_codes: np.ndarray, labels: List[str], train: np.ndarray) -> np.ndarray:
    """Per fold: sectors with < MIN_SECTOR_ROWS training rows fold into OTHER (OTHER itself is never re-folded)."""
    other = labels.index(OTHER_SECTOR)
    cnt = np.bincount(b2_codes[train], minlength=len(labels))
    small = [c for c in range(len(labels)) if c != other and cnt[c] < MIN_SECTOR_ROWS]
    out = b2_codes.copy()
    if small:
        out[np.isin(out, small)] = other
    return out


def run_bases(rows: dict, cfg: RunConfig, log=print) -> Tuple[Dict[str, np.ndarray], list, list]:
    """Fit every (fold, base, state) model and fill per-base OOF predictions (NaN = abstained / unscored)."""
    n = len(rows["name"])
    preds = {b: np.full(n, np.nan, dtype=np.float32) for b in BASE_CODES}
    fits, fold_counts = [], []
    y13 = rows["Y"][:, 0]
    for fi, fold in enumerate(cfg.folds):
        train, oof = fold_masks(rows, rows["sessions"], fold)
        fold_counts.append(dict(fold_index=fi, train_end=fold[0], oof_start=fold[1], oof_end=fold[2],
                                n_train_rows=int(train.sum()), n_oof_rows=int(oof.sum())))
        if not train.any() or not oof.any():
            log(f"fold {fi}: empty train or OOF — skipped", flush=True)
            continue
        labels = rows["state_labels"]
        state_cols = {"B0": np.zeros(n, dtype=np.int16), "B1": rows["b1"],
                      "B2": b2_state_map(rows["b2"], labels["B2"], train), "B3": rows["b3"]}
        for base, code in BASE_CODES.items():
            st = state_cols[base]
            valid = st >= 0                                   # -1 = state missing => the base abstains
            present = set(np.unique(st[(train | oof) & valid]).tolist())
            states = sorted(labels[base][c] for c in present)   # the base's SORTED state list => state_index
            for k, state in enumerate(states):
                sel = valid & (st == labels[base].index(state))
                tr_idx = np.where(train & sel)[0]
                te_idx = np.where(oof & sel)[0]
                seed = fit_seed(fi, code, k)
                rec = dict(fold_index=fi, base=base, state=str(state), state_index=k, seed=seed,
                           n_train_raw=int(len(tr_idx)), n_oof=int(len(te_idx)))
                if len(tr_idx) == 0:
                    rec.update(n_train_used=0, capped=False, fitted=False, note="no training rows: abstain")
                    fits.append(rec)
                    continue
                tr_idx, capped = cap_rows(tr_idx, cfg.row_cap, seed)
                rec.update(n_train_used=int(len(tr_idx)), capped=bool(capped), fitted=True)
                preds[base][te_idx] = fit_predict(rows["X"][tr_idx], y13[tr_idx], rows["X"][te_idx])
                fits.append(rec)
                log(f"fold {fi} {base}[{state}] train={len(tr_idx)}{' (capped)' if capped else ''} oof={len(te_idx)}",
                    flush=True)
    return preds, fits, fold_counts


# --------------------------------------------------------------------------
# screen: A1 session blocks, episodes, AR(1) ESS, block-t
# --------------------------------------------------------------------------
def session_blocks(rows: dict, pred: np.ndarray, label: np.ndarray, oof_mask: np.ndarray,
                   min_names: int) -> Tuple[Dict[str, float], Dict[str, int], Dict[str, list]]:
    """Per session: Spearman(pred, label) across names at each t=13..25 (>= min_names); block = mean of the 13."""
    ok = oof_mask & np.isfinite(pred) & np.isfinite(label)
    sess, slot = rows["session"][ok], rows["slot"][ok]
    p, y = pred[ok], label[ok]
    order = np.lexsort((slot, sess))
    sess, slot, p, y = sess[order], slot[order], p[order], y[order]
    blocks, n_names, bar_ics = {}, {}, {}
    if len(sess) == 0:
        return blocks, n_names, bar_ics
    bounds = np.flatnonzero(np.diff(sess)) + 1
    for chunk in np.split(np.arange(len(sess)), bounds):
        s = rows["sessions"][sess[chunk[0]]]
        ics, counts = [], []
        for t in SCREEN_SLOTS:
            m = chunk[slot[chunk] == t]
            if len(m) < min_names:
                break
            ic = spearmanr(p[m], y[m]).statistic
            if not np.isfinite(ic):
                break
            ics.append(float(ic)); counts.append(len(m))
        if len(ics) == len(SCREEN_SLOTS):
            blocks[s] = float(np.mean(ics)); n_names[s] = int(min(counts)); bar_ics[s] = [round(x, 6) for x in ics]
    return blocks, n_names, bar_ics


def episodes_of(block_sessions: List[str], sessions: List[str], regime_episode: np.ndarray) -> List[Tuple[str, List[str]]]:
    """Runs of equal regime over the BLOCK index (the census's construction): [(regime, [sessions...]), ...]."""
    sidx = {s: i for i, s in enumerate(sessions)}
    runs, cur, members = [], None, []
    for s in block_sessions:
        r = regime_episode[sidx[s]]
        if r != cur:
            if members:
                runs.append((cur, members))
            cur, members = r, []
        members.append(s)
    if members:
        runs.append((cur, members))
    return runs


def ess_stats(blocks: Dict[str, float], episodes: List[Tuple[str, List[str]]], regime: Optional[str] = None) -> dict:
    """AR(1) ESS on episode-internal pairs; rho1 floored at 0; fail-closed below MIN_PAIRS; block-t on adjusted units."""
    segs = [[blocks[s] for s in mem] for r, mem in episodes if regime is None or r == regime]
    vals = [v for seg in segs for v in seg]
    pairs = [(seg[i], seg[i + 1]) for seg in segs for i in range(len(seg) - 1)]
    out = dict(n_blocks=len(vals), n_episodes=len(segs), pairs=len(pairs),
               mean_block_ic=(round(float(np.mean(vals)), 6) if vals else None),
               sd_block_ic=(round(float(np.std(vals, ddof=1)), 6) if len(vals) > 1 else None),
               rho1_raw=None, rho1_used=None, n_eff_adj=None, block_t=None, estimator=None)
    if len(pairs) >= MIN_PAIRS and len(vals) > 1:
        a = np.asarray(pairs)
        rho_raw = float(np.corrcoef(a[:, 0], a[:, 1])[0, 1])
        rho_raw = rho_raw if np.isfinite(rho_raw) else 0.0
        rho_used = max(rho_raw, 0.0)
        n_eff = len(vals) * (1 - rho_used) / (1 + rho_used)
        sd = float(np.std(vals, ddof=1))
        t = float(np.mean(vals)) / (sd / math.sqrt(n_eff)) if sd > 0 and n_eff > 0 else None
        out.update(rho1_raw=round(rho_raw, 4), rho1_used=round(rho_used, 4), n_eff_adj=round(n_eff, 1),
                   block_t=(round(t, 4) if t is not None else None), estimator="ok")
    else:
        out.update(estimator=f"FAIL_CLOSED(<{MIN_PAIRS} pairs)", n_eff_adj="unestablished")
    return out


def screen_base(rows: dict, pred: np.ndarray, oof_mask: np.ndarray, cfg: RunConfig) -> Tuple[dict, dict]:
    Y = rows["Y"]
    blocks, n_names, bar_ics = session_blocks(rows, pred, Y[:, 0], oof_mask, cfg.min_names)
    bs = sorted(blocks)
    eps = episodes_of(bs, rows["sessions"], rows["regime_episode"])
    overall = ess_stats(blocks, eps)
    per_regime = {r: ess_stats(blocks, eps, r) for r in K5_REGIMES}
    t = overall["block_t"]
    result = dict(horizon=H, overall=overall, per_regime=per_regime,
                  passes_life_bar=bool(t is not None and t >= LIFE_BAR_T),
                  life_bar=f"block-t >= {LIFE_BAR_T} overall @ h={H} on dependence-adjusted units",
                  n_scored_rows=int((oof_mask & np.isfinite(pred)).sum()),
                  secondary_horizons_DIAGNOSTIC_ONLY={})
    for h, col in ((1, 1), (3, 2)):
        b_h, _, _ = session_blocks(rows, pred, Y[:, col], oof_mask, cfg.min_names)
        e_h = episodes_of(sorted(b_h), rows["sessions"], rows["regime_episode"])
        result["secondary_horizons_DIAGNOSTIC_ONLY"][f"h={h}"] = dict(
            note="h=13-trained prediction ranked against the within-session forward %d-bar label; not gating" % h,
            overall=ess_stats(b_h, e_h))
    result["secondary_horizons_DIAGNOSTIC_ONLY"]["h=39"] = "not computed: no within-session 39-bar forward window on the 39-slot grid"
    audit = dict(block_series=blocks, per_session_n_names=n_names, bar_time_ics=bar_ics)
    return result, audit


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime(_TS)


def source_state(repo_root: pathlib.Path, ignore: Sequence[pathlib.Path] = ()) -> dict:
    """`git rev-parse HEAD` + porcelain cleanliness of the harness's own checkout. Entries under `ignore`
    (the untracked bar store, the output directory) do not count as dirt but are listed as ignored."""
    repo_root = pathlib.Path(repo_root)
    try:
        head = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
        porcelain = subprocess.run(["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
                                   capture_output=True, text=True, check=True).stdout.splitlines()
    except (subprocess.CalledProcessError, OSError) as exc:
        return dict(commit=None, clean_tree=None, error=str(exc), ignored=[str(p) for p in ignore])
    ignored = [pathlib.Path(p).resolve() for p in ignore]
    dirty = []
    for line in porcelain:
        rel = line[3:].split(" -> ")[-1].strip().strip('"')
        full = (repo_root / rel).resolve()
        if any(full == ig or ig in full.parents for ig in ignored):
            continue
        dirty.append(line)
    return dict(commit=head, clean_tree=(not dirty), n_dirty=len(dirty), dirty_entries=dirty[:50],
                ignored=[str(p) for p in ignore],
                clean_tree_note="git status --porcelain --untracked-files=all, ignoring the listed paths")


def frozen_block(cfg: RunConfig) -> dict:
    """The full frozen-parameter block written to every report (constants + the run's window/folds)."""
    return dict(h=H, slots=SLOTS, screen_slots=list(SCREEN_SLOTS), dev_window=[cfg.dev_start, cfg.dev_end],
                seed_base=SEED_BASE, seed_formula="20260828 + 1000*fold_index + 100*base_code + state_index",
                xgb_params=XGB_PARAMS, row_cap=cfg.row_cap, base_codes=BASE_CODES,
                min_sector_rows=MIN_SECTOR_ROWS, folds=[list(f) for f in cfg.folds], purge_bars=PURGE_BARS,
                min_names_per_ic=cfg.min_names, min_pairs=MIN_PAIRS, life_bar_t=LIFE_BAR_T,
                secondary_horizons=list(SECONDARY_HORIZONS), features=list(FEATURE_NAMES),
                b1_state_lag_sessions=B1_STATE_LAG_SESSIONS, vz_trailing_sessions=VZ_TRAILING_SESSIONS,
                vz_min_present=VZ_MIN_PRESENT, b3_slow_sessions=B3_SLOW_SESSIONS,
                b3_fast_lag_slots=B3_FAST_LAG_SLOTS, k5_regimes=list(K5_REGIMES), b3_labels=list(B3_LABELS))


def _bind_dev_run(cfg: RunConfig) -> None:
    """A DEV_RUN is only ever executed against the gate bundle's audit, under a live GateAuthorization."""
    if cfg.run_status != "DEV_RUN":
        return
    if cfg.gate is None:
        raise GateNotAuthorized("DEV_RUN without a GateAuthorization — call load_gate_authorization() first")
    if pathlib.Path(cfg.census_audit).resolve() != pathlib.Path(cfg.gate.audit_path).resolve():
        raise GateNotAuthorized(f"DEV_RUN census audit {cfg.census_audit} is not the gate bundle's audit "
                                f"{cfg.gate.audit_path} (the development audit is not authorization)")
    if sha256_file(cfg.census_audit) != cfg.gate.audit_sha256:
        raise GateNotAuthorized("the gate audit changed on disk after authorization")
    if cfg.strategy_config is None or not pathlib.Path(cfg.strategy_config).is_file():
        raise GateNotAuthorized("DEV_RUN needs the pinned strategy config file for the provenance hash")


def run_stage_i1(cfg: RunConfig, log=print) -> dict:
    import xgboost
    started = _utcnow()
    _bind_dev_run(cfg)
    src = source_state(REPO, ignore=[cfg.bar_store, cfg.out_dir])
    kind = "dev" if cfg.run_status == "DEV_RUN" else "smoke"
    run_id = f"i1-{kind}-{started[:10].replace('-', '')}-{(src['commit'] or 'nogit')[:8]}"
    audit_in = load_census_audit(cfg.census_audit)
    sessions = session_list(audit_in, cfg.dev_start, cfg.dev_end)
    log(f"sessions in window: {len(sessions)} ({sessions[0]}..{sessions[-1]})" if sessions else "no sessions", flush=True)
    if not sessions:
        sys.exit("census audit carries no sessions inside the development window")
    rows = build_rows(cfg, audit_in, sessions, log=log)
    log(f"observations: {len(rows['name'])} over {len(rows['names'])} names", flush=True)
    preds, fits, fold_counts = run_bases(rows, cfg, log=log)
    oof_all = np.zeros(len(rows["name"]), dtype=bool)
    for fold in cfg.folds:
        _, oof = fold_masks(rows, sessions, fold)
        oof_all |= oof
    results, audit_out = {}, {"bases": {}, "fits": fits, "fold_row_counts": fold_counts}
    for base in BASE_CODES:
        results[base], audit_out["bases"][base] = screen_base(rows, preds[base], oof_all, cfg)
    s0_res, s0_aud = screen_base(rows, rows["s0"], oof_all, cfg)
    audit_out["bases"]["s0_reference"] = s0_aud
    b0_t = results["B0"]["overall"]["block_t"]
    comparison = {}
    for base in ("B1", "B2", "B3"):
        t = results[base]["overall"]["block_t"]
        comparison[base] = dict(block_t=t, b0_block_t=b0_t, passes=results[base]["passes_life_bar"],
                                beats_b0=(t is not None and b0_t is not None and t > b0_t),
                                b0_unestablished=b0_t is None)
    trigger = any(c["passes"] and c["beats_b0"] for c in comparison.values())
    consumed = rows["consumed_sha256"]
    frozen = frozen_block(cfg)
    ended = _utcnow()
    provenance = dict(
        run_id=run_id, run_status=cfg.run_status,
        source=dict(repo_root=str(REPO), **src),
        invocation=dict(argv=list(sys.argv), cwd=os.getcwd(), python=sys.executable,
                        env={"G2V3_BAR_STORE": os.environ.get("G2V3_BAR_STORE")}),
        timestamps_utc=dict(start=started, end=ended,
                            derivation="logged by this process's own clock (datetime.now(UTC)): start at entry "
                                       "to run_stage_i1, end immediately before the report is written"),
        gate_bundle=(cfg.gate.as_record() if cfg.gate is not None else None),
        inputs=dict(
            census_audit=dict(path=str(cfg.census_audit), sha256=sha256_file(cfg.census_audit)),
            strategy_config=(dict(path=str(cfg.strategy_config), sha256=sha256_file(cfg.strategy_config))
                             if cfg.strategy_config else None),
            sector_map_sha256=sha256_json(cfg.sector_map), sector_etf_map_sha256=sha256_json(cfg.sector_etf_map),
            spy_daily=dict(path=str(cfg.spy_daily), sha256=sha256_file(cfg.spy_daily)),
            bar_store=str(cfg.bar_store)),
        frozen_parameters=dict(frozen, interpretations=list(INTERPRETATIONS)),
        consumed_bar_manifest=dict(count=len(consumed), aggregate_sha256=manifest_aggregate(consumed),
                                   aggregate_method=MANIFEST_METHOD,
                                   per_file="audit consumed_sha256 (hashed from the store at run time)"),
    )
    report = dict(
        stage="GOAL-2v3 Stage I-1", run_status=cfg.run_status, run_id=run_id,
        generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        spec="doc/design/2026-08-27-goal2v3-intraday-granularity.md#stage-i-1",
        versions=dict(python=platform.python_version(), xgboost=xgboost.__version__, numpy=np.__version__,
                      pandas=pd.__version__, scipy=__import__("scipy").__version__),
        frozen=frozen,
        inputs=dict(census_audit=str(cfg.census_audit), bar_store=str(cfg.bar_store), spy_daily=str(cfg.spy_daily),
                    gate_run_id=(cfg.gate.run_id if cfg.gate is not None else None),
                    n_sessions=len(sessions), n_names=len(rows["names"]), n_observations=int(len(rows["name"])),
                    n_oof_observations=int(oof_all.sum()), missing_store_files=rows["missing_files"],
                    sec13_etf_available_by_sector=rows["sec13_available"],
                    store_hash_check="every consumed file hashed at run time == the gate audit's per-file "
                                     "sha256 (fail-closed on mismatch or on files absent from the audit)"),
        fold_row_counts=fold_counts,
        bases=results, s0_reference=s0_res, base_vs_b0=comparison,
        stage_i2_trigger=dict(rule="at least one of B1/B2/B3 passes the life bar AND beats B0's block-t",
                              fired=bool(trigger)),
        interpretations=INTERPRETATIONS,
        provenance=provenance,
    )
    if cfg.run_status != "DEV_RUN":
        report["note"] = "SMOKE run on synthetic data: no development-window evidence; no verdict."
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    (cfg.out_dir / "report.json").write_text(json.dumps(report, indent=1, default=_json_default))
    audit_out["consumed_sha256"] = consumed
    with gzip.open(cfg.out_dir / "g2v3_stage_i1_audit.json.gz", "wt") as fh:
        json.dump(audit_out, fh, default=_json_default)
    return report


# --------------------------------------------------------------------------
# provenance validator: rebuild every hash the report claims from the inputs on disk
# --------------------------------------------------------------------------
_CONSTANT_FROZEN = dict(h=H, slots=SLOTS, screen_slots=list(SCREEN_SLOTS), seed_base=SEED_BASE,
                        xgb_params=XGB_PARAMS, base_codes=BASE_CODES, min_sector_rows=MIN_SECTOR_ROWS,
                        purge_bars=PURGE_BARS, min_pairs=MIN_PAIRS, life_bar_t=LIFE_BAR_T,
                        secondary_horizons=list(SECONDARY_HORIZONS), features=list(FEATURE_NAMES),
                        b1_state_lag_sessions=B1_STATE_LAG_SESSIONS, vz_trailing_sessions=VZ_TRAILING_SESSIONS,
                        vz_min_present=VZ_MIN_PRESENT, b3_slow_sessions=B3_SLOW_SESSIONS,
                        b3_fast_lag_slots=B3_FAST_LAG_SLOTS, k5_regimes=list(K5_REGIMES), b3_labels=list(B3_LABELS))
_DEV_ONLY_FROZEN = dict(dev_window=[DEV_START, DEV_END], row_cap=ROW_CAP, folds=[list(f) for f in FOLDS],
                        min_names_per_ic=MIN_NAMES_PER_IC)


def validate_i1_provenance(report: dict, audit: dict, repo_root: pathlib.Path = None) -> List[str]:
    """Return every disagreement between a Stage I-1 report's `provenance` block and (a) the report itself,
    (b) the audit's consumed-bar hashes, (c) the files on disk it names, (d) this module's frozen constants,
    (e) the gate bundle under `repo_root`. Empty list == the provenance is complete and verifiable."""
    repo_root = pathlib.Path(repo_root if repo_root is not None else REPO)
    problems: List[str] = []
    prov = report.get("provenance")
    if not isinstance(prov, dict):
        return ["report has no provenance block"]
    dev = report.get("run_status") == "DEV_RUN"

    def need(*keys):
        v = _dig(prov, *keys)
        if v is None:
            problems.append(f"provenance.{'.'.join(keys)} missing")
        return v

    # --- identity
    run_id = need("run_id")
    if isinstance(run_id, str):
        if not _RUN_ID.match(run_id):
            problems.append(f"run_id {run_id!r} does not match i1-(dev|smoke)-<UTCdate>-<shortsha>")
        elif run_id.split("-")[1] != ("dev" if dev else "smoke"):
            problems.append(f"run_id {run_id!r} kind disagrees with run_status {report.get('run_status')!r}")
        if report.get("run_id") != run_id:
            problems.append("report.run_id != provenance.run_id")
    if prov.get("run_status") != report.get("run_status"):
        problems.append("provenance.run_status != report.run_status")
    # --- source
    commit = need("source", "commit")
    if not (isinstance(commit, str) and _HEX40.match(commit)):
        problems.append(f"source.commit is not a 40-hex sha: {commit!r}")
    elif isinstance(run_id, str) and _RUN_ID.match(run_id) and not run_id.endswith(commit[:8]):
        problems.append("run_id short sha != source.commit")
    if not isinstance(need("source", "clean_tree"), bool):
        problems.append("source.clean_tree must be a bool")
    # --- invocation + clock
    argv = need("invocation", "argv")
    if not (isinstance(argv, list) and argv):
        problems.append("invocation.argv must be a non-empty list")
    env = need("invocation", "env")
    if not (isinstance(env, dict) and "G2V3_BAR_STORE" in env):
        problems.append("invocation.env must record G2V3_BAR_STORE")
    elif dev and not env.get("G2V3_BAR_STORE"):
        problems.append("DEV_RUN invocation.env.G2V3_BAR_STORE is empty")
    start, end = need("timestamps_utc", "start"), need("timestamps_utc", "end")
    try:
        t0 = _dt.datetime.strptime(start, _TS)
        t1 = _dt.datetime.strptime(end, _TS)
        if t1 < t0:
            problems.append(f"timestamps_utc end {end} precedes start {start}")
        if isinstance(run_id, str) and _RUN_ID.match(run_id) and run_id.split("-")[2] != t0.strftime("%Y%m%d"):
            problems.append("run_id date != timestamps_utc.start date")
    except (TypeError, ValueError):
        problems.append(f"timestamps_utc start/end must be {_TS}: {start!r} / {end!r}")
    # --- gate bundle
    gate = prov.get("gate_bundle")
    if dev and not isinstance(gate, dict):
        problems.append("DEV_RUN provenance has no gate_bundle")
    if isinstance(gate, dict):
        g = ACCEPTED_GATE_BUNDLE
        for key, want in (("run_id", g["run_id"]), ("frozen_source_commit", g["frozen_source_commit"]),
                          ("gate_verdict", g["gate_verdict"]), ("report_sha256", g["report_sha256"]),
                          ("audit_sha256", g["audit_sha256"]),
                          ("input_manifest_aggregate_sha256", g["input_manifest_aggregate_sha256"]),
                          ("input_manifest_count", g["input_manifest_count"])):
            if gate.get(key) != want:
                problems.append(f"gate_bundle.{key} = {gate.get(key)!r} != bound {want!r}")
        bundle = repo_root / g["dir"]
        for key, fname in (("report_sha256", g["report_file"]), ("audit_sha256", g["audit_file"]),
                           ("provenance_sha256", g["provenance_file"])):
            p = bundle / fname
            if not p.is_file():
                problems.append(f"gate bundle file missing under repo_root: {p}")
            elif sha256_file(p) != gate.get(key):
                problems.append(f"gate_bundle.{key} != sha256 of {p.name} on disk")
    # --- inputs on disk
    for key in ("census_audit", "spy_daily"):
        entry = need("inputs", key)
        if isinstance(entry, dict):
            p = pathlib.Path(str(entry.get("path")))
            if not p.is_file():
                problems.append(f"inputs.{key}.path missing on disk: {p}")
            elif sha256_file(p) != entry.get("sha256"):
                problems.append(f"inputs.{key}.sha256 != file on disk")
    sc = _dig(prov, "inputs", "strategy_config")
    if dev and not isinstance(sc, dict):
        problems.append("DEV_RUN provenance has no inputs.strategy_config")
    if isinstance(sc, dict):
        p = pathlib.Path(str(sc.get("path")))
        if not p.is_file():
            problems.append(f"inputs.strategy_config.path missing on disk: {p}")
        else:
            if sha256_file(p) != sc.get("sha256"):
                problems.append("inputs.strategy_config.sha256 != file on disk")
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
                if sha256_json(dict(cfg["sector_map"])) != _dig(prov, "inputs", "sector_map_sha256"):
                    problems.append("inputs.sector_map_sha256 != sector_map rebuilt from the strategy config")
                if sha256_json(dict(cfg["sector_etf_map"])) != _dig(prov, "inputs", "sector_etf_map_sha256"):
                    problems.append("inputs.sector_etf_map_sha256 != sector_etf_map rebuilt from the strategy config")
            except (ValueError, KeyError, TypeError) as exc:
                problems.append(f"strategy config unreadable for the sector-map rebuild ({exc})")
    if dev and str(_dig(prov, "inputs", "census_audit", "path") or "") != str(GATE_AUDIT):
        problems.append(f"DEV_RUN census audit is not the gate bundle's audit {GATE_AUDIT}")
    # --- frozen block: internal consistency + module constants + the 11 interpretations byte-identical
    fp = need("frozen_parameters")
    if isinstance(fp, dict):
        if dict(report.get("frozen") or {}, interpretations=list(INTERPRETATIONS)) != fp:
            problems.append("provenance.frozen_parameters != report.frozen + INTERPRETATIONS")
        for key, want in _CONSTANT_FROZEN.items():
            if fp.get(key) != want:
                problems.append(f"frozen_parameters.{key} = {fp.get(key)!r} != module constant {want!r}")
        if dev:
            for key, want in _DEV_ONLY_FROZEN.items():
                if fp.get(key) != want:
                    problems.append(f"DEV_RUN frozen_parameters.{key} = {fp.get(key)!r} != frozen {want!r}")
        if fp.get("interpretations") != list(INTERPRETATIONS):
            problems.append("frozen_parameters.interpretations are not the frozen INTERPRETATIONS (byte-identical)")
    if report.get("interpretations") != list(INTERPRETATIONS):
        problems.append("report.interpretations != INTERPRETATIONS")
    # --- consumed-bar manifest: rebuilt from the audit, cross-checked against the census audit consumed
    man = need("consumed_bar_manifest")
    consumed = audit.get("consumed_sha256") if isinstance(audit, dict) else None
    if not isinstance(consumed, dict) or not consumed:
        problems.append("audit has no consumed_sha256 map")
    elif isinstance(man, dict):
        if man.get("count") != len(consumed):
            problems.append(f"consumed_bar_manifest.count {man.get('count')} != {len(consumed)} in the audit")
        if man.get("aggregate_sha256") != manifest_aggregate(consumed):
            problems.append("consumed_bar_manifest.aggregate_sha256 != aggregate rebuilt from audit.consumed_sha256")
        census_p = pathlib.Path(str(_dig(prov, "inputs", "census_audit", "path") or ""))
        if census_p.is_file():
            try:
                census_hashes = load_census_audit(census_p).get("bar_store_sha256") or {}
            except (OSError, ValueError):
                census_hashes = {}
            bad = [t for t, h in consumed.items() if census_hashes.get(t) != h]
            if bad:
                problems.append(f"{len(bad)} consumed files are not the census-audited files (e.g. {bad[:5]})")
    return problems


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(str(type(o)))


# --------------------------------------------------------------------------
# synthetic smoke store (shared by the default CLI path and the test)
# --------------------------------------------------------------------------
def _synthetic_store(root: pathlib.Path, n_names: int = 30, n_sessions: int = 40, planted: bool = True,
                     seed: int = 7, drop_eligibility: Optional[Dict[str, List[str]]] = None) -> dict:
    """Tiny bar store + census-shaped audit + SPY daily + sector maps. Returns the paths/maps for _smoke_config.

    planted=True: bar returns mean-revert on the trailing 13-bar return (a reversal signal every base can find);
    planted=False: independent random walks (null).
    """
    rng = np.random.default_rng(seed)
    root = pathlib.Path(root)
    store = root / "bars"; store.mkdir(parents=True, exist_ok=True)
    sessions = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2024-01-02", periods=n_sessions)]
    names = [f"SYN{i:03d}" for i in range(n_names)]
    tickers = names + ["SPY", "XLK", "XLF"]
    et = pd.Timestamp("2024-01-01 09:30", tz="America/New_York")
    hashes = {}
    for tk in tickers:
        frames = []
        lvl = math.log(100.0 + rng.uniform(0, 50))
        for s in sessions:
            e = rng.normal(0, 0.003, SLOTS)
            r = np.zeros(SLOTS)
            for t in range(SLOTS):
                back = r[max(0, t - H):t]
                r[t] = e[t] - (0.9 * back.mean() * min(len(back), H) / H if (planted and len(back)) else 0.0)
            lc = lvl + np.cumsum(r)
            lvl = lc[-1] + rng.normal(0, 0.005)
            close = np.exp(lc)
            opn = np.r_[np.exp(lc[0] - r[0]), close[:-1]]
            hi = np.maximum(opn, close) * (1 + rng.uniform(0, 0.001, SLOTS))
            lo = np.minimum(opn, close) * (1 - rng.uniform(0, 0.001, SLOTS))
            vol = rng.integers(1000, 5000, SLOTS).astype(float)
            base_ts = pd.Timestamp(s + " 09:30", tz="America/New_York")
            ts = [(base_ts + pd.Timedelta(minutes=10 * t)).tz_convert("UTC") for t in range(SLOTS)]
            frames.append(pd.DataFrame(dict(ts=ts, open=opn, high=hi, low=lo, close=close, volume=vol)))
        df = pd.concat(frames, ignore_index=True)
        p = store / f"{tk}.parquet"
        df.to_parquet(p)
        hashes[tk] = sha256_file(p)
    # SPY daily: 320 days of history before the sessions, drifting up with shrinking vol => BULL_CALM at the end
    hist = pd.bdate_range(end=pd.Timestamp(sessions[0]) - pd.Timedelta(days=1), periods=320)
    idx = hist.append(pd.DatetimeIndex(pd.to_datetime(sessions)))
    sig = np.linspace(0.02, 0.002, len(idx))
    daily = 400 * np.exp(np.cumsum(0.001 + rng.normal(0, 1, len(idx)) * sig))
    spy_daily = root / "SPY_1d.parquet"
    pd.DataFrame({"close": daily}, index=pd.Index(idx, name="date")).to_parquet(spy_daily)
    # census-shaped audit: all names eligible on all sessions except the dropped ones
    drop = drop_eligibility or {}
    membership = {s: [n for n in names if s not in drop.get(n, ())] for s in sessions}
    audit = dict(eligible_membership_post_drift=membership, bar_store_sha256=hashes,
                 excluded_names=[], layer1_excluded_name_days={})
    audit_p = root / "audit.json.gz"
    with gzip.open(audit_p, "wt") as fh:
        json.dump(audit, fh)
    third = n_names // 3
    sector_map = {n: "tech" for n in names[:third]}
    sector_map.update({n: "finance" for n in names[third:2 * third]})
    sector_etf_map = {"tech": "XLK", "finance": "XLF", "healthcare": "XLV"}   # XLV absent on purpose
    strategy_config = root / "strategy_config.json"
    strategy_config.write_text(json.dumps(dict(sector_map=sector_map, sector_etf_map=sector_etf_map), indent=1))
    return dict(bar_store=store, census_audit=audit_p, spy_daily=spy_daily, sector_map=sector_map,
                sector_etf_map=sector_etf_map, sessions=sessions, names=names, strategy_config=strategy_config)


def _smoke_folds(sessions: List[str]) -> Tuple[Tuple[str, str, str], ...]:
    n = len(sessions)
    a, b = n // 2, (3 * n) // 4
    return ((sessions[a - 1], sessions[a], sessions[b - 1]), (sessions[b - 1], sessions[b], sessions[-1]))


def run_smoke(out_dir: pathlib.Path, planted: bool = True, log=print) -> dict:
    syn = _synthetic_store(out_dir / "synthetic", planted=planted)
    cfg = _smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                        syn["sector_etf_map"], out_dir / "out", _smoke_folds(syn["sessions"]), min_names=20,
                        dev_start=syn["sessions"][0], dev_end=syn["sessions"][-1],
                        strategy_config=syn["strategy_config"])
    return run_stage_i1(cfg, log=log)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dev-run", action="store_true",
                    help="run on the REAL development bar store (G2V3_BAR_STORE); refuses (exit 2) unless the "
                         "Stage I-0 GATE_RUN bundle verifies against ACCEPTED_GATE_BUNDLE")
    ap.add_argument("--smoke-out", default=None, help="synthetic smoke output dir (default: a temp dir)")
    args = ap.parse_args(argv)
    if args.dev_run:
        try:
            auth = load_gate_authorization(REPO)          # FIRST: nothing else happens without it
            print(f"gate authorization: {auth.run_id} @ {auth.frozen_source_commit[:8]} verdict={auth.gate_verdict} "
                  f"report={auth.report_sha256[:12]}.. audit={auth.audit_sha256[:12]}..", flush=True)
            cfg = dev_run_config(auth)
            report = run_stage_i1(cfg)
        except GateNotAuthorized as exc:
            print(f"REFUSED --dev-run (fail closed): {exc}", file=sys.stderr, flush=True)
            return 2
    else:
        out = pathlib.Path(args.smoke_out or tempfile.mkdtemp(prefix="g2v3_i1_smoke_"))
        print(f"synthetic smoke -> {out}", flush=True)
        report = run_smoke(out)
    summary = {b: dict(block_t=r["overall"]["block_t"], passes=r["passes_life_bar"]) for b, r in report["bases"].items()}
    print(json.dumps(dict(run_status=report["run_status"], run_id=report["run_id"],
                          xgboost=report["versions"]["xgboost"], bases=summary,
                          s0_block_t=report["s0_reference"]["overall"]["block_t"],
                          stage_i2_trigger=report["stage_i2_trigger"]["fired"],
                          consumed_bar_manifest=report["provenance"]["consumed_bar_manifest"]["aggregate_sha256"]),
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
