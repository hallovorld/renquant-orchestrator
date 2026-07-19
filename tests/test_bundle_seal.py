"""P1 seal tests — first publication + flat views + rollback (SANDBOX only).

Every test runs against a tmp_path store with an injected stub pair
validator; NONE touches the live production store or the live serving pair
(AC4 migration P1; RFC RenQuant#492 §2.3/§2.6/§2.7, census §6). The seal
CODE is what these prove executable — the live cutover is operator-gated.
"""
from __future__ import annotations

import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from renquant_artifacts.bundle_schema import sha256_hex
from renquant_artifacts.bundle_store import (
    BundleReadRefusedError,
    BundleStore,
    BundleValidationError,
)
from renquant_orchestrator import bundle_seal
from renquant_orchestrator.bundle_seal import (
    CALIBRATOR_MEMBER,
    PANEL_MEMBER,
    SEAL_TOOL,
    VIEW_MODE,
    RunBundleProvenance,
    SealError,
    extract_bindings,
    regenerate_flat_views,
    seal_serving_pair,
)


# --------------------------------------------------------------------------
# fixtures / helpers (all synthetic JSON — the live pair is never read)
# --------------------------------------------------------------------------


class _TickingClock:
    """One second per call so bundles published in the same test never
    collide on ``created_at`` / bundle_id."""

    def __init__(self) -> None:
        self.now = datetime(2026, 7, 18, 3, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _accept_all(_manifest, _member_paths):
    return None  # store seam: None => pass


def _reject_all(_manifest, _member_paths):
    return False  # store seam: False => reject


def _make_store(root: Path, validator=_accept_all, **kwargs) -> BundleStore:
    kwargs.setdefault("local_mount_guard", lambda _p: (True, "test-injected"))
    kwargs.setdefault("clock", _TickingClock())
    return BundleStore(root, pair_validator=validator, **kwargs)


def _panel_bytes(tag: str = "a", verdict: str = "PASS") -> bytes:
    return (
        json.dumps(
            {
                "kind": "panel_ltr_xgb",
                "wf_gate_metadata": {"verdict": verdict, "as_of": "2026-07-14"},
                "model_content_fingerprint": "scorerfp" + tag,
                "booster_raw_json": "{" + tag * 8 + "}",
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _calibrator_bytes(tag: str = "a") -> bytes:
    return (
        json.dumps(
            {
                "kind": "global_panel_calibration",
                "metadata": {"scorer_model_content_fingerprint": "scorerfp" + tag},
                "spline_x": [0.0, 0.5, 1.0],
            },
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _write_pair(dirpath: Path, tag: str = "a", verdict: str = "PASS") -> tuple[Path, Path]:
    dirpath.mkdir(parents=True, exist_ok=True)
    panel = dirpath / PANEL_MEMBER
    calibrator = dirpath / CALIBRATOR_MEMBER
    panel.write_bytes(_panel_bytes(tag, verdict))
    calibrator.write_bytes(_calibrator_bytes(tag))
    return panel, calibrator


def _breakglass_auth() -> dict:
    return {
        "tool": "bundle_breakglass",
        "tool_version": "1.0.0",
        "actor": {"os_user": "tester", "operator": "renhao"},
        "source": {"incident_ref": "P1-ROLLBACK-TEST"},
        "inputs": {"reason": "restore-prior-generation"},
    }


# --------------------------------------------------------------------------
# 1. first-publication end-to-end
# --------------------------------------------------------------------------


def test_first_publication_end_to_end(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    panel, calibrator = _write_pair(tmp_path / "src")
    views = tmp_path / "views"
    views.mkdir()
    store = _make_store(root)

    result = seal_serving_pair(
        store,
        panel_path=panel,
        calibrator_path=calibrator,
        operator="renhao",
        flat_view_dir=views,
    )

    # generation 1, genesis bundle
    assert result.generation == 1
    prov = result.provenance
    assert isinstance(prov, RunBundleProvenance)
    assert len(prov.manifest_digest) == 64

    # run bundle records {bundle_id, digest, generation, member digests}
    panel_raw = panel.read_bytes()
    cal_raw = calibrator.read_bytes()
    assert prov.member_digests[PANEL_MEMBER] == {
        "sha256": sha256_hex(panel_raw),
        "bytes": len(panel_raw),
    }
    assert prov.member_digests[CALIBRATOR_MEMBER] == {
        "sha256": sha256_hex(cal_raw),
        "bytes": len(cal_raw),
    }

    # operation log: PREPARE precedes ACTIVATE and ACTIVATE is bound to it
    ops = store.read_operations()
    kinds = [r["record"] for r in ops if r.get("record") in ("PREPARE", "ACTIVATE")]
    assert kinds == ["PREPARE", "ACTIVATE"]
    prepare = next(r for r in ops if r["record"] == "PREPARE")
    activate = next(r for r in ops if r["record"] == "ACTIVATE")
    assert prepare["generation"] == 1 and prepare["bundle_id"] == result.bundle_id
    assert activate["generation"] == 1 and activate["bundle_id"] == result.bundle_id
    # ACTIVATE binds to the exact PREPARE line (activation-audit invariant)
    prepare_line = (
        json.dumps(prepare, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    assert activate["prepare_sha256"] == sha256_hex(prepare_line)

    # reader serves generation 1, byte-identical members, genesis parent
    with store.resolve_active() as resolved:
        assert resolved.generation == 1
        assert resolved.bundle_id == result.bundle_id
        assert resolved.manifest.parent_bundle is None
        assert resolved.manifest.manifest_digest == prov.manifest_digest
        assert resolved.read_member(PANEL_MEMBER) == panel_raw
        assert resolved.read_member(CALIBRATOR_MEMBER) == cal_raw

    # authorization stamped by the seal tool (not a restamp-class tool)
    assert prepare["authorization"]["tool"] == SEAL_TOOL
    assert prepare["authorization"]["actor"]["operator"] == "renhao"


def test_prepare_is_durable_before_the_active_flip(tmp_path):
    """Kill-inject at step 8 (ACTIVE.tmp written, before the step-9 rename):
    the PREPARE record is already fsync'd, but ACTIVE never flips."""
    root = tmp_path / "store"
    root.mkdir()
    panel, calibrator = _write_pair(tmp_path / "src")

    class _Boom(Exception):
        pass

    def crash(label: str) -> None:
        if label == "step8:active-tmp-written":
            raise _Boom()

    store = _make_store(root, crash_hook=crash)
    with pytest.raises(_Boom):
        seal_serving_pair(
            store,
            panel_path=panel,
            calibrator_path=calibrator,
            operator="renhao",
            regenerate_views=False,
        )

    ops = store.read_operations()
    prepares = [r for r in ops if r.get("record") == "PREPARE"]
    activates = [r for r in ops if r.get("record") == "ACTIVATE"]
    assert len(prepares) == 1 and prepares[0]["generation"] == 1  # durable before flip
    assert activates == []  # the flip never happened
    assert not (root / "ACTIVE").exists()  # ACTIVE pointer not created


# --------------------------------------------------------------------------
# 2. flat-view regeneration: 0444 + byte-identical
# --------------------------------------------------------------------------


def test_flat_view_is_read_only_and_byte_identical(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    panel, calibrator = _write_pair(tmp_path / "src")
    views = tmp_path / "views"
    views.mkdir()
    store = _make_store(root)

    result = seal_serving_pair(
        store,
        panel_path=panel,
        calibrator_path=calibrator,
        operator="renhao",
        flat_view_dir=views,
    )

    assert set(result.view_paths) == {PANEL_MEMBER, CALIBRATOR_MEMBER}
    with store.resolve_active() as resolved:
        for name, view_path in result.view_paths.items():
            assert view_path == views / name
            mode = stat.S_IMODE(view_path.stat().st_mode)
            assert mode == VIEW_MODE == 0o444  # read-only view
            # byte-identical to the bundle member a flat-path reader would load
            assert view_path.read_bytes() == resolved.read_member(name)


def test_view_default_dir_is_the_panel_directory(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    src = tmp_path / "src"
    panel, calibrator = _write_pair(src)
    panel_original = panel.read_bytes()
    store = _make_store(root)

    result = seal_serving_pair(
        store, panel_path=panel, calibrator_path=calibrator, operator="renhao"
    )
    # default flat_view_dir == the panel's own directory (the cutover shape)
    assert result.view_paths[PANEL_MEMBER] == src / PANEL_MEMBER
    assert stat.S_IMODE((src / PANEL_MEMBER).stat().st_mode) == 0o444
    # regenerated view is byte-identical to what was sealed
    assert (src / PANEL_MEMBER).read_bytes() == panel_original


# --------------------------------------------------------------------------
# 3. reader during a flip sees a consistent generation
# --------------------------------------------------------------------------


def test_reader_during_flip_sees_consistent_generation(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    panel_a, cal_a = _write_pair(tmp_path / "srcA", tag="a")
    panel_b, cal_b = _write_pair(tmp_path / "srcB", tag="b")
    store = _make_store(root)

    seal_serving_pair(
        store, panel_path=panel_a, calibrator_path=cal_a, operator="renhao",
        regenerate_views=False,
    )
    # a reader that resolves BEFORE the next flip
    reader = store.resolve_active()
    try:
        assert reader.generation == 1
        assert reader.read_member(PANEL_MEMBER) == panel_a.read_bytes()

        # a later publication flips ACTIVE to generation 2
        seal_serving_pair(
            store, panel_path=panel_b, calibrator_path=cal_b, operator="renhao",
            require_genesis=False, regenerate_views=False,
        )

        # the held-open reader still sees a CONSISTENT generation 1
        assert reader.generation == 1
        assert reader.read_member(PANEL_MEMBER) == panel_a.read_bytes()

        # a fresh reader sees a consistent generation 2
        with store.resolve_active() as reader2:
            assert reader2.generation == 2
            assert reader2.read_member(PANEL_MEMBER) == panel_b.read_bytes()
    finally:
        reader.close()


# --------------------------------------------------------------------------
# 3b. flat-view pair-atomicity: no legacy reader ever sees a MIXED pair
#     (the 2026-07-16 orphaned calibrator<->scorer binding incident class)
# --------------------------------------------------------------------------


def _read_flat_pair_binding(flat_dir: Path) -> tuple[str, str]:
    """A LEGACY flat-path reader: load BOTH flat serving files DIRECTLY from
    their fixed paths (NOT via ``store.resolve_active``) and return
    ``(panel_scorer_fingerprint, calibrator_scorer_binding)``.

    A consistent serving pair has these EQUAL. A mixed pair (new panel + old
    calibrator, or the reverse) makes them DIFFER — that is exactly the
    orphaned calibrator<->scorer binding GOAL-5 AC4 exists to eliminate. This
    reader is the compatibility surface the flat views claim to protect.
    """
    panel = json.loads((flat_dir / PANEL_MEMBER).read_bytes().decode("utf-8"))
    calibrator = json.loads((flat_dir / CALIBRATOR_MEMBER).read_bytes().decode("utf-8"))
    return (
        panel["model_content_fingerprint"],
        calibrator["metadata"]["scorer_model_content_fingerprint"],
    )


def test_flat_view_refuses_changed_content_and_leaves_pair_untouched(tmp_path):
    """The non-atomic two-file flat cutover REFUSES a changing pair before a
    single byte is written, so a legacy reader can never observe a mixed pair
    (deferred: the pair-atomic changing-content publisher, AC4 P2/P3)."""
    root = tmp_path / "store"
    root.mkdir()
    panel_a, cal_a = _write_pair(tmp_path / "srcA", tag="a")
    panel_b, cal_b = _write_pair(tmp_path / "srcB", tag="b")
    flat = tmp_path / "flat"
    flat.mkdir()
    store = _make_store(root)

    # genesis seal materializes flat pair A (byte-identical to gen-1 members)
    seal_serving_pair(
        store, panel_path=panel_a, calibrator_path=cal_a, operator="renhao",
        flat_view_dir=flat,
    )
    assert _read_flat_pair_binding(flat) == ("scorerfpa", "scorerfpa")

    # a later promote flips the STORE to a CHANGED pair B (no flat regen)
    seal_serving_pair(
        store, panel_path=panel_b, calibrator_path=cal_b, operator="renhao",
        require_genesis=False, regenerate_views=False,
    )

    # regenerating the flat views for the changed active pair (B over A) is
    # REFUSED — the non-atomic path is scoped to byte-identical content
    with store.resolve_active() as resolved:
        assert resolved.read_member(PANEL_MEMBER) == panel_b.read_bytes()
        with pytest.raises(SealError, match="CHANGE the served content"):
            regenerate_flat_views(resolved, flat)

    # the flat pair is untouched and still CONSISTENT (all-A): no mixed pair,
    # no partial write, no leftover tmp view file
    assert _read_flat_pair_binding(flat) == ("scorerfpa", "scorerfpa")
    assert (flat / PANEL_MEMBER).read_bytes() == panel_a.read_bytes()
    assert (flat / CALIBRATOR_MEMBER).read_bytes() == cal_a.read_bytes()
    assert [p.name for p in flat.iterdir() if p.name.startswith(".")] == []


def test_crash_between_the_two_view_writes_never_exposes_a_mixed_pair(tmp_path):
    """Fault injection: a crash BETWEEN the two flat-view replaces on the
    byte-identical (genesis / no-op refresh) path — the only path this P1
    publisher ever runs — can never leave a mixed pair. A legacy flat-path
    reader reading both files sees an all-old-or-all-new (here: consistent)
    pair, never new-panel + old-calibrator."""
    root = tmp_path / "store"
    root.mkdir()
    panel_a, cal_a = _write_pair(tmp_path / "srcA", tag="a")
    flat = tmp_path / "flat"
    flat.mkdir()
    store = _make_store(root)

    # genesis seal materializes flat pair A (byte-identical to gen-1 members)
    seal_serving_pair(
        store, panel_path=panel_a, calibrator_path=cal_a, operator="renhao",
        flat_view_dir=flat,
    )

    class _Boom(Exception):
        pass

    # panel-ltr sorts before panel-rank-calibration, so this crash lands in
    # the exact window that would expose "new panel + old calibrator"
    def crash(label: str) -> None:
        if label == f"after-view-replace:{PANEL_MEMBER}":
            raise _Boom()

    with store.resolve_active() as resolved:
        with pytest.raises(_Boom):
            regenerate_flat_views(resolved, flat, crash_hook=crash)

    # cutover interrupted mid-pair, yet the legacy reader sees a CONSISTENT
    # pair (panel new-inode == A, calibrator old-inode == A) — never mixed
    fp_panel, fp_cal = _read_flat_pair_binding(flat)
    assert fp_panel == fp_cal == "scorerfpa"
    assert (flat / PANEL_MEMBER).read_bytes() == panel_a.read_bytes()
    assert (flat / CALIBRATOR_MEMBER).read_bytes() == cal_a.read_bytes()


# --------------------------------------------------------------------------
# 4. rollback restores prior serving behavior without artifact surgery
# --------------------------------------------------------------------------


def test_rollback_restores_prior_serving_without_surgery(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    panel_a, cal_a = _write_pair(tmp_path / "srcA", tag="a")
    panel_b, cal_b = _write_pair(tmp_path / "srcB", tag="b")
    flat = tmp_path / "flat"
    flat.mkdir()
    store = _make_store(root)

    gen1 = seal_serving_pair(
        store, panel_path=panel_a, calibrator_path=cal_a, operator="renhao",
        flat_view_dir=flat,
    )
    gen1_id = gen1.bundle_id
    # capture the gen-1 archived member bytes (to prove NO surgery later)
    gen1_member = (root / "bundles" / gen1_id / PANEL_MEMBER).read_bytes()

    # a later promote flips the STORE to gen 2 (pair B). The changing-content
    # flat cutover (A->B) is the pair-atomic publisher deferred to AC4 P2/P3,
    # so we publish through the store WITHOUT regenerating the flat compat
    # views (regenerate_views=False); the flat pair stays authoritative at A.
    seal_serving_pair(
        store, panel_path=panel_b, calibrator_path=cal_b, operator="renhao",
        require_genesis=False, regenerate_views=False,
    )
    assert (flat / PANEL_MEMBER).read_bytes() == panel_a.read_bytes()  # flat still A

    # revert: point ACTIVE back to the gen-1 bundle (break-glass rollback)
    rolled = store.rollback_to(gen1_id, authorization=_breakglass_auth())
    assert rolled.bundle_id == gen1_id
    assert rolled.generation == 3  # monotonic pointer; targets the gen-1 bundle

    with store.resolve_active() as resolved:
        assert resolved.bundle_id == gen1_id
        assert resolved.read_member(PANEL_MEMBER) == panel_a.read_bytes()
        # gen-1 members are byte-identical to the flat pair (still A) => the
        # regeneration is a content no-op and passes the pair-atomicity guard
        views = regenerate_flat_views(resolved, flat)

    # serving behavior restored: views byte-identical to the original pair A
    assert (flat / PANEL_MEMBER).read_bytes() == panel_a.read_bytes()
    assert stat.S_IMODE(views[PANEL_MEMBER].stat().st_mode) == 0o444
    # NO artifact surgery: the gen-1 bundle member is byte-identical throughout
    assert (root / "bundles" / gen1_id / PANEL_MEMBER).read_bytes() == gen1_member


def test_seal_does_not_mutate_the_source_pair(tmp_path):
    """P1 is additive: the source serving pair is read-only to the seal, so
    reverting the P1 commit leaves the flat pair authoritative (census §6)."""
    root = tmp_path / "store"
    root.mkdir()
    src = tmp_path / "src"
    panel, calibrator = _write_pair(src)
    panel_original = panel.read_bytes()
    cal_original = calibrator.read_bytes()
    views = tmp_path / "views"
    views.mkdir()
    store = _make_store(root)

    seal_serving_pair(
        store, panel_path=panel, calibrator_path=calibrator, operator="renhao",
        flat_view_dir=views,
    )
    assert panel.read_bytes() == panel_original  # source untouched
    assert calibrator.read_bytes() == cal_original


# --------------------------------------------------------------------------
# 5. validator-gating, genesis guard, verbatim bindings, CLI wiring
# --------------------------------------------------------------------------


def test_publish_is_validator_gated_rejection_aborts_cleanly(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    panel, calibrator = _write_pair(tmp_path / "src")
    views = tmp_path / "views"
    views.mkdir()
    store = _make_store(root, validator=_reject_all)

    with pytest.raises(BundleValidationError):
        seal_serving_pair(
            store, panel_path=panel, calibrator_path=calibrator, operator="renhao",
            flat_view_dir=views,
        )

    # aborted before the flip: no PREPARE/ACTIVATE, no ACTIVE, no views
    assert store.read_operations() == []
    assert not (root / "ACTIVE").exists()
    with pytest.raises(BundleReadRefusedError):
        store.resolve_active()
    assert list(views.iterdir()) == []


def test_require_genesis_refuses_a_second_seal(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    panel, calibrator = _write_pair(tmp_path / "src")
    store = _make_store(root)

    seal_serving_pair(
        store, panel_path=panel, calibrator_path=calibrator, operator="renhao",
        regenerate_views=False,
    )
    with pytest.raises(SealError, match="FIRST publication"):
        seal_serving_pair(
            store, panel_path=panel, calibrator_path=calibrator, operator="renhao",
            regenerate_views=False,
        )
    # explicit override republishes as generation 2
    again = seal_serving_pair(
        store, panel_path=panel, calibrator_path=calibrator, operator="renhao",
        require_genesis=False, regenerate_views=False,
    )
    assert again.generation == 2


def test_seal_requires_an_operator(tmp_path):
    root = tmp_path / "store"
    root.mkdir()
    panel, calibrator = _write_pair(tmp_path / "src")
    store = _make_store(root)
    with pytest.raises(SealError):
        seal_serving_pair(
            store, panel_path=panel, calibrator_path=calibrator, operator="",
            regenerate_views=False,
        )


def test_extract_bindings_copies_wf_gate_verdict_verbatim():
    # verbatim copy of the panel's stamped verdict — NOT a buy-admissibility
    # assertion (RFC §2.7). A FAIL verdict is copied through faithfully.
    bindings = extract_bindings(_panel_bytes(verdict="FAIL"), _calibrator_bytes())
    assert bindings["wf_gate_verdict"] == "FAIL"
    assert bindings["scorer_fingerprint"] == "scorerfpa"
    assert bindings["calibrator_scorer_binding"] == "scorerfpa"
    assert "seal_note" in bindings

    # an unstamped panel yields the sentinel, still a non-empty object
    unstamped = json.dumps({"kind": "x", "booster_raw_json": "{}"}).encode()
    bindings2 = extract_bindings(unstamped, _calibrator_bytes())
    assert bindings2["wf_gate_verdict"] == "UNSTAMPED"


def test_extract_bindings_derives_verdict_from_passed_and_carries_override():
    # the LIVE panel stamps the outcome as `passed`/override booleans, not a
    # `verdict` string — the seal reflects that verbatim (§2.7) and carries
    # the operator-override provenance into the bundle.
    panel = json.dumps(
        {
            "kind": "panel_ltr_xgb",
            "booster_raw_json": "{}",
            "config_fingerprint": "sha256:f8fb2259b",
            "wf_gate_metadata": {
                "passed": True,
                "gate_verdict_before_override": False,
                "operator_authorized_override": True,
                "override_reason": "freshness > strict gate",
                "diagnostic_only": True,
                "gate_version": 2,
            },
        }
    ).encode()
    bindings = extract_bindings(panel, _calibrator_bytes())
    assert bindings["wf_gate_verdict"] == "PASS"  # derived from passed=True
    assert bindings["wf_passed"] is True
    assert bindings["wf_gate_verdict_before_override"] is False
    assert bindings["wf_operator_authorized_override"] is True
    assert bindings["wf_override_reason"] == "freshness > strict gate"
    assert bindings["scorer_fingerprint"] == "sha256:f8fb2259b"

    failed = json.dumps(
        {"kind": "x", "booster_raw_json": "{}", "wf_gate_metadata": {"passed": False}}
    ).encode()
    assert extract_bindings(failed, _calibrator_bytes())["wf_gate_verdict"] == "FAIL"


def test_cli_main_uses_create_default_store(tmp_path, monkeypatch, capsys):
    """The production CLI path builds the store via create_default_store,
    so writer step-6 pair validation is wired by construction (validator
    cannot be silently omitted)."""
    root = tmp_path / "store"
    root.mkdir()
    panel, calibrator = _write_pair(tmp_path / "src")
    views = tmp_path / "views"
    views.mkdir()

    calls = {}

    def fake_factory(store_root, *, accept_legacy_stamps=None, **kw):
        calls["root"] = store_root
        calls["accept_legacy_stamps"] = accept_legacy_stamps
        return _make_store(root)

    monkeypatch.setattr(
        "renquant_artifacts.bundle_contract_binding.create_default_store",
        fake_factory,
    )
    rc = bundle_seal.main(
        [
            "--store-root", str(root),
            "--panel", str(panel),
            "--calibrator", str(calibrator),
            "--operator", "renhao",
            "--flat-view-dir", str(views),
        ]
    )
    assert rc == 0
    assert calls["root"] == str(root)
    assert calls["accept_legacy_stamps"] is None
    printed = json.loads(capsys.readouterr().out)
    assert printed["sealed"]["generation"] == 1
    assert set(printed["views"]) == {PANEL_MEMBER, CALIBRATOR_MEMBER}
