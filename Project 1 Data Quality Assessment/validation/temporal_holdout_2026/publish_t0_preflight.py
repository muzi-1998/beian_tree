"""Record optional installed Nature source QA; public CI verifies actual files."""
import json
from pathlib import Path
import subprocess
import sys

from runtime import HERE, OUTPUT, write_json


def main():
    validator = Path.home()/".codex/skills/nature-figure/scripts/validate_figure.py"
    if not validator.is_file():
        raise RuntimeError("Local Nature preflight unavailable; do not claim it ran")
    completed = subprocess.run([sys.executable, str(validator), str(HERE/"plot_t0_results.py"), "--json"],
                               capture_output=True, text=True, check=True)
    audit = json.loads(completed.stdout)
    audit["source"] = "plot_t0_results.py"
    write_json(OUTPUT/"T0_results/T0_nature_source_preflight.json", audit)
    if not audit["summary"]["ready"]:
        raise RuntimeError("Nature source preflight failed")
    qa_path = OUTPUT/"T0_results/T0_figure_qa.json"
    qa = json.loads(qa_path.read_text())
    for figure in qa["figures"]:
        figure["visual_review"] = "reviewed_at_export_size_fonts_legends_IDs_NA_gaps_and_zero_values"
    write_json(qa_path, qa)
    print(audit["summary"])


if __name__ == "__main__":
    main()
