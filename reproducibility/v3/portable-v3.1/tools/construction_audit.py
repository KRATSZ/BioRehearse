"""Independently audit construction premises for the v3 mutation records.

This helper reads the immutable JSONL records and their source plans.  It does
not import either measured checker, mutate a plan, or rewrite a raw record.  It
only decides whether a construction label has the independent premise needed
for its denominator.  The resulting labels are written to a separate derived
audit file so that the original v3.1 freeze and the exploratory challenge stay
unchanged.

Examples::

    python3 benchmarks/v3/construction_audit.py --root /path/to/virtual-lab

The v3.1 and exploratory suites use the same source plans but have distinct
raw files and label vocabularies.  For transfer deletion the known-violation
premise requires a later use at the declared destination, in addition to a
cross-station transfer.  For resource replacement the new resource must be
outside the operation's declared candidates.  For time shifts the recorded
new start must be strictly before the actual predecessor end; this avoids
calling a clamped-to-zero shift a precedence violation.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable


PAPER_REL = Path("docs/paper/biofoundry-preprint")
RAW_REL = PAPER_REL / "source-data/v3"
PLAN_REL = PAPER_REL / "source-data/v2/repair/plans"
AUDIT_REL = PAPER_REL / "audit/v3"
V31_RAW_REL = RAW_REL / "mutations/mutants.jsonl"
CHALLENGE_RAW_REL = RAW_REL / "mutation-challenge.jsonl"
OUT_JSONL_REL = RAW_REL / "construction-audit-407-192.jsonl"
OUT_SUMMARY_REL = RAW_REL / "construction-audit-summary.json"

V31_KNOWN_LABELS = {
    "known_violation",
    "incompatible_device",
    "shift_time",
    "change_volume",
    "access_order",
    "intent_deadline",
}
CHALLENGE_KNOWN_LABELS = {
    "known_resource_mismatch",
    "known_precedence_violation",
    "protocol_quantity_mismatch",
    "known_access_violation",
    "known_violation",
}
ACCESS_CODES = {
    "ACCESS_CLOSED",
    "WRONG_LOCATION",
    "ACCESS_OPEN",
    "BUSY",
    "NOT_LOADED",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def locate_root(explicit: Path | None = None) -> Path:
    """Find a virtual-lab root without relying on a fixed parent depth."""

    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser().resolve())
    if os.environ.get("BIOFOUNDRY_VLAB"):
        candidates.append(Path(os.environ["BIOFOUNDRY_VLAB"]).expanduser().resolve())
    candidates.extend([Path.cwd().resolve(), Path(__file__).resolve()])
    for start in candidates:
        for place in (start, *start.parents):
            if (place / V31_RAW_REL).exists() and (place / PLAN_REL).exists():
                return place
    raise FileNotFoundError("Could not locate virtual-lab root; pass --root")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def plan_map(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    plans: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for path in sorted((root / PLAN_REL).glob("repair-*.json")):
        plan = json.loads(path.read_text())
        plans[plan["id"]] = plan
        paths[plan["id"]] = path
    return plans, paths


def first_transfer_pair(plan: dict[str, Any], task_id: str) -> tuple[int, int, dict[str, Any], dict[str, Any]] | None:
    """Return the original transfer start/finish pair for ``task_id``."""

    start_index = next(
        (
            index
            for index, event in enumerate(plan.get("events", []))
            if event.get("task_id") == task_id
            and event.get("kind") == "transfer"
            and event.get("phase") == "start"
        ),
        None,
    )
    if start_index is None:
        return None
    finish_index = next(
        (
            index
            for index in range(start_index + 1, len(plan.get("events", [])))
            if plan["events"][index].get("task_id") == task_id
            and plan["events"][index].get("kind") == "transfer"
            and plan["events"][index].get("phase") == "finish"
        ),
        None,
    )
    if finish_index is None:
        return None
    return start_index, finish_index, plan["events"][start_index], plan["events"][finish_index]


def later_use(plan: dict[str, Any], finish_index: int, moved: set[str]) -> dict[str, Any] | None:
    """Find the first later event that uses one of the moved containers.

    A later operation start is the usual material-use event.  Transfer starts
    are also retained as uses because they consume the carrier location.  The
    first matching event is evidence; no measured checker is called here.
    """

    for index, event in enumerate(plan.get("events", [])[finish_index + 1 :], finish_index + 1):
        if not moved.intersection(set(event.get("container_ids", []))):
            continue
        if event.get("phase") not in {"start", "liquid_complete"}:
            continue
        if event.get("kind") == "operation":
            required_station = event.get("resource")
        elif event.get("kind") == "transfer":
            required_station = event.get("source") if event.get("phase") == "start" else event.get("destination")
        else:
            required_station = None
        return {
            "event_index": index,
            "task_id": event.get("task_id"),
            "kind": event.get("kind"),
            "phase": event.get("phase"),
            "time_s": event.get("time_s"),
            "required_station": required_station,
            "resource": event.get("resource"),
            "source": event.get("source"),
            "destination": event.get("destination"),
            "container_ids": sorted(set(event.get("container_ids", [])) & moved),
        }
    return None


def transfer_premise(plan: dict[str, Any], task_id: str) -> dict[str, Any]:
    pair = first_transfer_pair(plan, task_id)
    if pair is None:
        return {
            "pair_found": False,
            "cross_station": None,
            "moved_container_ids": [],
            "first_later_use": None,
            "first_later_use_exists": False,
            "required_station": None,
            "destination_matches_required_station": False,
            "required_station_differs_from_source": False,
            "known_violation_premise": False,
            "equivalent_same_station_premise": False,
        }
    start_index, finish_index, start, finish = pair
    moved = set(start.get("container_ids", [])) | set(finish.get("container_ids", []))
    first = later_use(plan, finish_index, moved)
    source = start.get("source")
    destination = start.get("destination")
    required = first.get("required_station") if first else None
    cross_station = source != destination
    first_exists = first is not None
    # Destination matching is checked explicitly rather than inferred from a
    # cross-station transfer.  This is the construction audit requested for
    # the known-error denominator.
    destination_match = first_exists and required == destination
    required_differs = first_exists and required != source
    known = cross_station and destination_match and required_differs
    equivalent = (not cross_station) and source == destination
    return {
        "pair_found": True,
        "start_event_index": start_index,
        "finish_event_index": finish_index,
        "source": source,
        "destination": destination,
        "cross_station": cross_station,
        "moved_container_ids": sorted(moved),
        "first_later_use": first,
        "first_later_use_exists": first_exists,
        "required_station": required,
        "destination_matches_required_station": destination_match,
        "required_station_differs_from_source": required_differs,
        "known_violation_premise": known,
        "equivalent_same_station_premise": equivalent,
    }


def operation_row(plan: dict[str, Any], target: str) -> dict[str, Any] | None:
    return next((row for row in plan.get("rows", []) if row.get("id") == target), None)


def device_premise(plan: dict[str, Any], target: str, new_resource: str | None) -> dict[str, Any]:
    row = operation_row(plan, target)
    candidates = list(row.get("candidates", [])) if row else []
    old_resource = row.get("resource") if row else None
    return {
        "target_found": row is not None,
        "old_resource": old_resource,
        "new_resource": new_resource,
        "candidate_resources": candidates,
        "new_resource_in_candidates": new_resource in candidates if row else None,
        "resource_changed": new_resource != old_resource if row else False,
        "known_resource_mismatch_premise": bool(row) and new_resource != old_resource and new_resource not in candidates,
    }


def shift_premise(plan: dict[str, Any], target: str, new_start: Any, predecessor_id: str | None = None) -> dict[str, Any]:
    row = operation_row(plan, target)
    predecessor = operation_row(plan, predecessor_id) if predecessor_id else None
    if predecessor is None and row and row.get("depends_on"):
        predecessor = operation_row(plan, row["depends_on"][0])
    predecessor_end = predecessor.get("end_s") if predecessor else None
    try:
        actual_start = float(new_start)
        actual_end = float(predecessor_end) if predecessor_end is not None else None
        strict_before = actual_end is not None and actual_start < actual_end
    except (TypeError, ValueError):
        actual_start = None
        actual_end = None
        strict_before = False
    return {
        "target_found": row is not None,
        "predecessor": predecessor.get("id") if predecessor else predecessor_id,
        "predecessor_end_s": predecessor_end,
        "new_start_s": new_start,
        "actual_new_start_s": actual_start,
        "strictly_before_predecessor_end": strict_before,
        "known_precedence_violation_premise": strict_before,
    }


def volume_premise(parameters: dict[str, Any] | None) -> dict[str, Any]:
    parameters = parameters or {}
    old = parameters.get("old_volume_ul")
    new = parameters.get("new_volume_ul")
    try:
        changed = float(new) != float(old)
        source_exceeded = float(new) > float(old)
        negative = float(new) < 0
    except (TypeError, ValueError):
        changed = source_exceeded = negative = False
    return {
        "old_volume_ul": old,
        "new_volume_ul": new,
        "volume_changed": changed,
        "negative_volume": negative,
        "exceeds_recorded_source_volume": source_exceeded,
        "known_quantity_violation_premise": changed and (negative or source_exceeded),
    }


def access_premise(row: dict[str, Any]) -> dict[str, Any]:
    expected = row.get("asset_contract_expected_code")
    # These codes are produced by the contract's declared lifecycle
    # preconditions.  The measured `observed` field is deliberately not used
    # to establish the label premise.
    return {
        "asset_action_input": row.get("input_type") == "asset_action_probe",
        "asset_id_present": bool(row.get("asset_id")),
        "target_case": row.get("target"),
        "declared_contract_code": expected,
        "declared_code_is_known_access_precondition": expected in ACCESS_CODES,
        "known_access_violation_premise": row.get("input_type") == "asset_action_probe" and expected in ACCESS_CODES,
    }


def intent_premise(row: dict[str, Any]) -> dict[str, Any]:
    params = row.get("parameters") or {}
    expected = params.get("expected_deadline_s")
    actual = params.get("actual_deadline_s")
    return {
        "expected_deadline_s": expected,
        "actual_deadline_s": actual,
        "deadline_differs": expected != actual,
        "known_intent_mismatch_premise": expected is not None and actual is not None and expected != actual,
    }


def audit_row(
    row: dict[str, Any],
    plans: dict[str, dict[str, Any]],
    plan_hashes: dict[str, str],
    suite: str,
) -> dict[str, Any]:
    plan = plans.get(row.get("base_plan"))
    category = row.get("category")
    raw_label = row.get("oracle_label")
    premise: dict[str, Any]
    # Deadline diagnostics are external intent records and intentionally have
    # no compiled-plan identifier.  Access rows still bind to a base plan, but
    # their contract precondition is audited independently below.
    if category == "intent_deadline":
        premise = intent_premise(row)
        derived = "known_violation" if premise.get("known_intent_mismatch_premise") else "intent_mismatch_other_constraints_unlabelled"
    elif plan is None:
        premise = {"base_plan_found": False}
        derived = "unlabelled_missing_base_plan"
    elif category == "delete_transfer":
        premise = transfer_premise(plan, row.get("target"))
        if premise.get("known_violation_premise"):
            derived = "known_violation"
        elif premise.get("equivalent_same_station_premise"):
            derived = "equivalent_mutation"
        else:
            derived = "delete_transfer_other_constraints_unlabelled"
    elif category == "incompatible_device":
        params = row.get("parameters") or {}
        premise = device_premise(plan, row.get("target"), params.get("new_resource"))
        derived = "known_violation" if premise.get("known_resource_mismatch_premise") else "device_resource_other_constraints_unlabelled"
    elif category == "device_resource":
        params = row.get("parameters") or {}
        premise = device_premise(plan, row.get("target"), params.get("new_resource"))
        derived = "known_resource_mismatch" if premise.get("known_resource_mismatch_premise") else "candidate_compatible_resource_other_constraints_unlabelled"
    elif category in {"shift_time", "shift_offset"}:
        params = row.get("parameters") or {}
        premise = shift_premise(plan, row.get("target"), params.get("new_start_s"), params.get("predecessor"))
        if category == "shift_time":
            derived = "known_violation" if premise.get("known_precedence_violation_premise") else "shift_time_other_constraints_unlabelled"
        elif raw_label == "known_precedence_violation" and premise.get("known_precedence_violation_premise"):
            derived = "known_precedence_violation"
        else:
            derived = "nonnegative_precedence_offset_other_constraints_unlabelled"
    elif category == "change_volume":
        premise = volume_premise(row.get("parameters"))
        derived = "known_violation" if premise.get("known_quantity_violation_premise") else "volume_change_other_constraints_unlabelled"
    elif category == "volume_factor":
        premise = volume_premise(row.get("parameters"))
        # This exploratory family intentionally samples conservative and
        # expansive factors.  Its construction claim is a recipe change, not
        # a mass-balance violation; conservation is the measured layer and is
        # allowed to miss it.
        derived = "protocol_quantity_mismatch" if premise.get("volume_changed") else "protocol_quantity_change_other_constraints_unlabelled"
    elif category == "access_order":
        premise = access_premise(row)
        derived = "known_violation" if suite == "v31" and premise.get("known_access_violation_premise") else (
            "known_access_violation" if premise.get("known_access_violation_premise") else "access_order_other_constraints_unlabelled"
        )
    elif category == "control":
        premise = {"unchanged_control": True}
        derived = "equivalent_control"
    else:
        premise = {"category_audited": False}
        derived = "unlabelled_category_not_audited"

    return {
        "suite": suite,
        "record_id": row.get("mutation_id") or row.get("challenge_id"),
        "base_plan": row.get("base_plan"),
        "base_plan_sha256_recorded": row.get("base_plan_sha256"),
        "base_plan_sha256_actual": plan_hashes.get(row.get("base_plan")),
        "base_plan_hash_matches": (
            row.get("base_plan_sha256") == plan_hashes.get(row.get("base_plan"))
            if row.get("base_plan_sha256") is not None
            else None
        ),
        "category": category,
        "input_type": row.get("input_type"),
        "raw_oracle_label": raw_label,
        "derived_oracle_label": derived,
        "raw_label_preserved": raw_label == derived,
        "raw_layers": row.get("layers"),
        "raw_observed": row.get("observed"),
        "parameters": row.get("parameters"),
        "construction_premise": premise,
    }


def count_labels(rows: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(collections.Counter(row.get(field) for row in rows).items()))


def layer_union(row: dict[str, Any]) -> bool:
    return any(value is True for value in (row.get("raw_layers") or {}).values())


def counts_by_suite_category(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for suite in sorted({row["suite"] for row in rows}):
        result[suite] = {}
        for category in sorted({row["category"] for row in rows if row["suite"] == suite}):
            group = [row for row in rows if row["suite"] == suite and row["category"] == category]
            raw_known = [row for row in group if row["raw_oracle_label"] in (V31_KNOWN_LABELS if suite == "v31" else CHALLENGE_KNOWN_LABELS)]
            derived_known = [row for row in group if row["derived_oracle_label"] in (V31_KNOWN_LABELS if suite == "v31" else CHALLENGE_KNOWN_LABELS)]
            result[suite][category] = {
                "n": len(group),
                "raw_labels": count_labels(group, "raw_oracle_label"),
                "derived_labels": count_labels(group, "derived_oracle_label"),
                "raw_known_denominator": len(raw_known),
                "derived_known_denominator": len(derived_known),
                "construction_premise_failures_among_raw_known": sum(not row["raw_label_preserved"] for row in raw_known),
                "union_detected_raw_layers": sum(layer_union(row) for row in group),
                "derived_known_detected_union": sum(layer_union(row) for row in derived_known),
            }
    return result


def build_summary(root: Path, rows: list[dict[str, Any]], plans: dict[str, dict[str, Any]], plan_paths: dict[str, Path], helper: Path) -> dict[str, Any]:
    raw_files = [root / V31_RAW_REL, root / CHALLENGE_RAW_REL]
    plan_entries = [
        {
            "id": plan_id,
            "path": str(path.relative_to(root)),
            "sha256": sha256(path),
        }
        for plan_id, path in sorted(plan_paths.items())
    ]
    return {
        "schema": "biofoundry.v3.construction-audit/1",
        "status": "complete",
        "construction_audit_is_derived": True,
        "raw_records_unchanged": True,
        "suites": {"v31": 407, "exploratory": 192, "total": len(rows)},
        "counts_by_suite_category": counts_by_suite_category(rows),
        "raw_label_counts": {
            "v31": count_labels([row for row in rows if row["suite"] == "v31"], "raw_oracle_label"),
            "exploratory": count_labels([row for row in rows if row["suite"] == "exploratory"], "raw_oracle_label"),
        },
        "derived_label_counts": {
            "v31": count_labels([row for row in rows if row["suite"] == "v31"], "derived_oracle_label"),
            "exploratory": count_labels([row for row in rows if row["suite"] == "exploratory"], "derived_oracle_label"),
        },
        "source_sha256": {
            "construction_audit.py": sha256(helper),
            "v31_raw": sha256(root / V31_RAW_REL),
            "exploratory_raw": sha256(root / CHALLENGE_RAW_REL),
            "mutation_freeze": sha256(root / RAW_REL / "mutation-freeze.json"),
            "code_review": sha256(root / AUDIT_REL / "VALIDATION_CODE_REVIEW.json"),
        },
        "source_plan_hashes": plan_entries,
        "audit_rules": {
            "delete_transfer_known": "cross_station AND first_later_use_exists AND first_later_use.required_station == original_destination AND first_later_use.required_station != original_source",
            "delete_transfer_equivalent": "original_source == original_destination",
            "device_known": "new_resource != original_resource AND new_resource not in task.candidates",
            "shift_known": "recorded_new_start_s < actual_predecessor.end_s",
            "volume_known": "recorded_new_volume != old_volume AND (new_volume < 0 OR new_volume > old_volume)",
            "access_known": "declared asset-contract precondition code is one of the contract lifecycle rejection codes; Workflow.act observation is not used as the oracle",
            "intent_known": "recorded actual deadline differs from recorded expected deadline",
        },
        "negative_results_retained": True,
        "raw_known_labels_are_not_retroactively_rewritten": True,
        "run": {
            "command": "python3 docs/paper/biofoundry-preprint/benchmarks/v3/construction_audit.py --root /path/to/virtual-lab",
            "python": os.sys.executable,
        },
        "notes": [
            "This audit is independent of the measured schedule, mass-balance, material-location and asset-contract checkers: it reads source plans and predeclared record parameters only.",
            "The derived label is the denominator used after construction-audit review; raw JSONL and the original v3.1 freeze remain immutable.",
            "Asset-action access rows are contract probes. They do not turn compiled portfolio rows into fifth-layer plan passes.",
            "The exploratory equivalent-resource and nonnegative-time labels remain unlabelled for whole-plan validity; they are not false-positive controls.",
        ],
    }


def run(root: Path) -> dict[str, Any]:
    plans, plan_paths = plan_map(root)
    plan_hashes = {plan_id: sha256(path) for plan_id, path in plan_paths.items()}
    v31 = read_jsonl(root / V31_RAW_REL)
    exploratory = read_jsonl(root / CHALLENGE_RAW_REL)
    audited = [audit_row(row, plans, plan_hashes, "v31") for row in v31]
    audited.extend(audit_row(row, plans, plan_hashes, "exploratory") for row in exploratory)
    if len(v31) != 407 or len(exploratory) != 192:
        raise RuntimeError(f"Unexpected input counts: v3.1={len(v31)}, exploratory={len(exploratory)}")
    mismatched_v31_plans = [
        row["record_id"]
        for row in audited
        if row["suite"] == "v31" and row["base_plan_sha256_recorded"] is not None and not row["base_plan_hash_matches"]
    ]
    if mismatched_v31_plans:
        raise RuntimeError("v3.1 base-plan hash mismatch: " + ", ".join(mismatched_v31_plans))
    out_jsonl = root / OUT_JSONL_REL
    out_summary = root / OUT_SUMMARY_REL
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w") as handle:
        for row in audited:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    summary = build_summary(root, audited, plans, plan_paths, Path(__file__).resolve())
    out_summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "summary": str(out_summary),
        "records": len(audited),
        "v31": count_labels([row for row in audited if row["suite"] == "v31"], "derived_oracle_label"),
        "exploratory": count_labels([row for row in audited if row["suite"] == "exploratory"], "derived_oracle_label"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None, help="virtual-lab root; inferred when omitted")
    args = parser.parse_args()
    root = locate_root(args.root)
    print(json.dumps(run(root), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
