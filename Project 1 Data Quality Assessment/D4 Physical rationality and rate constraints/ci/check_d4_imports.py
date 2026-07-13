"""Static checks for D4 dimension independence and diagnostic boundaries."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
SCANNED = (ROOT / "src" / "d4_physical", ROOT / "src" / "pipeline")
FORBIDDEN_IMPORT_PREFIXES = (
    "src.common.state_blackboard",
    "src.pipeline.d1_streaming_stub",
)
FORBIDDEN_TEXT = (
    "q_rate_override",
    "cooldown_triggered_by_d1",
    "veto_suppressed_by_cooldown",
    "d1_streaming_freshness",
)
FORBIDDEN_PATTERNS = (
    re.compile(r"\.rolling\([^)]*\)\.quantile\b"),
    re.compile(r"\.expanding\([^)]*\)\.quantile\b"),
)


def check_file(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    violations = []
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append((node.lineno, f"forbidden score dependency: {module}"))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    violations.append((node.lineno, f"forbidden score dependency: {alias.name}"))
    for line_no, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        for token in FORBIDDEN_TEXT:
            if token in lowered:
                violations.append((line_no, f"forbidden cross-dimension token: {token}"))
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(line):
                violations.append((line_no, f"forbidden dynamic threshold: {line.strip()}"))
    return violations


def main() -> int:
    violations = []
    files = [path for folder in SCANNED for path in folder.rglob("*.py")]
    for path in files:
        for line_no, message in check_file(path):
            violations.append((path.relative_to(ROOT), line_no, message))

    mapping = yaml.safe_load((ROOT / "configs" / "d4_mapping.yaml").read_text(encoding="utf-8"))
    weights = mapping["aggregation"]["weights"]
    if "Q_boundary" in weights:
        violations.append((Path("configs/d4_mapping.yaml"), 0, "Q_boundary must remain diagnostic-only"))
    if abs(sum(weights.values()) - 1.0) > 1e-12:
        violations.append((Path("configs/d4_mapping.yaml"), 0, "aggregation weights must sum to 1"))

    if violations:
        print("D4 contract check failed:")
        for path, line_no, message in violations:
            print(f"  {path}:{line_no}: {message}")
        return 1
    print(f"D4 contract check passed: {len(files)} source files scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
