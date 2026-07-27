from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parent


def _load_audit_module():
    path = ROOT / "audit_cross_project_freshness.py"
    spec = importlib.util.spec_from_file_location("cross_project_freshness", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bundle_hash_is_line_ending_independent(tmp_path, monkeypatch):
    audit = _load_audit_module()
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    source = tmp_path / "source.yaml"
    source.write_bytes(b"alpha: 1\nbeta: 2\n")
    lf_hash = audit._bundle_sha256([source])

    source.write_bytes(b"alpha: 1\r\nbeta: 2\r\n")
    crlf_hash = audit._bundle_sha256([source])

    assert crlf_hash == lf_hash


def test_bundle_hash_detects_binary_changes(tmp_path, monkeypatch):
    audit = _load_audit_module()
    figure = tmp_path / "figure.png"
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    figure.write_bytes(b"first")
    first_hash = audit._bundle_sha256([figure])

    figure.write_bytes(b"second")
    second_hash = audit._bundle_sha256([figure])

    assert second_hash != first_hash
