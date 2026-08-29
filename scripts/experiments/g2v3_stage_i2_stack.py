"""GOAL-2v3 Stage I-2 harness — the stacked meta-learner over the I-1 bases, AS PREREGISTERED.

Implements, literally, doc/design/2026-08-29-goal2v3-stage-i2-prereg.md (merged #1089, declared
2026-08-29 before any I-2 fit) on top of the Stage I-1 harness scripts/experiments/g2v3_stage_i1_bases.py
(#1084), which this module IMPORTS and reuses — constants, feature builder, folds/purge/row cap, base
fitting, session blocks / episodes / AR(1) ESS / block-t, store-manifest and gate-authorization guards,
provenance helpers. Nothing of I-1 is re-implemented here; every frozen I-2 number lives in a module-level
constant traceable to a prereg section so a reviewer (and tests/test_g2v3_stage_i2_*.py) can check it
against the spec text without reading the code paths.

Two entry points, as in I-1:
  python scripts/experiments/g2v3_stage_i2_stack.py            # synthetic smoke (default)
  python scripts/experiments/g2v3_stage_i2_stack.py --dev-run  # the real development run
The `--dev-run` path FAILS CLOSED (exit code 2) unless, in this order: the Stage I-0 GATE_RUN bundle
still verifies (I-1's `load_gate_authorization`); the Stage I-1 DEV_RUN bundle on disk agrees with the
frozen ACCEPTED_I1_BUNDLE block (prereg §1 binding: run_id, source commit, report + audit sha256,
consumed-bar aggregate, run_status DEV_RUN, all four bases surviving, the I-1 harness byte-identical to
the blob at that commit); the source tree is clean apart from the bar store and the output root; the
output bundle `<out_root>/<run_id>/` does not exist; the bar store is the COMPLETE audited store (I-1's
`check_store_manifest`, strict); the bars consumed by the re-fit aggregate to the I-1 bundle's manifest;
and the base re-fit reproduces the I-1 overall block-t to 4 decimals with equal n_blocks for every base
(prereg §1.1 + interpretation 5) BEFORE any meta-learner is fitted.

Prereg §2 (nested OOF), §3 (M_xgb, 11 meta-features, M0 diagnostic), §4 (P1/P2/P3 on the common sample,
outcome register) are implemented in `meta_fold_layout`, `meta_features`, `fit_meta`, `m0_zsum`,
`common_sample`, `pass_bar`, `outcome_of`. The six prereg interpretations are copied verbatim into every
report; the harness-level readings the prereg text still left open are numbered after them
(HARNESS_INTERPRETATIONS) and declared BEFORE the dev run.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import datetime as _dt
import gzip
import hashlib
import importlib.util
import json
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

# --------------------------------------------------------------------------
# the Stage I-1 harness is IMPORTED (reused), never copied
# --------------------------------------------------------------------------
_I1_PATH = pathlib.Path(__file__).resolve().with_name("g2v3_stage_i1_bases.py")


def _load_i1():
    spec = importlib.util.spec_from_file_location("g2v3_stage_i1_bases__i2", _I1_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod            # dataclasses + postponed annotations need the module registered
    spec.loader.exec_module(mod)
    return mod


I1 = _load_i1()
H, SLOTS, SCREEN_SLOTS, FOLDS = I1.H, I1.SLOTS, I1.SCREEN_SLOTS, I1.FOLDS
K5_REGIMES, BASE_CODES = I1.K5_REGIMES, I1.BASE_CODES
MIN_NAMES_PER_IC, MIN_PAIRS, LIFE_BAR_T = I1.MIN_NAMES_PER_IC, I1.MIN_PAIRS, I1.LIFE_BAR_T
B1_STATE_LAG_SESSIONS, B3_SLOW_SESSIONS = I1.B1_STATE_LAG_SESSIONS, I1.B3_SLOW_SESSIONS
ACCEPTED_GATE_BUNDLE, GATE_AUDIT = I1.ACCEPTED_GATE_BUNDLE, I1.GATE_AUDIT
DevRunRefused, GateNotAuthorized, StoreNotAudited = I1.DevRunRefused, I1.GateNotAuthorized, I1.StoreNotAudited
sha256_file, sha256_json, manifest_aggregate, _dig = I1.sha256_file, I1.sha256_json, I1.manifest_aggregate, I1._dig
_json_default, MANIFEST_METHOD, _HEX40, _HEX64, _TS, _RUN_TS = (I1._json_default, I1.MANIFEST_METHOD, I1._HEX40,
                                                                 I1._HEX64, I1._TS, I1._RUN_TS)
REFUSE_LIST_N = I1.REFUSE_LIST_N

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "doc/research/data/2026-08-29-g2v3-i2"
SPEC = "doc/design/2026-08-29-goal2v3-stage-i2-prereg.md"

# --------------------------------------------------------------------------
# FROZEN CONSTANTS (the preregistration; do not edit — a change is a new attempt)
# --------------------------------------------------------------------------
# §1 binding: the Stage I-1 DEV_RUN bundle this harness re-fits against (#1088, merged). Every value below
# is copied from that bundle's report.json / provenance block, or is the sha256 of the file on disk.
# `--dev-run` refuses unless the bundle on disk agrees with EVERY field AND the source commit is resolvable
# in this repository with the I-1 harness blob hashing to I1_HARNESS_SHA256 (the module imported above).
ACCEPTED_I1_BUNDLE = dict(
    dir="doc/research/data/2026-08-29-g2v3-i1/i1-dev-20260829T113813Z-666484a7",
    report_file="report.json",
    audit_file="g2v3_stage_i1_audit.json.gz",
    run_id="i1-dev-20260829T113813Z-666484a7",
    source_commit="666484a7ab37dc9f88dd5692f8d9e90f3aab9332",
    run_status="DEV_RUN",
    stage="GOAL-2v3 Stage I-1",
    report_sha256="666d9c6a9a2286af4215399aebbd07a2fda8efafc6b5440d8d39ea6b9e1e1542",
    audit_sha256="d124d8f2a8766edf7d4a6f767206444467f05fa3bb8dec1818a76b01b2cd3082",
    consumed_bar_aggregate_sha256="4addcbe25f164a57afc0ea9fb0fd4e8e368a17fc292e2fe62b80fff5219d3883",
    consumed_bar_count=1508,
    gate_run_id="i0-gate-20260829-f3d5bf7b",                 # the I-0 gate the I-1 run was authorized by
    stage_i2_trigger_fired=True,                             # the reason I-2 exists at all
    n_observations=10487004,
    n_oof_observations=7097590,
    s0_block_t=4.1861,                                       # §0: the naive reversal reference, overall
    s0_n_blocks=622,
)
I1_HARNESS_PATH = "scripts/experiments/g2v3_stage_i1_bases.py"
# sha256 of the I-1 harness blob at ACCEPTED_I1_BUNDLE.source_commit == the file this module imports
# [VERIFIED 2026-08-29 — git show 666484a7:scripts/experiments/g2v3_stage_i1_bases.py | shasum -a 256]
I1_HARNESS_SHA256 = "13c31d1266e6753bbf2890862fd8afe66081d7c351746177360d770a22775e20"

# §1.1 + interpretation 5: the determinism guard — the re-fit must reproduce these to 4 dp with equal n_blocks
EXPECTED_I1_BLOCK_T = {"B0": 3.5042, "B1": 3.1837, "B2": 3.5915, "B3": 3.2394}
EXPECTED_I1_N_BLOCKS = {"B0": 622, "B1": 511, "B2": 622, "B3": 619}
DETERMINISM_DECIMALS = 4
# interpretation 1: "surviving bases" = every base whose I-1 passes_life_bar is true; all four survived
SURVIVING_BASES = ("B0", "B1", "B2", "B3")

# §2 nested out-of-fold discipline: meta-fold Mk trains on the base-OOF halves of FOLDS[0..k-1] and scores
# FOLDS[k]'s OOF half; 2022H1 (FOLDS[0]) is never meta-scored. The table is DERIVED from I-1's FOLDS so the
# two harnesses cannot disagree; tests compare it to the prereg's table literally.
META_PURGE_BARS = I1.PURGE_BARS                              # 13-bar purge at every meta train/OOF boundary


def meta_fold_layout(folds: Sequence[Tuple[str, str, str]]) -> Tuple[dict, ...]:
    """Mk = train on the OOF halves of folds[0..k-1], score folds[k]'s OOF half, for k = 1..len(folds)-1."""
    folds = [tuple(f) for f in folds]
    out = []
    for k in range(1, len(folds)):
        out.append(dict(name=f"M{k}", meta_fold=k, train_base_folds=list(range(k)),
                        train_start=folds[0][1], train_end=folds[k - 1][2],
                        oof_base_fold=k, oof_start=folds[k][1], oof_end=folds[k][2]))
    return tuple(out)


META_FOLDS = meta_fold_layout(FOLDS)
META_OOF_PERIOD = (META_FOLDS[0]["oof_start"], META_FOLDS[-1]["oof_end"])      # 2022-07-01..2024-06-30

# §3 the meta-learner
META_SEED_BASE = 20260829
META_XGB_PARAMS = dict(objective="reg:squarederror", max_depth=2, n_estimators=200, learning_rate=0.05,
                       subsample=0.8, colsample_bytree=1.0, min_child_weight=50, tree_method="hist",
                       random_state=20260829, n_jobs=8)
META_ROW_CAP = 4_000_000                                     # per meta-fit, sampled WITHOUT replacement
META_FEATURES = ("p_B0", "p_B1", "p_B2", "p_B3", "n_abstain",
                 "regime_BEAR", "regime_BULL_CALM", "regime_BULL_VOLATILE", "regime_CHOPPY",
                 "b3_slow_sign", "slot")                     # 11; s0 is NOT a feature; no sector one-hot
META_LABEL_HORIZON = H                                       # the I-1 h=13 forward log return, same bar-times
SECONDARY_HORIZONS = (1, 3)                                  # interpretation 6: DIAGNOSTIC ONLY for M_xgb

# §4 pass bar (harder than the parent design's minimum): strict inequalities on point estimates, no margin
P1_LIFE_BAR_T = LIFE_BAR_T                                   # M_xgb block-t >= 1.0 overall @ h=13
P1_BEAR_MIN_N_EFF_ADJ = 30.0                                 # BEAR n_eff_adj >= 30 re-verified on M_xgb's own OOF IC
SERIES = ("M_xgb", "M0", "B0", "B1", "B2", "B3", "s0")       # every series scored on the common sample

# §4.4 outcome register, copied verbatim (condition, consequence) — the report quotes the row it lands on
OUTCOME_REGISTER = {
    "PASS": dict(
        condition="P1 ∧ P2 ∧ P3",
        consequence=("graduate: write the confirmatory prereg against the SEALED window 2024-07-01..2026-06-30 "
                     "(its own PR; the window stays untouched until that prereg is merged)")),
    "FAIL-A": dict(
        condition="P1 ∧ P2 ∧ ¬P3",
        consequence=("stacking works but nothing in this line beats −r13 at h=13; record as a failed attempt; "
                     "line PAUSES for an operator decision (candidates for that decision, not for this run: "
                     "promote s₀ itself to a confirmatory prereg, or close the line)")),
    "FAIL-B": dict(
        condition="¬(P1 ∧ P2)",
        consequence="record as a failed attempt; line pauses for an operator decision"),
    "REFUSED": dict(
        condition="any fail-closed guard (§1 binding, determinism, dirty tree, store manifest)",
        consequence="no result; defect fixed, new attempt"),
}

# §5 the prereg's interpretations, copied verbatim
PREREG_INTERPRETATIONS = [
    "\"Surviving bases\" = every base whose I-1 `passes_life_bar` is true; all four survived, so all four enter "
    "the stack.",
    "Base abstain rows (I-1 interpretation 8) become NaN meta-features, never imputed; `n_abstain` carries the "
    "count; the common-sample comparison excludes rows where *any* series lacks a prediction.",
    "Sector code for the slow state = the B2 post-fold mapping of the fold in which the row is OOF (the mapping "
    "the base actually used).",
    "M0's per-row z-scoring uses the cross-section of names present at that session×slot; a row with fewer than "
    "`MIN_NAMES_PER_IC` names in its cross-section has no M0 value (and is therefore excluded from the common "
    "sample for M0's diagnostic line only).",
    "Determinism guard tolerance: block-t equal to 4 decimals and n_blocks equal; any drift beyond that refuses "
    "the run (XGBoost `hist` with fixed seeds and single-process fitting is deterministic on one machine; a "
    "cross-machine rerun is a new attempt).",
    "Secondary horizons h=1, h=3 are reported for M_xgb exactly as in I-1 — diagnostic only, never gating.",
]
# Harness-level readings of prereg text that was still open, declared BEFORE the dev run (numbered after §5's six)
HARNESS_INTERPRETATIONS = [
    "[harness 7] `meta_fold` in the seed formula 20260829 + 1000·meta_fold is the M-number (M1 -> 1 ... M4 -> 4): "
    "seeds 20261829, 20262829, 20263829, 20264829; META_XGB_PARAMS.random_state stays 20260829 for every meta-fit "
    "(the seed formula governs the row-cap subsample, as in I-1).",
    "[harness 8] The determinism guard additionally requires: the s0 reference to reproduce the I-1 bundle "
    "(block-t 4.1861, n_blocks 622 — no fit is involved, so a mismatch there is a row-set defect, not fit "
    "non-determinism, and still REFUSES); the bars consumed by the re-fit to aggregate to the I-1 bundle's "
    "consumed-bar manifest (checked after the store is read, before any fit); and the imported I-1 harness "
    "to be byte-identical to the blob at the bundle's source commit (I1_HARNESS_SHA256).",
    "[harness 9] Regime one-hot: a row whose prior-close K5 regime is undefined (I-1 code -1; only possible before "
    "200 SPY sessions of history, never inside the development window) gets all four indicators 0; "
    "`b3_slow_sign` NaN (fewer than 61 daily closes strictly before D) is passed to XGBoost as missing. Both "
    "counts are reported.",
    "[harness 10] Meta-training rows = every base-OOF row of the training halves (the h=13 label always exists by "
    "the A1 existence rule; meta-features may be NaN); no row is dropped for abstains. The 13-bar purge is "
    "applied literally through the I-1 machinery (`apply_purge`) and is inert on the A1 grid.",
    "[harness 11] M0: for each base, z = (p - mean) / sd over that base's FINITE predictions among the rows "
    "present at the session×slot; a base with fewer than 2 finite values or zero spread contributes nothing to "
    "that cross-section; M0 = the plain sum of the available z's (unweighted, not divided by their count). The "
    "MIN_NAMES_PER_IC cross-section minimum counts the rows present, and a row with no available z has no M0.",
    "[harness 12] P1 (life bar AND the BEAR n_eff_adj >= 30 re-check) is evaluated on the common sample — the "
    "identical row set P2/P3 use (§4 'all series ... on the identical meta-OOF row set'); M_xgb on its full "
    "meta-OOF rows is reported beside it, never gating. A series whose block-t is unestablished (the fail-closed "
    "AR(1) estimator) fails the corresponding P; a BEAR n_eff_adj of 'unestablished' fails P1.",
    "[harness 13] The sector code of §1.2 is carried in the audit as the per-fold list of post-fold B2 OOF states "
    "from the re-fit (the mapping B2 actually used); it enters the stack only through p_B2 (§3).",
    "[harness 14] The excluded fraction is reported over the meta-OOF rows where M_xgb has a prediction (every "
    "meta-OOF row: XGBoost scores NaN features natively), attributed per base by its abstain count; the M0-only "
    "extra exclusion is reported separately.",
]
INTERPRETATIONS = list(PREREG_INTERPRETATIONS) + list(HARNESS_INTERPRETATIONS)

_RUN_ID = re.compile(r"^i2-(dev|smoke)-(\d{8}T\d{6}Z)-([0-9a-f]{8}|nogit)$")


class I1NotBound(DevRunRefused):
    """The Stage I-1 bundle is missing, tampered, not DEV_RUN, or not the bundle this harness is bound to."""


class DeterminismRefused(DevRunRefused):
    """The base re-fit did not reproduce the I-1 bundle (§1.1 + interpretation 5): a defect, not a result."""


# --------------------------------------------------------------------------
# §1 binding: the Stage I-1 bundle
# --------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class I1Binding:
    """What `load_i1_binding` hands to --dev-run: the verified identity of the I-1 bundle."""
    bundle_dir: pathlib.Path
    report_path: pathlib.Path
    audit_path: pathlib.Path
    run_id: str
    source_commit: str
    report_sha256: str
    audit_sha256: str
    consumed_bar_aggregate_sha256: str
    consumed_bar_count: int
    harness_sha256: str
    block_t: Dict[str, float]
    n_blocks: Dict[str, int]
    surviving_bases: Tuple[str, ...]

    def as_record(self) -> dict:
        return dict(dir=str(self.bundle_dir), run_id=self.run_id, source_commit=self.source_commit,
                    report_sha256=self.report_sha256, audit_sha256=self.audit_sha256,
                    consumed_bar_aggregate_sha256=self.consumed_bar_aggregate_sha256,
                    consumed_bar_count=self.consumed_bar_count, harness_sha256=self.harness_sha256,
                    expected_block_t=dict(self.block_t), expected_n_blocks=dict(self.n_blocks),
                    surviving_bases=list(self.surviving_bases))


def _verify_i1_bundle_files(repo_root: pathlib.Path) -> I1Binding:
    """Every FILE-level check of the I-1 bundle against ACCEPTED_I1_BUNDLE (no git). Raises I1NotBound with the
    first disagreement. `load_i1_binding` adds the git binding on top."""
    b = ACCEPTED_I1_BUNDLE
    repo_root = pathlib.Path(repo_root)
    bundle = repo_root / b["dir"]
    report_p, audit_p = bundle / b["report_file"], bundle / b["audit_file"]

    def refuse(why: str):
        raise I1NotBound(f"Stage I-1 bundle {b['dir']}: {why}")

    if not bundle.is_dir():
        refuse("bundle directory missing")
    for p in (report_p, audit_p):
        if not p.is_file():
            refuse(f"{p.name} missing")
    # the files on disk against the constants FIRST (the report's own claims are not trusted)
    report_sha = sha256_file(report_p)
    if report_sha != b["report_sha256"]:
        refuse(f"{report_p.name} sha256 on disk {report_sha[:12]}.. != bound {b['report_sha256'][:12]}.. (tampered)")
    audit_sha = sha256_file(audit_p)
    if audit_sha != b["audit_sha256"]:
        refuse(f"{audit_p.name} sha256 on disk {audit_sha[:12]}.. != bound {b['audit_sha256'][:12]}.. (tampered)")
    try:
        report = json.loads(report_p.read_text(encoding="utf-8"))
    except ValueError as exc:
        refuse(f"{report_p.name} unparseable ({exc})")
    if not isinstance(report, dict):
        refuse(f"{report_p.name} is not a JSON object")
    if report.get("run_status") != b["run_status"]:
        refuse(f"report run_status {report.get('run_status')!r} != {b['run_status']!r} "
               f"(a SMOKE / DEVELOPMENT_ONLY report is not the I-1 development run)")
    expected = {
        "stage": (report.get("stage"), b["stage"]),
        "run_id": (report.get("run_id"), b["run_id"]),
        "provenance.run_id": (_dig(report, "provenance", "run_id"), b["run_id"]),
        "provenance.run_status": (_dig(report, "provenance", "run_status"), b["run_status"]),
        "provenance.source.commit": (_dig(report, "provenance", "source", "commit"), b["source_commit"]),
        "provenance.source.clean_tree": (_dig(report, "provenance", "source", "clean_tree"), True),
        "provenance.gate_bundle.run_id": (_dig(report, "provenance", "gate_bundle", "run_id"), b["gate_run_id"]),
        "provenance.gate_bundle.frozen_source_commit": (
            _dig(report, "provenance", "gate_bundle", "frozen_source_commit"),
            ACCEPTED_GATE_BUNDLE["frozen_source_commit"]),
        "provenance.consumed_bar_manifest.aggregate_sha256": (
            _dig(report, "provenance", "consumed_bar_manifest", "aggregate_sha256"), b["consumed_bar_aggregate_sha256"]),
        "provenance.consumed_bar_manifest.count": (
            _dig(report, "provenance", "consumed_bar_manifest", "count"), b["consumed_bar_count"]),
        "stage_i2_trigger.fired": (_dig(report, "stage_i2_trigger", "fired"), b["stage_i2_trigger_fired"]),
        "inputs.n_observations": (_dig(report, "inputs", "n_observations"), b["n_observations"]),
        "inputs.n_oof_observations": (_dig(report, "inputs", "n_oof_observations"), b["n_oof_observations"]),
        "s0_reference.overall.block_t": (_dig(report, "s0_reference", "overall", "block_t"), b["s0_block_t"]),
        "s0_reference.overall.n_blocks": (_dig(report, "s0_reference", "overall", "n_blocks"), b["s0_n_blocks"]),
        "frozen.folds": (_dig(report, "frozen", "folds"), [list(f) for f in FOLDS]),
        "frozen.xgb_params": (_dig(report, "frozen", "xgb_params"), I1.XGB_PARAMS),
        "frozen.row_cap": (_dig(report, "frozen", "row_cap"), I1.ROW_CAP),
        "frozen.min_names_per_ic": (_dig(report, "frozen", "min_names_per_ic"), MIN_NAMES_PER_IC),
    }
    for key, (got, want) in expected.items():
        if got != want:
            refuse(f"report {key} = {got!r}, this harness is bound to {want!r}")
    bases = report.get("bases")
    if not isinstance(bases, dict) or set(bases) != set(BASE_CODES):
        refuse("report carries no bases B0..B3")
    surviving = tuple(bb for bb in BASE_CODES if bases[bb].get("passes_life_bar") is True)
    if surviving != SURVIVING_BASES:
        refuse(f"surviving bases {surviving} != bound {SURVIVING_BASES} (interpretation 1)")
    for bb in BASE_CODES:
        t, n = _dig(bases, bb, "overall", "block_t"), _dig(bases, bb, "overall", "n_blocks")
        if t != EXPECTED_I1_BLOCK_T[bb] or n != EXPECTED_I1_N_BLOCKS[bb]:
            refuse(f"report bases.{bb}.overall block_t/n_blocks = {t!r}/{n!r}, bound "
                   f"{EXPECTED_I1_BLOCK_T[bb]!r}/{EXPECTED_I1_N_BLOCKS[bb]!r}")
    try:
        with gzip.open(audit_p, "rt", encoding="utf-8") as fh:
            audit = json.load(fh)
    except (OSError, ValueError) as exc:
        refuse(f"{audit_p.name} unreadable ({exc})")
    consumed = audit.get("consumed_sha256") if isinstance(audit, dict) else None
    if not isinstance(consumed, dict) or not consumed:
        refuse(f"{audit_p.name} carries no consumed_sha256 map")
    agg = manifest_aggregate(consumed)
    if agg != b["consumed_bar_aggregate_sha256"] or len(consumed) != b["consumed_bar_count"]:
        refuse(f"consumed-bar aggregate recomputed from the audit = {agg[:12]}.. over {len(consumed)} files, bound "
               f"{b['consumed_bar_aggregate_sha256'][:12]}.. over {b['consumed_bar_count']}")
    harness_p = repo_root / I1_HARNESS_PATH
    if not harness_p.is_file():
        refuse(f"{I1_HARNESS_PATH} missing from the checkout")
    hsha = sha256_file(harness_p)
    if hsha != I1_HARNESS_SHA256:
        refuse(f"{I1_HARNESS_PATH} on disk hashes to {hsha[:12]}.., bound {I1_HARNESS_SHA256[:12]}.. (the re-fit "
               f"would not be the I-1 code that produced the bundle)")
    return I1Binding(bundle_dir=bundle, report_path=report_p, audit_path=audit_p, run_id=b["run_id"],
                     source_commit=b["source_commit"], report_sha256=report_sha, audit_sha256=audit_sha,
                     consumed_bar_aggregate_sha256=agg, consumed_bar_count=len(consumed), harness_sha256=hsha,
                     block_t=dict(EXPECTED_I1_BLOCK_T), n_blocks=dict(EXPECTED_I1_N_BLOCKS),
                     surviving_bases=surviving)


def load_i1_binding(repo_root: pathlib.Path = None) -> I1Binding:
    """FAIL-CLOSED binding for --dev-run. Returns an I1Binding only when the bundle under `repo_root` passes
    every file check AND the source commit is resolvable in that repository AND the I-1 harness blob at that
    commit hashes to I1_HARNESS_SHA256. Anything else raises I1NotBound with the specific reason."""
    repo_root = pathlib.Path(repo_root if repo_root is not None else REPO)
    binding = _verify_i1_bundle_files(repo_root)
    commit = ACCEPTED_I1_BUNDLE["source_commit"]
    try:
        r = I1._git(repo_root, "cat-file", "-e", commit + "^{commit}")
    except OSError as exc:
        raise I1NotBound(f"cannot run git in {repo_root} to verify the I-1 source commit ({exc})")
    if r.returncode != 0:
        raise I1NotBound(f"I-1 source commit {commit[:8]} is not resolvable in {repo_root} "
                         f"(a bundle copy outside the reviewed repository is not a binding)")
    blob = I1._git(repo_root, "show", f"{commit}:{I1_HARNESS_PATH}")
    if blob.returncode != 0:
        raise I1NotBound(f"{I1_HARNESS_PATH} does not exist at {commit[:8]}")
    got = hashlib.sha256(blob.stdout).hexdigest()
    if got != I1_HARNESS_SHA256:
        raise I1NotBound(f"{I1_HARNESS_PATH} at {commit[:8]} hashes to {got[:12]}.., bound {I1_HARNESS_SHA256[:12]}..")
    return binding


# --------------------------------------------------------------------------
# run configuration
# --------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class I2Config:
    base: I1.RunConfig                       # the I-1 configuration the re-fit runs under (frozen defaults for DEV_RUN)
    out_dir: pathlib.Path
    run_status: str                          # "DEV_RUN" | "SMOKE"
    i1: Optional[I1Binding] = None           # REQUIRED for DEV_RUN
    expected_block_t: Optional[Dict[str, float]] = None      # determinism guard targets (DEV_RUN: the constants)
    expected_n_blocks: Optional[Dict[str, int]] = None
    expected_s0: Optional[Tuple[float, int]] = None
    expected_consumed_aggregate: Optional[str] = None
    meta_row_cap: int = META_ROW_CAP

    @property
    def meta_folds(self) -> Tuple[dict, ...]:
        return meta_fold_layout(self.base.folds)


def dev_run_config(auth: I1.GateAuthorization, i1: I1Binding) -> I2Config:
    """The ONLY way the --dev-run path builds its configuration: I-1's `dev_run_config` (frozen constants + the
    gate authorization) + the verified I-1 binding + the frozen determinism targets."""
    if not isinstance(i1, I1Binding):
        raise I1NotBound("dev_run_config needs the I1Binding returned by load_i1_binding()")
    base = I1.dev_run_config(auth)
    return I2Config(base=base, out_dir=OUT_DIR, run_status="DEV_RUN", i1=i1,
                    expected_block_t=dict(EXPECTED_I1_BLOCK_T), expected_n_blocks=dict(EXPECTED_I1_N_BLOCKS),
                    expected_s0=(ACCEPTED_I1_BUNDLE["s0_block_t"], ACCEPTED_I1_BUNDLE["s0_n_blocks"]),
                    expected_consumed_aggregate=ACCEPTED_I1_BUNDLE["consumed_bar_aggregate_sha256"])


def _smoke_config(base: I1.RunConfig, out_dir, expected_block_t=None, expected_n_blocks=None, expected_s0=None,
                  expected_consumed_aggregate=None, i1=None) -> I2Config:
    """PRIVATE smoke hook: the only entry that accepts tiny folds / guard-target overrides. Never used by --dev-run."""
    return I2Config(base=base, out_dir=pathlib.Path(out_dir), run_status="SMOKE", i1=i1,
                    expected_block_t=expected_block_t, expected_n_blocks=expected_n_blocks, expected_s0=expected_s0,
                    expected_consumed_aggregate=expected_consumed_aggregate)


# --------------------------------------------------------------------------
# §1.1 determinism guard (pure; runs BEFORE any meta fit)
# --------------------------------------------------------------------------
def determinism_guard(base_results: Dict[str, dict], expected_t: Dict[str, float], expected_n: Dict[str, int],
                      s0_result: Optional[dict] = None, expected_s0: Optional[Tuple[float, int]] = None,
                      decimals: int = DETERMINISM_DECIMALS) -> dict:
    """Compare every base's overall block-t (rounded to `decimals`) and n_blocks with the I-1 bundle's. Returns the
    per-base record; raises DeterminismRefused on the first mismatch (a defect, not a result)."""
    record, bad = {}, []
    targets = [(bb, base_results[bb]["overall"], expected_t[bb], expected_n[bb]) for bb in expected_t]
    if s0_result is not None and expected_s0 is not None:
        targets.append(("s0", s0_result["overall"], expected_s0[0], expected_s0[1]))
    for key, overall, want_t, want_n in targets:
        got_t, got_n = overall.get("block_t"), overall.get("n_blocks")
        t_ok = isinstance(got_t, (int, float)) and round(float(got_t), decimals) == round(float(want_t), decimals)
        n_ok = got_n == want_n
        record[key] = dict(expected_block_t=want_t, observed_block_t=got_t, expected_n_blocks=want_n,
                           observed_n_blocks=got_n, match=bool(t_ok and n_ok))
        if not (t_ok and n_ok):
            bad.append(f"{key}: block_t {got_t!r} vs {want_t!r} @ {decimals} dp, n_blocks {got_n!r} vs {want_n!r}")
    if bad:
        raise DeterminismRefused("base re-fit does not reproduce the I-1 bundle — " + "; ".join(bad) +
                                 " (§1.1: a determinism defect, not a result; no meta-learner was fitted)")
    return dict(status="PASS", tolerance=f"block-t equal to {decimals} decimals and n_blocks equal", per_series=record)


# --------------------------------------------------------------------------
# §3 meta-features (11) + M_xgb
# --------------------------------------------------------------------------
def meta_seed(meta_fold: int) -> int:
    return META_SEED_BASE + 1000 * int(meta_fold)


def meta_features(rows: dict, preds: Dict[str, np.ndarray], b3_slow: np.ndarray) -> Tuple[np.ndarray, dict]:
    """(n, 11) float32 in META_FEATURES order. p_B* = raw base OOF prediction (NaN where the base abstained or the
    row is not OOF); n_abstain = count of NaN among p_B0..p_B3; regime one-hot from the prior-close K5 regime
    (I-1 `b1` code; -1 => all zeros); b3_slow_sign in {-1, +1} (NaN passed as missing); slot."""
    n = len(rows["name"])
    P = np.stack([preds[bb].astype(np.float32) for bb in BASE_CODES], axis=1)
    n_abstain = np.isnan(P).sum(axis=1).astype(np.float32)
    b1 = rows["b1"].astype(np.int64)
    onehot = np.zeros((n, len(K5_REGIMES)), dtype=np.float32)
    ok = b1 >= 0
    onehot[np.where(ok)[0], b1[ok]] = 1.0
    slow = b3_slow[rows["session"]].astype(np.float32)
    slot = rows["slot"].astype(np.float32)
    X = np.concatenate([P, n_abstain[:, None], onehot, slow[:, None], slot[:, None]], axis=1)
    assert X.shape[1] == len(META_FEATURES)
    diag = dict(regime_undefined_rows=int((~ok).sum()), b3_slow_missing_rows=int(np.isnan(slow).sum()))
    return X, diag


def fit_meta(X_tr: np.ndarray, y_tr: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    import xgboost as xgb
    model = xgb.XGBRegressor(**META_XGB_PARAMS)
    model.fit(X_tr, y_tr)
    return model.predict(X_te) if len(X_te) else np.zeros(0, dtype=np.float32)


def run_meta(rows: dict, X: np.ndarray, oof_masks: List[np.ndarray], cfg: I2Config, log=print
             ) -> Tuple[np.ndarray, np.ndarray, list]:
    """§2 nested OOF: for each meta-fold, train on the union of the earlier base-OOF halves (purged, capped),
    score its own OOF half. Returns (p_meta with NaN outside the meta-OOF period, meta_oof mask, fold records)."""
    n = len(rows["name"])
    p_meta = np.full(n, np.nan, dtype=np.float32)
    meta_oof = np.zeros(n, dtype=bool)
    y = rows["Y"][:, 0]
    records = []
    for mf in cfg.meta_folds:
        train = np.zeros(n, dtype=bool)
        for j in mf["train_base_folds"]:
            train |= oof_masks[j]
        oof = oof_masks[mf["oof_base_fold"]]
        train_purged = I1.apply_purge(rows, rows["sessions"], train, oof)
        tr_idx = np.where(train_purged)[0]
        te_idx = np.where(oof)[0]
        seed = meta_seed(mf["meta_fold"])
        rec = dict(mf, seed=seed, n_train_raw=int(train.sum()), n_purged=int(train.sum() - len(tr_idx)),
                   n_oof=int(len(te_idx)))
        if len(tr_idx) == 0 or len(te_idx) == 0:
            rec.update(n_train_used=0, capped=False, fitted=False, note="empty train or OOF: no meta fit")
            records.append(rec)
            log(f"meta {mf['name']}: empty train or OOF — skipped", flush=True)
            continue
        tr_idx, capped = I1.cap_rows(tr_idx, cfg.meta_row_cap, seed)
        rec.update(n_train_used=int(len(tr_idx)), capped=bool(capped), fitted=True)
        p_meta[te_idx] = fit_meta(X[tr_idx], y[tr_idx], X[te_idx])
        meta_oof |= oof
        records.append(rec)
        log(f"meta {mf['name']} train={len(tr_idx)}{' (capped)' if capped else ''} oof={len(te_idx)} seed={seed}",
            flush=True)
    return p_meta, meta_oof, records


# --------------------------------------------------------------------------
# §3 M0 diagnostic: unweighted z-sum within each session×slot cross-section (interpretation 4 + harness 11)
# --------------------------------------------------------------------------
def m0_zsum(rows: dict, preds: Dict[str, np.ndarray], mask: np.ndarray, min_names: int) -> np.ndarray:
    n = len(rows["name"])
    out = np.full(n, np.nan, dtype=np.float32)
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return out
    key = rows["session"][idx].astype(np.int64) * SLOTS + rows["slot"][idx].astype(np.int64)
    order = np.argsort(key, kind="stable")
    idx, key = idx[order], key[order]
    starts = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    counts = np.diff(np.r_[starts, len(key)])
    G = len(starts)
    grp = np.repeat(np.arange(G), counts)
    total = np.zeros(len(idx))
    avail = np.zeros(len(idx), dtype=np.int32)
    for bb in BASE_CODES:
        p = preds[bb][idx].astype(np.float64)
        fin = np.isfinite(p)
        cnt = np.bincount(grp, weights=fin.astype(float), minlength=G)
        mean = np.bincount(grp, weights=np.where(fin, p, 0.0), minlength=G) / np.maximum(cnt, 1)
        dev = np.where(fin, p - mean[grp], 0.0)
        var = np.bincount(grp, weights=dev * dev, minlength=G) / np.maximum(cnt - 1, 1)
        sd = np.sqrt(var)
        ok = fin & (cnt[grp] >= 2) & (sd[grp] > 0)
        total += np.where(ok, dev / np.where(ok, sd[grp], 1.0), 0.0)
        avail += ok
    total[(counts[grp] < min_names) | (avail == 0)] = np.nan
    out[idx] = total.astype(np.float32)
    return out


# --------------------------------------------------------------------------
# §4 common sample, pass bar, outcome register
# --------------------------------------------------------------------------
def common_sample(meta_oof: np.ndarray, p_meta: np.ndarray, preds: Dict[str, np.ndarray], s0: np.ndarray,
                  m0: np.ndarray) -> Tuple[np.ndarray, np.ndarray, dict]:
    """Rows where M_xgb has a prediction AND every base AND s0 have one (interpretation 2). M0's line uses the
    common sample further restricted to rows with an M0 value (interpretation 4)."""
    scored = meta_oof & np.isfinite(p_meta)
    common = scored.copy()
    excluded_by = {}
    for bb in BASE_CODES:
        miss = scored & ~np.isfinite(preds[bb])
        excluded_by[f"p_{bb}"] = int(miss.sum())
        common &= ~miss
    miss = scored & ~np.isfinite(s0)
    excluded_by["s0"] = int(miss.sum())
    common &= ~miss
    common_m0 = common & np.isfinite(m0)
    n_scored, n_common, n_m0 = int(scored.sum()), int(common.sum()), int(common_m0.sum())
    stats = dict(n_meta_oof_rows=int(meta_oof.sum()), n_mxgb_scored_rows=n_scored, n_common=n_common,
                 n_excluded=n_scored - n_common,
                 excluded_fraction=(round((n_scored - n_common) / n_scored, 6) if n_scored else None),
                 excluded_by_series=excluded_by,
                 n_common_m0=n_m0, m0_only_extra_excluded=n_common - n_m0,
                 m0_only_extra_excluded_fraction=(round((n_common - n_m0) / n_common, 6) if n_common else None),
                 rule=("common sample = meta-OOF rows where M_xgb, every base and s0 all have a prediction; every "
                       "series in the P1/P2/P3 comparison is scored on exactly these rows (interpretation 2); "
                       "M0's diagnostic line drops rows without an M0 value (interpretation 4)"))
    return common, common_m0, stats


def _t(res: dict):
    t = _dig(res, "overall", "block_t")
    return float(t) if isinstance(t, (int, float)) else None


def pass_bar(series: Dict[str, dict]) -> dict:
    """P1/P2/P3 on the common-sample results (strict inequalities on point estimates; margins stated as numbers)."""
    t_m = _t(series["M_xgb"])
    bear = _dig(series["M_xgb"], "per_regime", "BEAR", "n_eff_adj")
    bear_num = float(bear) if isinstance(bear, (int, float)) else None
    p1_life = t_m is not None and t_m >= P1_LIFE_BAR_T
    p1_bear = bear_num is not None and bear_num >= P1_BEAR_MIN_N_EFF_ADJ
    base_t = {bb: _t(series[bb]) for bb in SURVIVING_BASES}
    established = {bb: t for bb, t in base_t.items() if t is not None}
    best_base = max(established, key=established.get) if established else None
    best_t = established[best_base] if best_base else None
    p2 = (t_m is not None and best_t is not None and len(established) == len(base_t) and t_m > best_t)
    t_s0 = _t(series["s0"])
    p3 = t_m is not None and t_s0 is not None and t_m > t_s0
    return dict(
        P1=dict(passes=bool(p1_life and p1_bear), rule=f"M_xgb block-t >= {P1_LIFE_BAR_T} overall @ h={H} on "
                f"dependence-adjusted units AND BEAR n_eff_adj >= {P1_BEAR_MIN_N_EFF_ADJ:g} on M_xgb's own OOF IC",
                block_t=t_m, life_bar_t=P1_LIFE_BAR_T, margin_block_t=(round(t_m - P1_LIFE_BAR_T, 4) if t_m is not None else None),
                bear_n_eff_adj=bear, bear_min=P1_BEAR_MIN_N_EFF_ADJ,
                margin_bear=(round(bear_num - P1_BEAR_MIN_N_EFF_ADJ, 1) if bear_num is not None else None),
                life=bool(p1_life), bear_ok=bool(p1_bear)),
        P2=dict(passes=bool(p2), rule="M_xgb block-t > max(B0, B1, B2, B3 block-t) on the common sample",
                block_t=t_m, base_block_t=base_t, best_base=best_base, best_base_block_t=best_t,
                margin=(round(t_m - best_t, 4) if (t_m is not None and best_t is not None) else None),
                all_bases_established=(len(established) == len(base_t))),
        P3=dict(passes=bool(p3), rule="M_xgb block-t > s0 block-t on the common sample",
                block_t=t_m, s0_block_t=t_s0,
                margin=(round(t_m - t_s0, 4) if (t_m is not None and t_s0 is not None) else None)),
        stage_i2_pass=bool(p1_life and p1_bear and p2 and p3),
        note="strict inequalities on point estimates; no margin is claimed and none is required (§4)",
    )


def outcome_of(bar: dict) -> dict:
    p1, p2, p3 = bar["P1"]["passes"], bar["P2"]["passes"], bar["P3"]["passes"]
    if p1 and p2 and p3:
        verdict = "PASS"
    elif p1 and p2:
        verdict = "FAIL-A"
    else:
        verdict = "FAIL-B"
    row = OUTCOME_REGISTER[verdict]
    return dict(verdict=verdict, P1=p1, P2=p2, P3=p3, condition=row["condition"], consequence=row["consequence"],
                register_row=f"| {verdict} | {row['condition']} | {row['consequence']} |",
                register="doc/design/2026-08-29-goal2v3-stage-i2-prereg.md §4.4")


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def dev_run_identity(cfg: I2Config, src: dict, started: _dt.datetime) -> Tuple[str, pathlib.Path]:
    """DEV_RUN only: refuses (DevRunRefused) a tree that is not clean outside the bar store / output root or one
    without a commit; mints i2-dev-<UTC YYYYMMDDTHHMMSSZ>-<shortsha>; refuses if <out_root>/<run_id>/ exists."""
    if not isinstance(src.get("commit"), str) or not _HEX40.match(src["commit"]):
        raise DevRunRefused(f"cannot establish the source commit of the harness checkout ({src.get('error')})")
    if src.get("clean_tree") is not True:
        dirty = src.get("dirty_entries") or []
        raise DevRunRefused(f"source tree is not clean: {src.get('n_dirty')} entries outside the declared bar store / "
                            f"output root (e.g. {dirty[:REFUSE_LIST_N]}); commit or remove them — a DEV_RUN must be "
                            f"reproducible from its recorded commit")
    run_id = f"i2-dev-{started.strftime(_RUN_TS)}-{src['commit'][:8]}"
    bundle_dir = pathlib.Path(cfg.out_dir) / run_id
    if bundle_dir.exists():
        raise DevRunRefused(f"output bundle {bundle_dir} already exists; refusing to overwrite (every DEV_RUN "
                            f"writes its own bundle directory)")
    return run_id, bundle_dir


def _bind_dev_run(cfg: I2Config) -> None:
    """A DEV_RUN is only ever executed under a live GateAuthorization (I-1's check) AND a live I1Binding whose
    bundle files still hash to the bound values."""
    if cfg.run_status != "DEV_RUN":
        return
    I1._bind_dev_run(cfg.base)
    if cfg.base.run_status != "DEV_RUN":
        raise DevRunRefused("I-2 DEV_RUN over a base configuration that is not DEV_RUN")
    if cfg.i1 is None:
        raise I1NotBound("DEV_RUN without an I1Binding — call load_i1_binding() first")
    if sha256_file(cfg.i1.report_path) != cfg.i1.report_sha256 or sha256_file(cfg.i1.audit_path) != cfg.i1.audit_sha256:
        raise I1NotBound("the I-1 bundle changed on disk after binding")
    if (cfg.expected_block_t != EXPECTED_I1_BLOCK_T or cfg.expected_n_blocks != EXPECTED_I1_N_BLOCKS
            or tuple(cfg.expected_s0 or ()) != (ACCEPTED_I1_BUNDLE["s0_block_t"], ACCEPTED_I1_BUNDLE["s0_n_blocks"])
            or cfg.expected_consumed_aggregate != ACCEPTED_I1_BUNDLE["consumed_bar_aggregate_sha256"]):
        raise DevRunRefused("DEV_RUN determinism targets are not the frozen constants")


def frozen_block(cfg: I2Config) -> dict:
    """The full frozen-parameter block written to every report (I-2 constants + the I-1 block the re-fit used)."""
    return dict(
        spec=SPEC, i1=I1.frozen_block(cfg.base),
        accepted_i1_bundle=dict(ACCEPTED_I1_BUNDLE), i1_harness_sha256=I1_HARNESS_SHA256,
        expected_i1_block_t=dict(EXPECTED_I1_BLOCK_T), expected_i1_n_blocks=dict(EXPECTED_I1_N_BLOCKS),
        determinism_decimals=DETERMINISM_DECIMALS, surviving_bases=list(SURVIVING_BASES),
        meta_folds=[dict(m) for m in cfg.meta_folds], meta_oof_period=[cfg.meta_folds[0]["oof_start"],
                                                                        cfg.meta_folds[-1]["oof_end"]],
        meta_purge_bars=META_PURGE_BARS, meta_seed_base=META_SEED_BASE,
        meta_seed_formula="20260829 + 1000*meta_fold (meta_fold = the M-number 1..4)",
        meta_xgb_params=dict(META_XGB_PARAMS), meta_row_cap=cfg.meta_row_cap, meta_features=list(META_FEATURES),
        meta_label_horizon=META_LABEL_HORIZON, secondary_horizons=list(SECONDARY_HORIZONS),
        p1_life_bar_t=P1_LIFE_BAR_T, p1_bear_min_n_eff_adj=P1_BEAR_MIN_N_EFF_ADJ, series=list(SERIES),
        outcome_register={k: dict(v) for k, v in OUTCOME_REGISTER.items()},
    )


def run_stage_i2(cfg: I2Config, log=print) -> dict:
    import xgboost
    started_dt = _now_utc()
    started = started_dt.strftime(_TS)
    dev = cfg.run_status == "DEV_RUN"
    base = cfg.base
    _bind_dev_run(cfg)
    src = I1.source_state(REPO, ignore=[base.bar_store, cfg.out_dir])
    if dev:
        run_id, bundle_dir = dev_run_identity(cfg, src, started_dt)     # refuses dirty tree / existing bundle
    else:
        run_id = f"i2-smoke-{started_dt.strftime(_RUN_TS)}-{(src['commit'] or 'nogit')[:8]}"
        bundle_dir = pathlib.Path(cfg.out_dir)                          # smoke: fixed dir, overwrite allowed
    log(f"run {run_id} -> {bundle_dir}", flush=True)
    # ---- the I-1 re-fit, exactly as I-1 ran it (its own functions, its own constants)
    audit_in = I1.load_census_audit(base.census_audit)
    sessions = I1.session_list(audit_in, base.dev_start, base.dev_end)
    if not sessions:
        sys.exit("census audit carries no sessions inside the development window")
    manifest = I1.check_store_manifest(base.bar_store, audit_in, sessions, base.sector_etf_map, strict=dev)
    log(f"store manifest: {len(manifest['actual'])} files hashed == gate audit; {len(manifest['missing'])} missing; "
        f"absent from the audit: {manifest['absent_from_audit']}", flush=True)
    rows = I1.build_rows(base, audit_in, sessions, manifest, log=log)
    consumed = rows["consumed_sha256"]
    consumed_agg = manifest_aggregate(consumed)
    consumed_check = dict(aggregate_sha256=consumed_agg, count=len(consumed),
                          expected=cfg.expected_consumed_aggregate,
                          matches_i1_bundle=(consumed_agg == cfg.expected_consumed_aggregate
                                             if cfg.expected_consumed_aggregate else None))
    if cfg.expected_consumed_aggregate and consumed_agg != cfg.expected_consumed_aggregate:
        raise DeterminismRefused(f"the bars consumed by this run aggregate to {consumed_agg[:12]}.. over "
                                 f"{len(consumed)} files; the I-1 bundle consumed {cfg.expected_consumed_aggregate[:12]}.. "
                                 f"(harness interpretation 8: the re-fit must read the same bars; no fit was made)")
    log(f"observations: {len(rows['name'])} over {len(rows['names'])} names", flush=True)
    preds, fits, fold_counts = I1.run_bases(rows, base, log=log)
    oof_masks = [I1.fold_masks(rows, sessions, fold)[1] for fold in base.folds]
    oof_all = np.zeros(len(rows["name"]), dtype=bool)
    for m in oof_masks:
        oof_all |= m
    refit, audit_refit = {}, {}
    for bb in BASE_CODES:
        refit[bb], audit_refit[bb] = I1.screen_base(rows, preds[bb], oof_all, base)
    s0_refit, audit_refit["s0_reference"] = I1.screen_base(rows, rows["s0"], oof_all, base)
    # ---- §1.1 determinism guard BEFORE any meta fit
    if cfg.expected_block_t is not None:
        guard = determinism_guard(refit, cfg.expected_block_t, cfg.expected_n_blocks, s0_refit, cfg.expected_s0)
        log("determinism guard: PASS — " + ", ".join(f"{k} {v['observed_block_t']}/{v['observed_n_blocks']}"
                                                     for k, v in guard["per_series"].items()), flush=True)
    else:
        guard = dict(status="NOT_APPLIED", tolerance=f"block-t equal to {DETERMINISM_DECIMALS} decimals and n_blocks "
                     f"equal", per_series={}, note="SMOKE: no I-1 bundle to reproduce; the guard is exercised by tests")
    # ---- §2 + §3 the stack
    spy_daily = pd.read_parquet(base.spy_daily, columns=["close"])["close"]
    spy_daily.index = pd.to_datetime(spy_daily.index)
    spy_daily = spy_daily.sort_index()
    b3_slow = I1.b3_slow_state(spy_daily, sessions)                    # the I-1 definition, as of the prior close
    X_meta, feat_diag = meta_features(rows, preds, b3_slow)
    p_meta, meta_oof, meta_records = run_meta(rows, X_meta, oof_masks, cfg, log=log)
    m0 = m0_zsum(rows, preds, meta_oof, base.min_names)
    common, common_m0, cs = common_sample(meta_oof, p_meta, preds, rows["s0"], m0)
    log(f"meta-OOF rows {cs['n_meta_oof_rows']}, common sample {cs['n_common']} "
        f"(excluded {cs['excluded_fraction']}), M0 line {cs['n_common_m0']}", flush=True)
    # ---- §4 every series on the common sample (+ M_xgb on its full meta-OOF rows, diagnostic)
    series, audit_series = {}, {}
    series["M_xgb"], audit_series["M_xgb"] = I1.screen_base(rows, p_meta, common, base)
    series["M_xgb_full_meta_oof_DIAGNOSTIC_ONLY"], audit_series["M_xgb_full_meta_oof"] = \
        I1.screen_base(rows, p_meta, meta_oof, base)
    series["M0"], audit_series["M0"] = I1.screen_base(rows, m0, common_m0, base)
    for bb in BASE_CODES:
        series[bb], audit_series[bb] = I1.screen_base(rows, preds[bb], common, base)
    series["s0"], audit_series["s0"] = I1.screen_base(rows, rows["s0"], common, base)
    for name, res in series.items():
        res["sample"] = ("common" if name in SERIES else
                         "all meta-OOF rows (diagnostic; the pass bar uses the common sample)")
        res["gating"] = (name == "M_xgb")
        res.pop("life_bar", None)
        res["passes_life_bar_DIAGNOSTIC_ONLY"] = res.pop("passes_life_bar")
        if name != "M_xgb":
            res.pop("secondary_horizons_DIAGNOSTIC_ONLY", None)      # interpretation 6: reported for M_xgb
    bar = pass_bar(series)
    outcome = outcome_of(bar)
    feature_missing = {f: int(np.isnan(X_meta[meta_oof, i]).sum()) for i, f in enumerate(META_FEATURES)}
    b2_oof_states = {}
    for f in fits:
        if f["base"] == "B2" and f.get("n_oof", 0) > 0:
            b2_oof_states.setdefault(f"fold_{f['fold_index']}", []).append(f["state"])
    frozen = frozen_block(cfg)
    ended = _now_utc().strftime(_TS)
    provenance = dict(
        run_id=run_id, run_status=cfg.run_status,
        outputs=dict(root=str(cfg.out_dir), bundle_dir=str(bundle_dir), report="report.json",
                     audit="g2v3_stage_i2_audit.json.gz",
                     policy=("DEV_RUN: bundle_dir = <root>/<run_id>/, refused if it already exists; "
                             "SMOKE: bundle_dir = root, overwritten")),
        source=dict(repo_root=str(REPO), **src),
        invocation=dict(argv=list(sys.argv), cwd=os.getcwd(), python=sys.executable,
                        env={"G2V3_BAR_STORE": os.environ.get("G2V3_BAR_STORE")}),
        timestamps_utc=dict(start=started, end=ended,
                            derivation="logged by this process's own clock (datetime.now(UTC)): start at entry "
                                       "to run_stage_i2, end immediately before the report is written"),
        gate_bundle=(base.gate.as_record() if base.gate is not None else None),
        i1_bundle=(cfg.i1.as_record() if cfg.i1 is not None else None),
        inputs=dict(
            census_audit=_input_record(base.census_audit),
            strategy_config=(_input_record(base.strategy_config) if base.strategy_config else None),
            sector_map_sha256=sha256_json(base.sector_map), sector_etf_map_sha256=sha256_json(base.sector_etf_map),
            spy_daily=_input_record(base.spy_daily),
            bar_store=str(base.bar_store)),
        store_manifest_check=dict(
            strict=dev, n_needed=len(manifest["needed"]), n_required_in_audit=len(manifest["required"]),
            n_hashed=len(manifest["actual"]), missing_files=manifest["missing"],
            absent_from_audit=manifest["absent_from_audit"],
            expected_absent_from_audit=sorted(I1.EXPECTED_ABSENT_FROM_AUDIT),
            rule=("every needed file the gate audit carries must exist and hash-match before any bar is read; "
                  "DEV_RUN refuses on any missing/mismatched/unaudited file or on an absent-ETF set != "
                  "EXPECTED_ABSENT_FROM_AUDIT")),
        frozen_parameters=dict(frozen, interpretations=list(INTERPRETATIONS)),
        consumed_bar_manifest=dict(count=len(consumed), aggregate_sha256=consumed_agg, aggregate_method=MANIFEST_METHOD,
                                   per_file="audit consumed_sha256 (hashed from the store at run time)",
                                   i1_bundle_aggregate_sha256=cfg.expected_consumed_aggregate,
                                   matches_i1_bundle=consumed_check["matches_i1_bundle"]),
        determinism_guard=copy.deepcopy(guard),          # its own copy: the validator compares it to base_refit's
    )
    report = dict(
        stage="GOAL-2v3 Stage I-2", run_status=cfg.run_status, run_id=run_id,
        generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        spec=SPEC, i1_spec="doc/design/2026-08-27-goal2v3-intraday-granularity.md#stage-i-1",
        versions=dict(python=platform.python_version(), xgboost=xgboost.__version__, numpy=np.__version__,
                      pandas=pd.__version__, scipy=__import__("scipy").__version__),
        frozen=frozen,
        inputs=dict(census_audit=str(base.census_audit), bar_store=str(base.bar_store), spy_daily=str(base.spy_daily),
                    gate_run_id=(base.gate.run_id if base.gate is not None else None),
                    i1_run_id=(cfg.i1.run_id if cfg.i1 is not None else None),
                    n_sessions=len(sessions), n_names=len(rows["names"]), n_observations=int(len(rows["name"])),
                    n_oof_observations=int(oof_all.sum()), n_meta_oof_observations=int(meta_oof.sum()),
                    missing_store_files=rows["missing_files"], absent_from_audit=rows["absent_from_audit"],
                    sec13_etf_available_by_sector=rows["sec13_available"], consumed_bar_check=consumed_check),
        base_refit=dict(fold_row_counts=fold_counts, bases=refit, s0_reference=s0_refit, determinism_guard=guard,
                        note="the I-1 bases re-fitted with the I-1 harness (same constants, seeds, folds, row cap, "
                             "store); scored on all I-1 OOF rows exactly as I-1 did, for the §1.1 guard"),
        meta=dict(folds=meta_records, features=list(META_FEATURES), feature_nan_counts_on_meta_oof=feature_missing,
                  **feat_diag, b2_oof_states_by_fold=b2_oof_states,
                  n_meta_oof_rows=int(meta_oof.sum()), s0_is_a_feature=False),
        common_sample=cs,
        series=series,
        pass_bar=bar,
        outcome=outcome,
        prereg_interpretations=list(PREREG_INTERPRETATIONS), harness_interpretations=list(HARNESS_INTERPRETATIONS),
        interpretations=list(INTERPRETATIONS),
        provenance=provenance,
    )
    if not dev:
        report["note"] = "SMOKE run on synthetic data: no development-window evidence; the outcome is not a verdict."
        report["outcome"]["binding"] = False
    else:
        report["outcome"]["binding"] = True
    if dev:
        bundle_dir.mkdir(parents=True, exist_ok=False)
    else:
        bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "report.json").write_text(json.dumps(report, indent=1, default=_json_default))
    audit_out = dict(base_refit=audit_refit, base_fits=fits, fold_row_counts=fold_counts, meta_folds=meta_records,
                     series=audit_series, consumed_sha256=consumed)
    with gzip.open(bundle_dir / "g2v3_stage_i2_audit.json.gz", "wt") as fh:
        json.dump(audit_out, fh, default=_json_default)
    return report


# --------------------------------------------------------------------------
# provenance validator: rebuild every hash the report claims from the inputs on disk
# --------------------------------------------------------------------------
_CONSTANT_FROZEN = dict(spec=SPEC, accepted_i1_bundle=dict(ACCEPTED_I1_BUNDLE), i1_harness_sha256=I1_HARNESS_SHA256,
                        expected_i1_block_t=dict(EXPECTED_I1_BLOCK_T), expected_i1_n_blocks=dict(EXPECTED_I1_N_BLOCKS),
                        determinism_decimals=DETERMINISM_DECIMALS, surviving_bases=list(SURVIVING_BASES),
                        meta_purge_bars=META_PURGE_BARS, meta_seed_base=META_SEED_BASE,
                        meta_xgb_params=dict(META_XGB_PARAMS), meta_features=list(META_FEATURES),
                        meta_label_horizon=META_LABEL_HORIZON, secondary_horizons=list(SECONDARY_HORIZONS),
                        p1_life_bar_t=P1_LIFE_BAR_T, p1_bear_min_n_eff_adj=P1_BEAR_MIN_N_EFF_ADJ, series=list(SERIES),
                        outcome_register={k: dict(v) for k, v in OUTCOME_REGISTER.items()})
_DEV_ONLY_FROZEN = dict(meta_folds=[dict(m) for m in META_FOLDS], meta_oof_period=list(META_OOF_PERIOD),
                        meta_row_cap=META_ROW_CAP)


# --------------------------------------------------------------------------
# path identity is REPO-RELATIVE (codex r1 on #1091). A run records absolute paths; the prefix above its own
# repo root is that run's environment (a scratchpad worktree that need not exist where the review happens).
# What identifies a committed file is (its path relative to the run's repo root, its sha256): the validator
# resolves the recorded path against the recorded root and checks the file at <this checkout>/<relative>.
# --------------------------------------------------------------------------
def recorded_repo_root(prov: dict) -> Optional[str]:
    """The run's own checkout root as its report recorded it: `source.repo_root`, else `invocation.cwd`."""
    root = _dig(prov, "source", "repo_root") or _dig(prov, "invocation", "cwd")
    return str(root) if root else None


_BAD_SEGMENTS = ("", ".", "..")


def _abs_segments(path) -> Optional[List[str]]:
    """Segments of an ABSOLUTE POSIX path that contains no '', '.' or '..' segment; None for anything else.
    Lexical only — the form is judged on the recorded text, not on what a filesystem would do with it."""
    s = str(path)
    if not s.startswith("/"):
        return None
    segs = s[1:].split("/") if len(s) > 1 else []
    return None if any(seg in _BAD_SEGMENTS for seg in segs) else segs


def path_form_problems(label: str, path) -> List[str]:
    """A recorded path that is not absolute, or carries a '', '.' or '..' segment, is a problem in its own right —
    never silently 'outside the repository' (codex r2 on #1092: `<repo_root>/../outside/x` must not validate)."""
    if path is not None and _abs_segments(path) is None:
        return [f"{label} {str(path)!r} is not an absolute path free of '', '.' and '..' segments"]
    return []


def repo_relative(path, root) -> Optional[str]:
    """`path` relative to `root` as POSIX text when both are well-formed absolute paths (see `_abs_segments`)
    and `path` is lexically a strict descendant of `root`; None otherwise (missing, malformed, or not under
    `root`). The result never contains a '', '.' or '..' segment. Pure path arithmetic."""
    if not path or not root:
        return None
    ps, rs = _abs_segments(path), _abs_segments(root)
    if ps is None or rs is None or len(ps) <= len(rs) or ps[:len(rs)] != rs:
        return None
    return "/".join(ps[len(rs):])


def confined(p: pathlib.Path, repo_root: pathlib.Path) -> bool:
    """True iff `p`, with every symlink resolved, lies inside the resolved `repo_root`."""
    try:
        return p.resolve().is_relative_to(repo_root.resolve())
    except (OSError, RuntimeError):
        return False


def _input_record(p) -> dict:
    """{path, path_relative, sha256} for a run input. `path_relative` is the path relative to this checkout's
    REPO (the `source.repo_root` the same report records; None for an input outside it) — the same arithmetic
    the validator performs, recorded so a reader sees the checkout-independent identity without doing it."""
    return dict(path=str(p), path_relative=repo_relative(str(p), str(REPO)), sha256=sha256_file(p))


def _bundle_dir_problems(block: dict, label: str, bound_dir: str, run_root: Optional[str]) -> List[str]:
    """`<label>.dir` as recorded must be `bound_dir` relative to the run's own repo root."""
    rel = repo_relative(block.get("dir"), run_root)
    if rel != bound_dir:
        return [f"{label}.dir {block.get('dir')!r} is not {bound_dir!r} relative to the recorded repo root {run_root!r}"]
    return []


def _input_file_problems(entry: dict, key: str, run_root: Optional[str],
                         repo_root: pathlib.Path) -> Tuple[List[str], Optional[str], Optional[pathlib.Path]]:
    """Check one `inputs.<key>` = {path, sha256[, path_relative]} record. A path under the run's repo root is
    checked at <repo_root>/<relative>; a path outside it (the umbrella's SPY parquet, the pinned strategy config)
    can only be checked where it was recorded. Returns (problems, relative-or-None, the path checked — None when
    the record was refused unread, so no caller opens a refused path either)."""
    problems = path_form_problems(f"inputs.{key}.path", entry.get("path"))
    if problems:
        return problems, None, None                                       # malformed: nothing is read for it
    rel = repo_relative(entry.get("path"), run_root)
    if "path_relative" in entry:
        pr = entry.get("path_relative")
        if pr is not None and (str(pr).startswith("/") or any(seg in _BAD_SEGMENTS for seg in str(pr).split("/"))):
            problems.append(f"inputs.{key}.path_relative {pr!r} is not a relative path free of '', '.' and '..' segments")
        if pr != rel:
            problems.append(f"inputs.{key}.path_relative {pr!r} != {rel!r} "
                            f"(path relative to the recorded repo root {run_root!r})")
    p = (repo_root / rel) if rel is not None else pathlib.Path(str(entry.get("path")))
    if rel is not None and not confined(p, repo_root):
        problems.append(f"inputs.{key}.path resolves outside repo_root (symlink or traversal): {p}")
        return problems, rel, None                                        # refused: nothing is read for it
    if not p.is_file():
        problems.append(f"inputs.{key}.path missing on disk: {p}")
    elif sha256_file(p) != entry.get("sha256"):
        problems.append(f"inputs.{key}.sha256 != file on disk ({p})")
    return problems, rel, p


def _dev_census_audit_problems(prov: dict, run_root: Optional[str], census_rel: Optional[str]) -> List[str]:
    """DEV_RUN: the census audit must be the gate bundle's audit — same repo-relative path AND the bound sha256."""
    g = ACCEPTED_GATE_BUNDLE
    want = f"{g['dir']}/{g['audit_file']}"
    if census_rel != want:
        return [f"DEV_RUN census audit is not the gate bundle's audit {want} (recorded path "
                f"{_dig(prov, 'inputs', 'census_audit', 'path')!r} resolves to {census_rel!r} relative to the "
                f"recorded repo root {run_root!r})"]
    if _dig(prov, "inputs", "census_audit", "sha256") != g["audit_sha256"]:
        return ["DEV_RUN inputs.census_audit.sha256 != the bound gate audit sha256"]
    return []


def _census_cross_check_problems(consumed: dict, census_on_disk: Optional[pathlib.Path]) -> List[str]:
    """Every consumed bar file must be the census-audited file (same sha256 in the census audit's map)."""
    if census_on_disk is None or not census_on_disk.is_file():
        return []                                   # its absence is already a problem on its own line
    try:
        census_hashes = I1.load_census_audit(census_on_disk).get("bar_store_sha256") or {}
    except (OSError, ValueError):
        census_hashes = {}
    bad = [t for t, h in consumed.items() if census_hashes.get(t) != h]
    return [f"{len(bad)} consumed files are not the census-audited files (e.g. {bad[:5]})"] if bad else []


def validate_i1_provenance(report: dict, audit: dict, repo_root: pathlib.Path = None) -> List[str]:
    """`I1.validate_i1_provenance` with the census audit's identity checked REPO-RELATIVELY (the rule above).

    The I-1 harness compares the recorded absolute `inputs.census_audit.path` with THIS checkout's GATE_AUDIT —
    the reviewer's environment — so the committed I-1 bundle (recorded from a scratchpad worktree) fails from
    every other checkout with "DEV_RUN census audit is not the gate bundle's audit". That harness file is frozen
    by the §1 binding (I1_HARNESS_SHA256: the module imported above IS the code the accepted bundle was fitted
    with; editing it would un-bind this line), so the correction lives here: for a DEV_RUN report the I-1
    verdicts about the census audit's absolute path are replaced by the repo-relative rule and the consumed-bar
    cross-check is re-run against the file at <repo_root>/<relative>. Every other I-1 check is I-1's own."""
    repo_root = pathlib.Path(repo_root if repo_root is not None else REPO)
    problems = I1.validate_i1_provenance(report, audit, repo_root)
    prov = report.get("provenance")
    if not isinstance(prov, dict) or report.get("run_status") != "DEV_RUN":
        return problems         # a SMOKE census audit lives outside any repo: I-1's absolute-path checks are the rule
    environment_only = ("DEV_RUN census audit is not the gate bundle's audit",
                        "inputs.census_audit.path missing on disk", "inputs.census_audit.sha256 != file on disk")
    problems = [p for p in problems
                if not p.startswith(environment_only) and "consumed files are not the census-audited files" not in p]
    run_root = recorded_repo_root(prov)
    if run_root is None:
        problems.append("provenance records neither source.repo_root nor invocation.cwd")
    problems += path_form_problems("source.repo_root", run_root)
    entry = _dig(prov, "inputs", "census_audit")
    census_rel, census_on_disk = None, None
    if isinstance(entry, dict):
        more, census_rel, census_on_disk = _input_file_problems(entry, "census_audit", run_root, repo_root)
        problems += more
    problems += _dev_census_audit_problems(prov, run_root, census_rel)
    gate = prov.get("gate_bundle")
    if isinstance(gate, dict):
        problems += _bundle_dir_problems(gate, "gate_bundle", ACCEPTED_GATE_BUNDLE["dir"], run_root)
    consumed = audit.get("consumed_sha256") if isinstance(audit, dict) else None
    if isinstance(consumed, dict) and consumed:
        problems += _census_cross_check_problems(consumed, census_on_disk)
    return problems


def validate_i2_provenance(report: dict, audit: dict, repo_root: pathlib.Path = None) -> List[str]:
    """Return every disagreement between a Stage I-2 report's `provenance` block and (a) the report itself,
    (b) the audit's consumed-bar hashes, (c) the files on disk it names, (d) this module's frozen constants,
    (e) the gate + I-1 bundles under `repo_root`. Empty list == the provenance is complete and verifiable.
    Paths are compared REPO-RELATIVELY (see `repo_relative`): the same verdict from a checkout at any path."""
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
            problems.append(f"run_id {run_id!r} does not match i2-(dev|smoke)-<UTC YYYYMMDDTHHMMSSZ>-<shortsha>")
        elif run_id.split("-")[1] != ("dev" if dev else "smoke"):
            problems.append(f"run_id {run_id!r} kind disagrees with run_status {report.get('run_status')!r}")
        elif dev and run_id.endswith("-nogit"):
            problems.append("DEV_RUN run_id carries no source commit")
        if report.get("run_id") != run_id:
            problems.append("report.run_id != provenance.run_id")
    if prov.get("run_status") != report.get("run_status"):
        problems.append("provenance.run_status != report.run_status")
    bundle_dir, root = need("outputs", "bundle_dir"), need("outputs", "root")
    if isinstance(bundle_dir, str) and isinstance(root, str) and isinstance(run_id, str):
        bp = pathlib.Path(bundle_dir)
        if dev and (bp.name != run_id or bp.parent != pathlib.Path(root)):
            problems.append(f"DEV_RUN outputs.bundle_dir {bundle_dir!r} is not <outputs.root>/<run_id>/")
    # --- source
    commit = need("source", "commit")
    if not (isinstance(commit, str) and _HEX40.match(commit)):
        problems.append(f"source.commit is not a 40-hex sha: {commit!r}")
    elif isinstance(run_id, str) and _RUN_ID.match(run_id) and not run_id.endswith(commit[:8]):
        problems.append("run_id short sha != source.commit")
    clean = need("source", "clean_tree")
    if not isinstance(clean, bool):
        problems.append("source.clean_tree must be a bool")
    elif dev and clean is not True:
        problems.append("DEV_RUN source.clean_tree is not True (a dev run from a dirty tree is not reproducible)")
    run_root = recorded_repo_root(prov)         # the run's OWN checkout root: recorded paths resolve against it
    if run_root is None:
        problems.append("provenance records neither source.repo_root nor invocation.cwd")
    problems += path_form_problems("source.repo_root", run_root)
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
        t0, t1 = _dt.datetime.strptime(start, _TS), _dt.datetime.strptime(end, _TS)
        if t1 < t0:
            problems.append(f"timestamps_utc end {end} precedes start {start}")
        if isinstance(run_id, str) and _RUN_ID.match(run_id) and run_id.split("-")[2] != t0.strftime(_RUN_TS):
            problems.append("run_id UTC instant != timestamps_utc.start")
    except (TypeError, ValueError):
        problems.append(f"timestamps_utc start/end must be {_TS}: {start!r} / {end!r}")
    # --- gate bundle (I-0), as I-1 validates it
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
        problems += _bundle_dir_problems(gate, "gate_bundle", g["dir"], run_root)
        gb = repo_root / g["dir"]
        for key, fname in (("report_sha256", g["report_file"]), ("audit_sha256", g["audit_file"]),
                           ("provenance_sha256", g["provenance_file"])):
            p = gb / fname
            if not p.is_file():
                problems.append(f"gate bundle file missing under repo_root: {p}")
            elif sha256_file(p) != gate.get(key):
                problems.append(f"gate_bundle.{key} != sha256 of {p.name} on disk")
    # --- I-1 bundle
    i1 = prov.get("i1_bundle")
    if dev and not isinstance(i1, dict):
        problems.append("DEV_RUN provenance has no i1_bundle")
    if isinstance(i1, dict):
        b = ACCEPTED_I1_BUNDLE
        for key, want in (("run_id", b["run_id"]), ("source_commit", b["source_commit"]),
                          ("report_sha256", b["report_sha256"]), ("audit_sha256", b["audit_sha256"]),
                          ("consumed_bar_aggregate_sha256", b["consumed_bar_aggregate_sha256"]),
                          ("consumed_bar_count", b["consumed_bar_count"]), ("harness_sha256", I1_HARNESS_SHA256),
                          ("expected_block_t", EXPECTED_I1_BLOCK_T), ("expected_n_blocks", EXPECTED_I1_N_BLOCKS),
                          ("surviving_bases", list(SURVIVING_BASES))):
            if i1.get(key) != want:
                problems.append(f"i1_bundle.{key} = {i1.get(key)!r} != bound {want!r}")
        problems += _bundle_dir_problems(i1, "i1_bundle", b["dir"], run_root)
        ib = repo_root / b["dir"]
        for key, fname in (("report_sha256", b["report_file"]), ("audit_sha256", b["audit_file"])):
            p = ib / fname
            if not p.is_file():
                problems.append(f"I-1 bundle file missing under repo_root: {p}")
            elif sha256_file(p) != i1.get(key):
                problems.append(f"i1_bundle.{key} != sha256 of {p.name} on disk")
        hp = repo_root / I1_HARNESS_PATH
        if not hp.is_file():
            problems.append(f"I-1 harness missing under repo_root: {hp}")
        elif sha256_file(hp) != i1.get("harness_sha256"):
            problems.append("i1_bundle.harness_sha256 != sha256 of the I-1 harness on disk")
    # --- inputs on disk (repo-relative where the recorded path is under the run's repo root)
    census_rel, census_on_disk = None, None
    for key in ("census_audit", "spy_daily"):
        entry = need("inputs", key)
        if isinstance(entry, dict):
            more, rel, p = _input_file_problems(entry, key, run_root, repo_root)
            problems += more
            if key == "census_audit":
                census_rel, census_on_disk = rel, p
    sc = _dig(prov, "inputs", "strategy_config")
    if dev and not isinstance(sc, dict):
        problems.append("DEV_RUN provenance has no inputs.strategy_config")
    if isinstance(sc, dict):
        more, _rel, p = _input_file_problems(sc, "strategy_config", run_root, repo_root)
        problems += more
        if p is not None and p.is_file():                          # a refused record is not parsed either
            try:
                cfgj = json.loads(p.read_text(encoding="utf-8"))
                if sha256_json(dict(cfgj["sector_map"])) != _dig(prov, "inputs", "sector_map_sha256"):
                    problems.append("inputs.sector_map_sha256 != sector_map rebuilt from the strategy config")
                if sha256_json(dict(cfgj["sector_etf_map"])) != _dig(prov, "inputs", "sector_etf_map_sha256"):
                    problems.append("inputs.sector_etf_map_sha256 != sector_etf_map rebuilt from the strategy config")
            except (ValueError, KeyError, TypeError) as exc:
                problems.append(f"strategy config unreadable for the sector-map rebuild ({exc})")
    if dev:
        problems += _dev_census_audit_problems(prov, run_root, census_rel)
    # --- store manifest check
    smc = need("store_manifest_check")
    if isinstance(smc, dict):
        if dev and smc.get("strict") is not True:
            problems.append("DEV_RUN store_manifest_check.strict is not True")
        if dev and smc.get("missing_files"):
            problems.append(f"DEV_RUN store_manifest_check.missing_files is not empty: {smc.get('missing_files')[:5]}")
        if dev and sorted(smc.get("absent_from_audit") or []) != sorted(I1.EXPECTED_ABSENT_FROM_AUDIT):
            problems.append(f"DEV_RUN store_manifest_check.absent_from_audit {smc.get('absent_from_audit')!r} != "
                            f"EXPECTED_ABSENT_FROM_AUDIT {sorted(I1.EXPECTED_ABSENT_FROM_AUDIT)}")
        if smc.get("expected_absent_from_audit") != sorted(I1.EXPECTED_ABSENT_FROM_AUDIT):
            problems.append("store_manifest_check.expected_absent_from_audit != module EXPECTED_ABSENT_FROM_AUDIT")
    # --- frozen block: internal consistency + module constants + the interpretations byte-identical
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
            i1fp = fp.get("i1") or {}
            for key, want in dict(I1._CONSTANT_FROZEN, **I1._DEV_ONLY_FROZEN).items():
                if i1fp.get(key) != want:
                    problems.append(f"DEV_RUN frozen_parameters.i1.{key} = {i1fp.get(key)!r} != I-1 frozen {want!r}")
        if fp.get("interpretations") != list(INTERPRETATIONS):
            problems.append("frozen_parameters.interpretations are not the frozen INTERPRETATIONS (byte-identical)")
    if report.get("interpretations") != list(INTERPRETATIONS):
        problems.append("report.interpretations != INTERPRETATIONS")
    if report.get("prereg_interpretations") != list(PREREG_INTERPRETATIONS):
        problems.append("report.prereg_interpretations != the prereg's six, verbatim")
    # --- consumed-bar manifest: rebuilt from the audit; DEV_RUN must equal the I-1 bundle's aggregate
    man = need("consumed_bar_manifest")
    consumed = audit.get("consumed_sha256") if isinstance(audit, dict) else None
    if not isinstance(consumed, dict) or not consumed:
        problems.append("audit has no consumed_sha256 map")
    elif isinstance(man, dict):
        if man.get("count") != len(consumed):
            problems.append(f"consumed_bar_manifest.count {man.get('count')} != {len(consumed)} in the audit")
        agg = manifest_aggregate(consumed)
        if man.get("aggregate_sha256") != agg:
            problems.append("consumed_bar_manifest.aggregate_sha256 != aggregate rebuilt from audit.consumed_sha256")
        if dev and (agg != ACCEPTED_I1_BUNDLE["consumed_bar_aggregate_sha256"] or man.get("matches_i1_bundle") is not True):
            problems.append("DEV_RUN consumed-bar aggregate != the I-1 bundle's (the re-fit did not read the same bars)")
        problems += _census_cross_check_problems(consumed, census_on_disk)
    # --- determinism guard: a DEV_RUN report exists only if the guard passed on the frozen targets
    dg = need("determinism_guard")
    if isinstance(dg, dict):
        if dev:
            if dg.get("status") != "PASS":
                problems.append(f"DEV_RUN determinism_guard.status = {dg.get('status')!r}, not PASS")
            per = dg.get("per_series") or {}
            for bb, want_t in EXPECTED_I1_BLOCK_T.items():
                rec = per.get(bb) or {}
                if rec.get("match") is not True or rec.get("expected_block_t") != want_t \
                        or rec.get("expected_n_blocks") != EXPECTED_I1_N_BLOCKS[bb]:
                    problems.append(f"DEV_RUN determinism_guard.per_series.{bb} does not match the frozen targets")
                got = _dig(report, "base_refit", "bases", bb, "overall", "block_t")
                if not isinstance(got, (int, float)) or round(float(got), DETERMINISM_DECIMALS) != want_t:
                    problems.append(f"DEV_RUN base_refit.bases.{bb}.overall.block_t {got!r} != {want_t}")
        if dg != _dig(report, "base_refit", "determinism_guard"):
            problems.append("provenance.determinism_guard != report.base_refit.determinism_guard")
    # --- outcome register + pass-bar arithmetic
    out = report.get("outcome") or {}
    verdict = out.get("verdict")
    if verdict not in ("PASS", "FAIL-A", "FAIL-B"):
        problems.append(f"outcome.verdict {verdict!r} is not a §4.4 result row")
    else:
        row = OUTCOME_REGISTER[verdict]
        if out.get("condition") != row["condition"] or out.get("consequence") != row["consequence"]:
            problems.append("outcome row text != OUTCOME_REGISTER (verbatim)")
        bar = report.get("pass_bar") or {}
        p1, p2, p3 = (_dig(bar, k, "passes") for k in ("P1", "P2", "P3"))
        if None in (p1, p2, p3):
            problems.append("pass_bar lacks P1/P2/P3")
        else:
            if bar.get("stage_i2_pass") != (p1 and p2 and p3):
                problems.append("pass_bar.stage_i2_pass != P1 ∧ P2 ∧ P3")
            if outcome_of(bar)["verdict"] != verdict:
                problems.append("outcome.verdict != the register row implied by P1/P2/P3")
        if out.get("binding") is not dev:
            problems.append("outcome.binding must be True for DEV_RUN and False otherwise")
    return problems


# --------------------------------------------------------------------------
# synthetic smoke (shared by the default CLI path and the tests)
# --------------------------------------------------------------------------
def _smoke_folds(sessions: List[str]) -> Tuple[Tuple[str, str, str], ...]:
    """Three forward-chaining base folds (train ~40%, then three OOF chunks) => two meta-folds M1, M2."""
    n = len(sessions)
    a, b, c = (2 * n) // 5, (3 * n) // 5, (4 * n) // 5
    return ((sessions[a - 1], sessions[a], sessions[b - 1]),
            (sessions[b - 1], sessions[b], sessions[c - 1]),
            (sessions[c - 1], sessions[c], sessions[-1]))


def smoke_base_config(syn: dict, out_dir: pathlib.Path, min_names: int = 20, gate=None) -> I1.RunConfig:
    return I1._smoke_config(syn["bar_store"], syn["census_audit"], syn["spy_daily"], syn["sector_map"],
                            syn["sector_etf_map"], out_dir, _smoke_folds(syn["sessions"]), min_names=min_names,
                            dev_start=syn["sessions"][0], dev_end=syn["sessions"][-1],
                            strategy_config=syn["strategy_config"], gate=gate)


def run_smoke(out_dir: pathlib.Path, planted: bool = True, log=print, n_names: int = 30, n_sessions: int = 40) -> dict:
    syn = I1._synthetic_store(out_dir / "synthetic", planted=planted, n_names=n_names, n_sessions=n_sessions)
    cfg = _smoke_config(smoke_base_config(syn, out_dir / "out"), out_dir / "out")
    return run_stage_i2(cfg, log=log)


def _summary(report: dict) -> dict:
    return dict(run_status=report["run_status"], run_id=report["run_id"], xgboost=report["versions"]["xgboost"],
                determinism_guard=report["base_refit"]["determinism_guard"]["status"],
                base_refit={bb: report["base_refit"]["bases"][bb]["overall"]["block_t"] for bb in BASE_CODES},
                common_sample=dict(n=report["common_sample"]["n_common"],
                                   excluded_fraction=report["common_sample"]["excluded_fraction"]),
                series={k: _t(v) for k, v in report["series"].items()},
                P1=report["pass_bar"]["P1"]["passes"], P2=report["pass_bar"]["P2"]["passes"],
                P3=report["pass_bar"]["P3"]["passes"], outcome=report["outcome"]["verdict"],
                binding=report["outcome"]["binding"],
                consumed_bar_manifest=report["provenance"]["consumed_bar_manifest"]["aggregate_sha256"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dev-run", action="store_true",
                    help="run on the REAL development bar store (G2V3_BAR_STORE); refuses (exit 2) unless the "
                         "Stage I-0 GATE_RUN bundle and the Stage I-1 DEV_RUN bundle verify against the frozen "
                         "constants, the tree is clean, <out_root>/<run_id>/ does not exist, the store is the "
                         "complete audited store and the base re-fit reproduces the I-1 bundle")
    ap.add_argument("--smoke-out", default=None, help="synthetic smoke output dir (default: a temp dir)")
    args = ap.parse_args(argv)
    if args.dev_run:
        try:
            auth = I1.load_gate_authorization(REPO)            # FIRST: the I-0 gate
            print(f"gate authorization: {auth.run_id} @ {auth.frozen_source_commit[:8]} verdict={auth.gate_verdict}",
                  flush=True)
            i1 = load_i1_binding(REPO)                        # SECOND: the I-1 bundle
            print(f"I-1 binding: {i1.run_id} @ {i1.source_commit[:8]} report={i1.report_sha256[:12]}.. "
                  f"audit={i1.audit_sha256[:12]}.. consumed={i1.consumed_bar_aggregate_sha256[:12]}..", flush=True)
            cfg = dev_run_config(auth, i1)
            report = run_stage_i2(cfg)
        except DevRunRefused as exc:                          # gate / I-1 binding / tree / bundle / store / determinism
            print(f"REFUSED --dev-run (fail closed): {exc}", file=sys.stderr, flush=True)
            return 2
    else:
        out = pathlib.Path(args.smoke_out or tempfile.mkdtemp(prefix="g2v3_i2_smoke_"))
        print(f"synthetic smoke -> {out}", flush=True)
        report = run_smoke(out)
    print(json.dumps(_summary(report), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
