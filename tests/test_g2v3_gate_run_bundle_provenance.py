"""GATE_RUN bundles under doc/research/data/ must carry a provenance.json that AGREES.

Born from PR #1083 review r1: a gate report that only *narrates* its origin
("run from f3d5bf7b") is not independently checkable from the bundle. Every
directory whose report carries ``run_status == "GATE_RUN"`` must ship a
``provenance.json`` beside it, and this test fails if that file is missing or
disagrees with the artifacts it describes:

- report / audit sha256 in provenance == sha256 of the files on disk
- seed-list sha256 + count in provenance == the committed seed list
- frozen_source_commit is a full 40-hex sha; clean_tree is a bool
- gate_verdict / report_run_status in provenance == the report's own values
- census-script and design-doc hashes are non-empty 64-hex strings
- input manifest aggregate == sha256 recomputed over the audit's per-file hashes

And the converse: a DEVELOPMENT_ONLY report may not sit beside a provenance
claiming GATE_RUN. A tampered copy (mutated report) must FAIL validation.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO / "doc" / "research" / "data"
PROVENANCE_NAME = "provenance.json"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The one committed gate bundle this line has produced; the test must never be
# vacuous, so its presence is asserted explicitly.
KNOWN_GATE_BUNDLE = DATA_ROOT / "2026-08-29-g2v3-i0-gate-run"
KNOWN_DEV_BUNDLE = DATA_ROOT / "2026-08-27-g2v3-i0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_reports(data_root: Path):
    """Yield (bundle_dir, report_path, report_dict) for every JSON report that
    declares a run_status anywhere under data_root."""
    for path in sorted(data_root.rglob("*report*.json")):
        try:
            obj = _load_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(obj, dict) and "run_status" in obj:
            yield path.parent, path, obj


def _input_manifest_aggregate(audit_gz: Path) -> tuple[str, int]:
    with gzip.open(audit_gz, "rt", encoding="utf-8") as fh:
        audit = json.load(fh)
    hashes = audit.get("bar_store_sha256")
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError("audit has no bar_store_sha256 map")
    text = "\n".join(f"{t} {hashes[t]}" for t in sorted(hashes))
    return hashlib.sha256(text.encode("utf-8")).hexdigest(), len(hashes)


def validate_gate_bundle(bundle_dir: Path, report_path: Path, report: dict,
                         repo_root: Path) -> list[str]:
    """Return every disagreement between a GATE_RUN report and its provenance.
    An empty list means the bundle is internally consistent."""
    problems: list[str] = []
    prov_path = bundle_dir / PROVENANCE_NAME
    if not prov_path.is_file():
        return [f"{bundle_dir}: GATE_RUN report without {PROVENANCE_NAME}"]
    try:
        prov = _load_json(prov_path)
    except ValueError as exc:
        return [f"{prov_path}: unparseable ({exc})"]
    if not isinstance(prov, dict):
        return [f"{prov_path}: not a JSON object"]

    def need(key: str):
        if key not in prov:
            problems.append(f"{prov_path}: missing key {key!r}")
            return None
        return prov[key]

    if not isinstance(need("run_id"), str) or not prov.get("run_id"):
        problems.append(f"{prov_path}: run_id must be a non-empty string")

    commit = need("frozen_source_commit")
    if not (isinstance(commit, str) and _HEX40.match(commit)):
        problems.append(f"{prov_path}: frozen_source_commit is not a 40-hex sha: {commit!r}")
    if not isinstance(need("clean_tree"), bool):
        problems.append(f"{prov_path}: clean_tree must be a bool")

    inv = need("invocation")
    if not (isinstance(inv, dict) and inv.get("command") and "--gate-run" in str(inv.get("command"))):
        problems.append(f"{prov_path}: invocation.command must record the --gate-run invocation")

    ts = need("timestamps_utc")
    if not (isinstance(ts, dict) and ts.get("start") and ts.get("end")):
        problems.append(f"{prov_path}: timestamps_utc needs start and end")

    # --- verdict cross-check -------------------------------------------------
    if need("report_run_status") != report.get("run_status"):
        problems.append(
            f"{prov_path}: report_run_status {prov.get('report_run_status')!r} != report {report.get('run_status')!r}")
    if need("gate_verdict") != report.get("gate_verdict"):
        problems.append(
            f"{prov_path}: gate_verdict {prov.get('gate_verdict')!r} != report {report.get('gate_verdict')!r}")

    # --- output hashes --------------------------------------------------------
    outputs = need("outputs")
    audit_path: Path | None = None
    if isinstance(outputs, dict):
        for key in ("report", "audit"):
            entry = outputs.get(key)
            if not (isinstance(entry, dict) and entry.get("path") and entry.get("sha256")):
                problems.append(f"{prov_path}: outputs.{key} needs path + sha256")
                continue
            target = bundle_dir / entry["path"]
            if not target.is_file():
                problems.append(f"{prov_path}: outputs.{key} path missing: {target}")
                continue
            actual = _sha256(target)
            if actual != entry["sha256"]:
                problems.append(
                    f"{target.name}: sha256 mismatch (provenance {entry['sha256'][:12]}.., disk {actual[:12]}..)")
            if key == "report" and target.resolve() != report_path.resolve():
                problems.append(f"{prov_path}: outputs.report does not point at {report_path.name}")
            if key == "audit":
                audit_path = target
    else:
        problems.append(f"{prov_path}: outputs must be an object")

    # --- seed list ------------------------------------------------------------
    seed = need("seed_list")
    if isinstance(seed, dict) and seed.get("path"):
        seed_file = repo_root / seed["path"]
        if not seed_file.is_file():
            problems.append(f"{prov_path}: seed_list.path missing: {seed_file}")
        else:
            if _sha256(seed_file) != seed.get("sha256"):
                problems.append(f"{prov_path}: seed_list.sha256 does not match {seed['path']}")
            count = sum(1 for line in seed_file.read_text(encoding="utf-8").splitlines() if line.strip())
            if count != seed.get("count"):
                problems.append(f"{prov_path}: seed_list.count {seed.get('count')} != {count} names on disk")
    else:
        problems.append(f"{prov_path}: seed_list needs path/sha256/count")

    # --- code identity --------------------------------------------------------
    code = need("code")
    if isinstance(code, dict):
        for key in ("census_script", "design_doc"):
            entry = code.get(key)
            digest = entry.get("sha256") if isinstance(entry, dict) else None
            if not (isinstance(digest, str) and _HEX64.match(digest)):
                problems.append(f"{prov_path}: code.{key}.sha256 must be a 64-hex sha256")
            if isinstance(entry, dict) and entry.get("commit") != commit:
                problems.append(f"{prov_path}: code.{key}.commit != frozen_source_commit")
    else:
        problems.append(f"{prov_path}: code must be an object")

    params = need("frozen_parameters")
    if not (isinstance(params, dict) and params):
        problems.append(f"{prov_path}: frozen_parameters must be a non-empty object")
    elif params.get("h") != report.get("h"):
        problems.append(f"{prov_path}: frozen_parameters.h {params.get('h')!r} != report h {report.get('h')!r}")

    # --- input manifest aggregate ----------------------------------------------
    manifest = need("input_manifest")
    if isinstance(manifest, dict) and audit_path is not None and audit_path.is_file():
        try:
            agg, count = _input_manifest_aggregate(audit_path)
        except (OSError, ValueError) as exc:
            problems.append(f"{audit_path.name}: cannot recompute manifest aggregate ({exc})")
        else:
            if manifest.get("aggregate_sha256") != agg:
                problems.append(f"{prov_path}: input_manifest.aggregate_sha256 does not match the audit")
            if manifest.get("count") != count:
                problems.append(f"{prov_path}: input_manifest.count {manifest.get('count')} != {count}")
    elif not isinstance(manifest, dict):
        problems.append(f"{prov_path}: input_manifest must be an object")

    return problems


def _gate_reports(data_root: Path):
    return [(d, p, r) for d, p, r in _iter_reports(data_root) if r.get("run_status") == "GATE_RUN"]


# --------------------------------------------------------------------------- #
# committed bundles
# --------------------------------------------------------------------------- #

def test_known_gate_bundle_is_present_and_marked_gate_run():
    report = KNOWN_GATE_BUNDLE / "g2v3_stage_i0_report.json"
    assert report.is_file(), "the I-0 gate bundle must be committed"
    assert _load_json(report)["run_status"] == "GATE_RUN"
    assert (KNOWN_GATE_BUNDLE / PROVENANCE_NAME).is_file()


def test_every_committed_gate_run_bundle_has_agreeing_provenance():
    gate = _gate_reports(DATA_ROOT)
    assert gate, "no GATE_RUN report found under doc/research/data -- test would be vacuous"
    problems = []
    for bundle_dir, report_path, report in gate:
        problems.extend(validate_gate_bundle(bundle_dir, report_path, report, REPO))
    assert not problems, "\n".join(problems)


def test_known_gate_bundle_provenance_pins_the_frozen_commit():
    prov = _load_json(KNOWN_GATE_BUNDLE / PROVENANCE_NAME)
    assert prov["frozen_source_commit"] == "f3d5bf7bd75ffa9c0fb59f8c3bfa98fa509e8779"
    assert prov["run_id"] == "i0-gate-20260829-f3d5bf7b"
    assert prov["gate_verdict"] == "PASS"
    assert prov["clean_tree"] is True


def test_development_only_reports_never_carry_gate_run_provenance():
    seen_dev = False
    for bundle_dir, report_path, report in _iter_reports(DATA_ROOT):
        if report.get("run_status") == "GATE_RUN":
            continue
        seen_dev = True
        assert report.get("gate_verdict") is None, (
            f"{report_path}: a {report.get('run_status')} report must not carry a gate verdict")
        prov_path = bundle_dir / PROVENANCE_NAME
        if prov_path.is_file():
            prov = _load_json(prov_path)
            assert prov.get("report_run_status") != "GATE_RUN", (
                f"{prov_path}: provenance claims GATE_RUN beside a {report.get('run_status')} report")
    assert seen_dev, "expected at least one DEVELOPMENT_ONLY report (the 2026-08-27 dev runs)"


def test_development_bundle_was_preserved_not_overwritten():
    report = _load_json(KNOWN_DEV_BUNDLE / "g2v3_stage_i0_report.json")
    assert report["run_status"] == "DEVELOPMENT_ONLY"
    assert report["gate_verdict"] is None
    assert not (KNOWN_DEV_BUNDLE / PROVENANCE_NAME).exists()


# --------------------------------------------------------------------------- #
# tamper detection on a copy
# --------------------------------------------------------------------------- #

@pytest.fixture
def bundle_copy(tmp_path: Path) -> tuple[Path, Path]:
    """A faithful copy of the committed gate bundle inside a fake repo root
    (seed list mirrored at its repo-relative path)."""
    fake_repo = tmp_path / "repo"
    rel = KNOWN_GATE_BUNDLE.relative_to(REPO)
    dst = fake_repo / rel
    shutil.copytree(KNOWN_GATE_BUNDLE, dst)
    prov = _load_json(dst / PROVENANCE_NAME)
    seed_rel = Path(prov["seed_list"]["path"])
    (fake_repo / seed_rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / seed_rel, fake_repo / seed_rel)
    return fake_repo, dst


def _validate_copy(fake_repo: Path, bundle: Path) -> list[str]:
    report_path = bundle / "g2v3_stage_i0_report.json"
    return validate_gate_bundle(bundle, report_path, _load_json(report_path), fake_repo)


def test_faithful_copy_validates(bundle_copy):
    fake_repo, bundle = bundle_copy
    assert _validate_copy(fake_repo, bundle) == []


def test_tampered_report_fails_hash_check(bundle_copy):
    fake_repo, bundle = bundle_copy
    report_path = bundle / "g2v3_stage_i0_report.json"
    report = _load_json(report_path)
    report["by_regime"]["BEAR"]["n_eff_adj"] = 999.0
    report_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    problems = _validate_copy(fake_repo, bundle)
    assert any("g2v3_stage_i0_report.json: sha256 mismatch" in p for p in problems), problems


def test_tampered_audit_fails_hash_and_manifest_check(bundle_copy):
    fake_repo, bundle = bundle_copy
    audit_path = bundle / "g2v3_stage_i0_audit.json.gz"
    with gzip.open(audit_path, "rt", encoding="utf-8") as fh:
        audit = json.load(fh)
    first = sorted(audit["bar_store_sha256"])[0]
    audit["bar_store_sha256"][first] = "0" * 64
    with gzip.open(audit_path, "wt", encoding="utf-8") as fh:
        json.dump(audit, fh)
    problems = _validate_copy(fake_repo, bundle)
    assert any("g2v3_stage_i0_audit.json.gz: sha256 mismatch" in p for p in problems), problems
    assert any("input_manifest.aggregate_sha256" in p for p in problems), problems


def test_verdict_disagreement_fails(bundle_copy):
    fake_repo, bundle = bundle_copy
    prov_path = bundle / PROVENANCE_NAME
    prov = _load_json(prov_path)
    prov["gate_verdict"] = "KILL"
    prov_path.write_text(json.dumps(prov, indent=1), encoding="utf-8")
    problems = _validate_copy(fake_repo, bundle)
    assert any("gate_verdict 'KILL' != report 'PASS'" in p for p in problems), problems


def test_missing_provenance_fails(bundle_copy):
    fake_repo, bundle = bundle_copy
    (bundle / PROVENANCE_NAME).unlink()
    problems = _validate_copy(fake_repo, bundle)
    assert problems and "without provenance.json" in problems[0]


def test_short_commit_and_tampered_seed_fail(bundle_copy):
    fake_repo, bundle = bundle_copy
    prov_path = bundle / PROVENANCE_NAME
    prov = _load_json(prov_path)
    prov["frozen_source_commit"] = "f3d5bf7b"
    prov_path.write_text(json.dumps(prov, indent=1), encoding="utf-8")
    seed_file = fake_repo / prov["seed_list"]["path"]
    seed_file.write_text(seed_file.read_text(encoding="utf-8") + "\nZZZZ\n", encoding="utf-8")
    problems = _validate_copy(fake_repo, bundle)
    assert any("not a 40-hex sha" in p for p in problems), problems
    assert any("seed_list.sha256" in p for p in problems), problems
    assert any("seed_list.count" in p for p in problems), problems
