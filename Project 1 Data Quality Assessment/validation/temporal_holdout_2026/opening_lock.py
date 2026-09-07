"""Content-authoritative freeze: fail closed on inference code/config/asset drift."""
import json
from pathlib import Path

from runtime import PROJECT, OFFICIAL, OUTPUT, content_hash, sha256


def verify_lock(*, private_inputs=False):
    path = OUTPUT / "T0_opening_lock.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    gate = json.loads((OUTPUT / "opening_gate.json").read_text(encoding="utf-8"))
    if sha256(path) != gate.get("opening_lock_sha256"):
        raise RuntimeError("Opening lock identity differs from authorized gate")
    for name, expected in data["code_config_assets"].items():
        actual = (PROJECT / name).resolve()
        if not actual.is_relative_to(PROJECT.resolve()) or content_hash(actual) != expected:
            raise RuntimeError(f"Frozen inference changed: {name}")
    if private_inputs:
        for name, expected in data["private_official_inputs"].items():
            if sha256(OFFICIAL / name) != expected:
                raise RuntimeError(f"Private source identity changed: {name}")
    return data
