"""Exploratory mutation challenge kept separate from the frozen v3.1 suite.

The v3.1 result is immutable after its input freeze.  This challenge probes
less deterministic alternatives that are useful for finding checker misses:
moderate protocol-volume changes, candidate and non-candidate resources,
positive and negative precedence offsets, transfer deletion, and contract
access-order faults.  Its labels are construction labels (protocol mismatch,
precedence violation, or an explicitly equivalent change); they are not
treated as a sensitivity estimate or merged into the frozen headline result.

Run from the repository root with::

    python benchmarks/v3/mutation_challenge.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PAPER = ROOT / "docs" / "paper" / "biofoundry-preprint"
OUT = PAPER / "source-data" / "v3"
SEED = 20261021
COUNTS = {
    "volume_factor": 48,
    "device_resource": 48,
    "shift_offset": 48,
    "delete_transfer": 24,
    "access_order": 24,
}
FACTORS = (0.5, 0.8, 1.2, 1.5)
OFFSETS = (-600, -60, -1, 1, 60, 600)
ACCESS_CASES = (
    "closed_door_load",
    "open_after_load_without_close",
    "wrong_origin_load",
    "unload_before_load",
    "open_while_running",
    "load_twice",
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_frozen_helpers():
    return load_module("biofoundry_v3_mutation_frozen_helpers", Path(__file__).with_name("mutation.py"))


def mutate_volume(plan, rng):
    q = copy.deepcopy(plan)
    events = [e for e in q["events"] if e.get("transfers")]
    event = events[rng.randrange(len(events))]
    transfer_index = rng.randrange(len(event["transfers"]))
    source, destination, old = event["transfers"][transfer_index]
    factor = FACTORS[rng.randrange(len(FACTORS))]
    new = float(old) * factor
    event["transfers"][transfer_index][2] = new
    return q, event["task_id"], "protocol_quantity_mismatch", {
        "source": source,
        "destination": destination,
        "old_volume_ul": old,
        "factor": factor,
        "new_volume_ul": new,
    }


def mutate_device(plan, catalog, rng):
    q = copy.deepcopy(plan)
    rows = [r for r in q["rows"] if r.get("kind") == "operation" and r.get("resource") not in ("operator",)]
    row = rows[rng.randrange(len(rows))]
    resources = [key for key, value in catalog["devices"].items() if value.get("selectable")]
    if "bench" not in resources:
        resources.append("bench")
    choices = [resource for resource in resources if resource != row.get("resource")]
    new_resource = choices[rng.randrange(len(choices))]
    old_resource = row["resource"]
    row["resource"] = new_resource
    equivalent = new_resource in row.get("candidates", [])
    return q, row["id"], "equivalent_resource" if equivalent else "known_resource_mismatch", {
        "old_resource": old_resource,
        "new_resource": new_resource,
        "candidate_resources": row.get("candidates", []),
        "candidate_equivalent": equivalent,
    }


def mutate_shift(plan, rng):
    q = copy.deepcopy(plan)
    rows = [r for r in q["rows"] if r.get("kind") == "operation" and r.get("depends_on")]
    row = rows[rng.randrange(len(rows))]
    predecessor = next(r for r in q["rows"] if r["id"] == row["depends_on"][0])
    offset = OFFSETS[rng.randrange(len(OFFSETS))]
    old_start = row["start_s"]
    duration = row["end_s"] - old_start
    row["start_s"] = max(0, predecessor["end_s"] + offset)
    row["end_s"] = row["start_s"] + duration
    row["process_start_s"] = row["start_s"] + row["load_s"]
    row["process_end_s"] = row["end_s"] - row["clean_s"]
    for reservation in q["reservations"]:
        if reservation["task_id"] == row["id"]:
            delta = row["start_s"] - old_start
            reservation["start_s"] += delta
            reservation["end_s"] += delta
    label = "known_precedence_violation" if offset < 0 else "equivalent_time_shift"
    return q, row["id"], label, {
        "predecessor": predecessor["id"],
        "offset_from_predecessor_end_s": offset,
        "old_start_s": old_start,
        "new_start_s": row["start_s"],
    }


def plan_layers(scorer, catalog, plan):
    schedule = scorer.score(plan, plan["graph"], catalog)
    state = scorer.states(plan)
    return {
        "intent": None,
        "schedule": not schedule.get("valid", False),
        "mass_balance": not state.get("mass_valid", False),
        "material_location": not state.get("material_valid", False),
        "asset_contract": None,
    }, {
        "schedule_violations": schedule.get("violations", []),
        "mass_issues": len(state.get("mass_issues", [])),
        "location_issues": len(state.get("location_issues", [])),
    }


def run():
    frozen = load_frozen_helpers()
    scorer, catalog, plans = frozen.load_v2()
    validation = load_module("biofoundry_v3_validation_challenge", PAPER / "benchmarks" / "v3" / "validation.py")
    protocol, _runner, access_rows = validation.access_bindings()
    access_map = {row["asset_id"]: protocol.Library(frozen.EXPORT).select(asset_id=row["asset_id"]) for row in access_rows}
    rng = random.Random(SEED)
    records = []
    for category, count in COUNTS.items():
        for _ in range(count):
            local_seed = rng.randrange(1 << 31)
            local = random.Random(local_seed)
            plan = plans[rng.randrange(len(plans))]
            record = {
                "challenge_id": f"v3-challenge-{len(records):04d}",
                "seed": local_seed,
                "category": category,
                "base_plan": plan["id"],
                "input_type": "asset_action_probe" if category == "access_order" else "compiled_plan_mutation",
                "oracle_independent_of_checker": True,
                "layers": {"intent": None, "schedule": None, "mass_balance": None, "material_location": None, "asset_contract": None},
            }
            if category == "access_order":
                asset_id = sorted(access_map)[local.randrange(len(access_map))]
                case_name = ACCESS_CASES[local.randrange(len(ACCESS_CASES))]
                outcome = frozen.run_access_mutation(protocol, access_map[asset_id], case_name)
                record.update({
                    "asset_id": asset_id,
                    "target": case_name,
                    "oracle_label": "known_access_violation",
                    "asset_contract_expected_code": outcome["expected_code"],
                    "layers": {"intent": None, "schedule": None, "mass_balance": None, "material_location": None, "asset_contract": outcome["detected"]},
                    "observed": {"asset_contract_code": outcome["observed_code"], "state_unchanged": outcome["state_unchanged"]},
                })
            elif category == "volume_factor":
                mutated, target, label, parameters = mutate_volume(plan, local)
                layers, observed = plan_layers(scorer, catalog, mutated)
                record.update({"target": target, "oracle_label": label, "parameters": parameters, "layers": layers, "observed": observed})
            elif category == "device_resource":
                mutated, target, label, parameters = mutate_device(plan, catalog, local)
                layers, observed = plan_layers(scorer, catalog, mutated)
                record.update({"target": target, "oracle_label": label, "parameters": parameters, "layers": layers, "observed": observed})
            elif category == "shift_offset":
                mutated, target, label, parameters = mutate_shift(plan, local)
                layers, observed = plan_layers(scorer, catalog, mutated)
                record.update({"target": target, "oracle_label": label, "parameters": parameters, "layers": layers, "observed": observed})
            else:
                mutated, target, label, parameters = frozen.mutate_plan(plan, "delete_transfer", local)
                layers, observed = plan_layers(scorer, catalog, mutated)
                record.update({"target": target, "oracle_label": label, "parameters": parameters, "layers": layers, "observed": observed})
            records.append(record)

    OUT.mkdir(parents=True, exist_ok=True)
    jsonl = OUT / "mutation-challenge.jsonl"
    with jsonl.open("w") as fh:
        for row in records:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    expected_detection_labels = {
        "known_access_violation",
        "known_precedence_violation",
        "known_resource_mismatch",
        "known_violation",
        "protocol_quantity_mismatch",
    }
    detected_by_label = {}
    misses_by_label = {}
    for row in records:
        if row["oracle_label"] not in expected_detection_labels:
            continue
        detected = any(value is True for value in row["layers"].values())
        detected_by_label[row["oracle_label"]] = detected_by_label.get(row["oracle_label"], 0) + int(detected)
        if not detected:
            misses_by_label[row["oracle_label"]] = misses_by_label.get(row["oracle_label"], 0) + 1
    summary = {
        "schema": "biofoundry.v3.exploratory-mutation-challenge/1",
        "seed": SEED,
        "counts": COUNTS,
        "total": len(records),
        "factors": FACTORS,
        "offsets_s": OFFSETS,
        "notes": [
            "Exploratory challenge; excluded from frozen v3.1 headline scores.",
            "protocol_quantity_mismatch labels preserve method-level quantity changes even when mass conservation remains valid.",
            "Resource and time labels are assigned from declared candidates or arithmetic precedence, while checker detections remain separate.",
            "Asset-order rows are Workflow.act traces over selected delivered contracts, not portfolio-plan rows.",
        ],
        "oracle_counts": dict(sorted(__import__("collections").Counter(row["oracle_label"] for row in records).items())),
        "detected_by_label": dict(sorted(detected_by_label.items())),
        "misses_by_label": dict(sorted(misses_by_label.items())),
        "detected_union": sum(any(value is True for value in row["layers"].values()) for row in records),
        "misses": [row["challenge_id"] for row in records if row["oracle_label"] in expected_detection_labels and not any(value is True for value in row["layers"].values())],
    }
    (OUT / "mutation-challenge-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    run()
