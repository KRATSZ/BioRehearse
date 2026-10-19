"""Run the required source, alignment, font and collision gates for v3 figures."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
V3 = HERE.parent
PAPER = V3.parents[1]
TOOLS = PAPER / "reproducibility" / "figure-qa"
PYTHON = PAPER / ".venv" / "bin" / "python"


def _run(command: list[str], log_path: Path) -> tuple[int, str]:
    result = subprocess.run(command, capture_output=True, text=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    return result.returncode, result.stdout + result.stderr


def main() -> None:
    qa_dir = V3 / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    records = []
    source_files = sorted(HERE.glob("figure*.py"))
    for source in source_files:
        code, output = _run([str(PYTHON), str(TOOLS / "validate_figure.py"), str(source), "--json"], qa_dir / f"{source.stem}.static.log")
        records.append({"source": source.name, "static_exit": code})

    # Audit the six LaTeX-facing exports once.  fig1_system and
    # fig6_validation are source-stem compatibility aliases, so including
    # both stems would duplicate every collision/font result in the summary.
    canonical_stems = ["fig1_concept", "fig2_assets", "fig3_rehearsal", "fig4_language", "fig5_scheduling", "fig6_layers"]
    for stem in canonical_stems:
        pdf = V3 / f"{stem}.pdf"
        if not pdf.exists():
            records.append({"figure": pdf.name, "font_exit": 1, "collision_exit": 1, "alignment_verdict": "MISSING", "alignment_summary": {}})
            continue
        base = pdf.with_suffix("")
        font_code, _ = _run([str(PYTHON), str(TOOLS / "audit_pdf_text.py"), str(pdf), "--min-pt", "5.5", "--json"], qa_dir / f"{pdf.stem}.font.log")
        collision_code, _ = _run(
            [str(PYTHON), str(TOOLS / "audit_figure_collisions.py"), str(pdf), "--json-out", str(qa_dir / f"{pdf.stem}.collision.json")],
            qa_dir / f"{pdf.stem}.collision.log",
        )
        alignment_path = V3 / f"{pdf.stem}.alignment.json"
        alignment = json.loads(alignment_path.read_text(encoding="utf-8")) if alignment_path.exists() else {"verdict": "MISSING"}
        records.append(
            {
                "figure": pdf.name,
                "font_exit": font_code,
                "collision_exit": collision_code,
                "alignment_verdict": alignment.get("verdict"),
                "alignment_summary": alignment.get("summary", {}),
            }
        )
    (qa_dir / "qa-summary.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(records, indent=2, ensure_ascii=False))
    failures = [r for r in records if any(r.get(key, 0) not in (0, "PASS", "NOT APPLICABLE") for key in ("static_exit", "font_exit", "collision_exit", "alignment_verdict"))]
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
