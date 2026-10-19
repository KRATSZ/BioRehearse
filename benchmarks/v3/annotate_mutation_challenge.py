"""Add conservative labels to the exploratory mutation challenge.

The JSONL produced by ``mutation_challenge.py`` is retained byte-for-byte.
This derived annotation only renames two construction flags whose truth
cannot be decided by the mutation itself: a nonnegative time offset can still
violate another schedule constraint, and a candidate-compatible resource can
still alter duration or location assumptions.  They are therefore not
equivalence or false-positive labels in the derived report.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PAPER = ROOT / "docs" / "paper" / "biofoundry-preprint"
OUT = PAPER / "source-data" / "v3"
RAW = OUT / "mutation-challenge.jsonl"
ANNOTATED = OUT / "mutation-challenge-annotated.jsonl"
SUMMARY = OUT / "mutation-challenge-annotated-summary.json"

LABEL_MAP = {
    "equivalent_time_shift": "nonnegative_precedence_offset_other_constraints_unlabelled",
    "equivalent_resource": "candidate_compatible_resource_other_constraints_unlabelled",
}


def main():
    rows = [json.loads(line) for line in RAW.read_text().splitlines() if line.strip()]
    annotated = []
    for row in rows:
        original = row["oracle_label"]
        item = dict(row)
        item["oracle_label_original"] = original
        item["derived_oracle_label"] = LABEL_MAP.get(original, original)
        item["derived_label_semantics"] = (
            "construction flag only; later offsets may violate windows, resource overlap, deadlines or other constraints"
            if original == "equivalent_time_shift"
            else "construction flag only; candidate compatibility does not establish duration, geometry or location validity"
            if original == "equivalent_resource"
            else None
        )
        annotated.append(item)
    with ANNOTATED.open("w") as fh:
        for row in annotated:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    by_category = {}
    for category in sorted({row["category"] for row in annotated}):
        group = [row for row in annotated if row["category"] == category]
        layer = {}
        for name in ("intent", "schedule", "mass_balance", "material_location", "asset_contract"):
            values = [row["layers"][name] for row in group if row["layers"][name] is not None]
            layer[name] = {"detected": sum(bool(value) for value in values), "total": len(values), "not_applicable": len(group) - len(values)}
        by_category[category] = {"n": len(group), "layers": layer, "union_detected": sum(any(value is True for value in row["layers"].values()) for row in group)}

    label_counts = collections.Counter(row["derived_oracle_label"] for row in annotated)
    unlabelled = [row for row in annotated if row["derived_oracle_label"].endswith("other_constraints_unlabelled")]
    summary = {
        "schema": "biofoundry.v3.exploratory-mutation-challenge-annotated/1",
        "source_raw": str(RAW.relative_to(PAPER)),
        "raw_labels_preserved": True,
        "label_map": LABEL_MAP,
        "label_counts": dict(sorted(label_counts.items())),
        "by_category": by_category,
        "total": len(annotated),
        "union_detected": sum(any(value is True for value in row["layers"].values()) for row in annotated),
        "unlabelled_other_constraint_records": len(unlabelled),
        "unlabelled_other_constraint_detections": sum(any(value is True for value in row["layers"].values()) for row in unlabelled),
        "notes": [
            "The raw oracle_label field is preserved; derived_oracle_label is the publication-facing annotation.",
            "nonnegative_precedence_offset_other_constraints_unlabelled and candidate_compatible_resource_other_constraints_unlabelled are not equivalent-validity or false-positive labels.",
            "The exploratory challenge is separate from frozen v3.1 and is not a sensitivity estimate.",
        ],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
