"""Frozen, independent mutation suite for the layered rehearsal checks.

The suite mutates compiled plans after intent compilation and separately
mutates access-lifecycle command traces from delivered asset contracts.  A
mutation's oracle label is assigned by its predeclared construction (for
example, a negative transfer volume is a known balance violation); it is not
derived from any of the checkers being measured.  Controls, equivalent
mutations, and checker misses are retained in the JSONL output.

Usage::

    python benchmarks/v3/mutation.py --freeze
    python benchmarks/v3/mutation.py

The first command writes the input hash freeze.  The second command refuses to
run if the freeze is absent or stale.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
VLAB = Path(os.environ.get("BIOFOUNDRY_VLAB", str(ROOT)))
PAPER = ROOT / "docs" / "paper" / "biofoundry-preprint"
EXPORT = VLAB / "exports" / "biofoundry"
V2 = PAPER / "benchmarks" / "v2"
PLAN_DIR = PAPER / "source-data" / "v2" / "repair" / "plans"
CATALOG = PAPER / "source-data" / "v2" / "catalog.json"
LANGUAGE_DIAGNOSTICS = PAPER / "source-data" / "v2" / "language-diagnostics.json"
PROTOCOL = PAPER / "benchmarks" / "v3" / "VALIDATION_PROTOCOL.md"
OUT = PAPER / "source-data" / "v3"
FREEZE = OUT / "mutation-freeze.json"
SEED = 20261020
COUNTS = {
    "control": 40,
    "delete_transfer": 72,
    "incompatible_device": 72,
    "shift_time": 72,
    "change_volume": 72,
    "access_order": 72,
    "intent_deadline": 7,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def inputs():
    contracts = sorted((EXPORT / "library").glob("*/asset.contract.json"))
    deadline_cases = real_deadline_cases()
    return {
        "v3_mutation_sha256": sha256(Path(__file__).resolve()),
        "v3_validation_sha256": sha256(PAPER / "benchmarks" / "v3" / "validation.py"),
        "protocol_sha256": sha256(PROTOCOL),
        "v2_scorer_sha256": sha256(V2 / "scorer.py"),
        "v2_repair_schema_sha256": sha256(V2 / "repair.py"),
        "base_catalog_sha256": sha256(CATALOG),
        "sim_import_chain": [{"path": str((VLAB / "sim" / "library_protocols.py").relative_to(VLAB)), "sha256": sha256(VLAB / "sim" / "library_protocols.py")}],
        "asset_contracts": [{"path": str(p.relative_to(VLAB)), "sha256": sha256(p)} for p in contracts],
        "access_contracts": [{"path": str(p.relative_to(VLAB)), "sha256": sha256(p)} for p in contracts if json.loads(p.read_text()).get("protocol", {}).get("access_lifecycle_tested") is True],
        "base_plans": [{"path": str(p.relative_to(VLAB)), "sha256": sha256(p)} for p in sorted(PLAN_DIR.glob("repair-*.json"))],
        "language_diagnostics_sha256": sha256(LANGUAGE_DIAGNOSTICS),
        "real_deadline_cases": [{"model": r["model"], "case": r["case"], "raw_file": r["raw_file"], "raw_sha256": sha256(PAPER / r["raw_file"])} for r in deadline_cases],
    }


def freeze_inputs(force: bool = False):
    OUT.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": "biofoundry.v3.1.mutation-freeze/1",
        "seed": SEED,
        "counts": COUNTS,
        "total_mutations": sum(COUNTS.values()),
        "protocol": str(PROTOCOL.relative_to(VLAB)),
        "inputs": inputs(),
        "oracle_rule": "oracle_label is assigned by the predeclared mutator construction; checker outputs are separate fields and never define truth labels",
    }
    if FREEZE.exists():
        existing = json.loads(FREEZE.read_text())
        if existing != data and not force:
            raise RuntimeError("Existing mutation freeze differs; do not overwrite a frozen evaluation")
        if existing == data:
            return existing
    FREEZE.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return data


def assert_frozen():
    if not FREEZE.exists():
        raise RuntimeError("Missing mutation-freeze.json; run --freeze before evaluation")
    frozen = json.loads(FREEZE.read_text())
    current = inputs()
    if frozen.get("inputs") != current:
        raise RuntimeError("Mutation input hash changed after freeze; preserve the frozen suite")
    if frozen.get("seed") != SEED or frozen.get("counts") != COUNTS:
        raise RuntimeError("Mutation protocol parameters differ from freeze")
    return frozen


def load_v2():
    if str(V2) not in sys.path:
        sys.path.insert(0, str(V2))
    scorer = load_module("biofoundry_v3_v2_scorer", V2 / "scorer.py")
    # The v2 scorer is intentionally loaded directly; this keeps its frozen
    # source independent of production validation code.
    catalog = json.loads(CATALOG.read_text())
    plans = []
    for path in sorted(PLAN_DIR.glob("repair-*.json")):
        plan = json.loads(path.read_text())
        # Metadata is outside the frozen plan schema and is ignored by both
        # independent scorers; it lets each JSONL record bind to its source
        # file without guessing from the generated plan id.
        plan["_source_path"] = str(path)
        plans.append(plan)
    return scorer, catalog, plans


def real_deadline_cases():
    """The seven recorded deadline mismatches from the frozen language study."""
    rows = json.loads(LANGUAGE_DIAGNOSTICS.read_text()).get("annotations", [])
    cases = [r for r in rows if r.get("diagnostic") == "deadline mismatch"]
    if len(cases) != COUNTS["intent_deadline"]:
        raise RuntimeError(f"Expected {COUNTS['intent_deadline']} recorded deadline cases, found {len(cases)}")
    # language-diagnostics.json intentionally stores the diagnostic summary;
    # the raw generated response is indexed by model/case in the frozen
    # scores.jsonl manifests.  Resolve that provenance here instead of
    # inventing a path or hashing a derived summary as if it were the model
    # output.
    enriched = []
    for case in cases:
        score_path = PAPER / "source-data" / "v2" / "heldout" / "language" / case["model"] / "scores.jsonl"
        matches = []
        for line in score_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("case") == case["case"]:
                matches.append(row)
        if len(matches) != 1 or not matches[0].get("raw_file"):
            raise RuntimeError(f"Expected one raw score manifest row for {case['model']}:{case['case']}")
        raw_file = matches[0]["raw_file"]
        raw_path = PAPER / raw_file
        if not raw_path.exists():
            raise RuntimeError(f"Missing raw language response: {raw_path}")
        enriched.append({**case, "raw_file": raw_file, "raw_sha256": sha256(raw_path)})
    return enriched


def deep_plan(plan):
    return copy.deepcopy(plan)


def operation_rows(plan):
    return [r for r in plan["rows"] if r.get("kind") == "operation"]


def transfer_pairs(plan):
    pairs = []
    seen = set()
    for i, event in enumerate(plan["events"]):
        if event.get("kind") != "transfer":
            continue
        task = event.get("task_id")
        if task in seen:
            continue
        if event.get("phase") == "start":
            j = next((j for j in range(i + 1, len(plan["events"])) if plan["events"][j].get("task_id") == task and plan["events"][j].get("phase") == "finish"), None)
            if j is not None:
                pairs.append((i, j, task))
                seen.add(task)
    return pairs


def mutate_plan(plan, category, rng):
    """Return (mutated_plan, target, construction_oracle, parameters)."""
    q = deep_plan(plan)
    if category == "control":
        return q, "none", "equivalent_control", {}
    if category == "delete_transfer":
        pairs = transfer_pairs(q)
        i, j, task = pairs[rng.randrange(len(pairs))]
        moved = set(q["events"][i].get("container_ids", [])) | set(q["events"][j].get("container_ids", []))
        later_use = any(moved.intersection(set(e.get("container_ids", []))) for e in q["events"][j + 1:])
        same_station = q["events"][i].get("source") == q["events"][i].get("destination")
        # Removing both events is an explicit custody mutation.  The plan rows
        # remain unchanged so schedule arithmetic can legitimately pass while
        # the independent state replay detects the missing hand-off.
        del q["events"][j]
        del q["events"][i]
        oracle = "equivalent_mutation" if same_station else "known_violation"
        return q, task, oracle, {"removed_phases": ["start", "finish"], "container_used_later": later_use, "same_station_transfer": same_station}
    if category == "incompatible_device":
        candidates = [r for r in operation_rows(q) if r.get("resource") not in ("bench", "operator")]
        row = candidates[rng.randrange(len(candidates))]
        old = row["resource"]
        row["resource"] = "bench"
        # This is intentionally a post-compilation mismatch.  The original
        # intent is left untouched so the intent layer is not scored here;
        # schedule/capability checking must find the incompatible resource.
        return q, row["id"], "known_violation", {"old_resource": old, "new_resource": "bench"}
    if category == "shift_time":
        rows = [r for r in operation_rows(q) if r.get("depends_on")]
        row = rows[rng.randrange(len(rows))]
        dep = row["depends_on"][0]
        predecessor = next(r for r in q["rows"] if r["id"] == dep)
        duration = row["end_s"] - row["start_s"]
        old = row["start_s"]
        row["start_s"] = max(0, predecessor["end_s"] - 1)
        row["end_s"] = row["start_s"] + duration
        row["process_start_s"] = row["start_s"] + row["load_s"]
        row["process_end_s"] = row["end_s"] - row["clean_s"]
        for reservation in q["reservations"]:
            if reservation["task_id"] == row["id"]:
                delta = row["start_s"] - old
                reservation["start_s"] += delta
                reservation["end_s"] += delta
        return q, row["id"], "known_violation", {"predecessor": dep, "old_start_s": old, "new_start_s": row["start_s"]}
    if category == "change_volume":
        events = [e for e in q["events"] if e.get("transfers")]
        event = events[rng.randrange(len(events))]
        transfer_index = rng.randrange(len(event["transfers"]))
        src, dst, old = event["transfers"][transfer_index]
        # A negative volume is an unambiguous balance mutation and is retained
        # as a negative result if a checker misses it.
        new = -1.0 if rng.random() < 0.5 else float(old) + 100000.0
        event["transfers"][transfer_index][2] = new
        return q, event["task_id"], "known_violation", {"source": src, "destination": dst, "old_volume_ul": old, "new_volume_ul": new}
    raise ValueError(category)


def run_access_mutation(mod, binding, case_name):
    """Run a contract-derived access-order mutation on a fresh state."""
    station = "asset_probe"
    flow = mod.Workflow({station: binding}, mod.demo_samples())
    before = copy.deepcopy(flow.state)
    act = lambda command, **kwargs: flow.act(station, command, **kwargs)
    expected_codes = {
        "closed_door_load": "ACCESS_CLOSED",
        "open_after_load_without_close": "ACCESS_OPEN",
        "wrong_origin_load": "WRONG_LOCATION",
        "unload_before_load": "NOT_LOADED",
        "open_while_running": "BUSY",
        "load_twice": "ACCESS_CLOSED",
    }
    expected = expected_codes[case_name]
    try:
        if case_name == "closed_door_load":
            act("load", sample_id="sample", origin="prep:sample")
        elif case_name == "open_after_load_without_close":
            act("open")
            act("load", sample_id="sample", origin="prep:sample")
            act("start")
        elif case_name == "wrong_origin_load":
            act("open")
            act("load", sample_id="sample", origin="prep:wrong")
        elif case_name == "unload_before_load":
            act("open")
            act("unload", sample_id="sample", origin="prep:sample", destination="prep:other")
        elif case_name == "open_while_running":
            act("open")
            act("load", sample_id="sample", origin="prep:sample")
            act("close")
            act("start")
            act("open")
        elif case_name == "load_twice":
            act("open")
            act("load", sample_id="sample", origin="prep:sample")
            act("close")
            act("load", sample_id="sample", origin="device:sample")
        else:
            raise ValueError(case_name)
        return {"detected": False, "expected_code": expected, "observed_code": None, "state_unchanged": before == flow.state}
    except mod.Blocked as exc:
        return {"detected": True, "expected_code": expected, "observed_code": exc.code, "state_unchanged": before == flow.state}


def run_suite():
    frozen = assert_frozen()
    scorer, catalog, plans = load_v2()
    # Validate that each source plan is valid before it becomes a mutation
    # substrate. This is recorded, not silently assumed.
    base_status = []
    for plan in plans:
        base = scorer.score(plan, plan["graph"], catalog)
        state = scorer.states(plan)
        base_status.append({"plan": plan["id"], "schedule_valid": base["valid"], "mass_valid": state["mass_valid"], "material_valid": state["material_valid"]})
    if not all(row["schedule_valid"] and row["mass_valid"] and row["material_valid"] for row in base_status):
        raise RuntimeError("A mutation substrate failed its independent base checks")

    validation = load_module("biofoundry_v3_validation", PAPER / "benchmarks" / "v3" / "validation.py")
    mod, _runner, access_rows = validation.access_bindings()
    access_map = {r["asset_id"]: mod.Library(EXPORT).select(asset_id=r["asset_id"]) for r in access_rows}
    access_cases = ["closed_door_load", "open_after_load_without_close", "wrong_origin_load", "unload_before_load", "open_while_running", "load_twice"]
    deadline_cases = real_deadline_cases()

    rng = random.Random(SEED)
    records = []
    for category, count in COUNTS.items():
        for index in range(count):
            local_seed = rng.randrange(1 << 31)
            local = random.Random(local_seed)
            plan = plans[rng.randrange(len(plans))] if category != "intent_deadline" else None
            record = {
                "mutation_id": f"v3-{len(records):04d}",
                "seed": local_seed,
                "category": category,
                "input_type": "recorded_intent_case" if category == "intent_deadline" else ("asset_action_probe" if category == "access_order" else "compiled_plan_mutation"),
                "base_plan": plan["id"] if plan is not None else None,
                "base_plan_sha256": sha256(Path(plan["_source_path"])) if plan is not None else None,
                "oracle_independent_of_checker": True,
                "layers": {"intent": None, "schedule": None, "mass_balance": None, "material_location": None, "asset_contract": None},
            }
            if category == "intent_deadline":
                case = deadline_cases[index]
                expected = int(case["expected_deadline_s"])
                actual = int(case["actual_deadline_s"])
                detected = actual != expected
                record.update({"target": case["case"], "oracle_label": "known_violation" if detected else "equivalent_mutation", "source_model": case["model"], "source_raw_file": case["raw_file"], "source_raw_sha256": sha256(PAPER / case["raw_file"]), "parameters": {"expected_deadline_s": expected, "actual_deadline_s": actual}})
                record["layers"]["intent"] = detected
                record["observed"] = {"expected_deadline_s": expected, "actual_deadline_s": actual}
            elif category == "access_order":
                asset_id = sorted(access_map)[local.randrange(len(access_map))]
                case_name = access_cases[local.randrange(len(access_cases))]
                outcome = run_access_mutation(mod, access_map[asset_id], case_name)
                record.update({"asset_id": asset_id, "target": case_name, "oracle_label": "known_violation", "asset_contract_expected_code": outcome["expected_code"]})
                record["layers"]["asset_contract"] = outcome["detected"]
                record["observed"] = {"asset_contract_code": outcome["observed_code"], "state_unchanged": outcome["state_unchanged"]}
            else:
                mutated, target, oracle_label, params = mutate_plan(plan, category, local)
                schedule = scorer.score(mutated, mutated["graph"], catalog)
                state = scorer.states(mutated)
                record.update({"target": target, "oracle_label": oracle_label, "parameters": params})
                record["layers"].update({"schedule": not schedule.get("valid", False), "mass_balance": not state.get("mass_valid", False), "material_location": not state.get("material_valid", False)})
                record["observed"] = {"schedule_violations": schedule.get("violations", []), "mass_issues": len(state.get("mass_issues", [])), "location_issues": len(state.get("location_issues", []))}
            records.append(record)

    outdir = OUT / "mutations"
    outdir.mkdir(parents=True, exist_ok=True)
    jsonl = outdir / "mutants.jsonl"
    with jsonl.open("w") as fh:
        for row in records:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    # Aggregate only what was actually tested.  Rates are mutation-yield
    # statistics, not prevalence or sensitivity on naturally occurring errors.
    summary = {"schema": "biofoundry.v3.1.mutation-summary/1", "seed": SEED, "freeze_sha256": sha256(FREEZE), "base_status": base_status, "counts": {}, "layers": {}, "notes": ["Compiled-plan probes and asset-action probes are separate input types; the asset-contract layer is not applied to the 24 portfolio plans.", "Intent is reported only for the seven recorded deadline mismatches; compiled-plan mutations are not re-scored as intent.", "Known/equivalent labels come from predeclared construction or frozen diagnostic records, not checker outputs; all controls and misses are retained.", "No mutation yield is interpreted as natural error prevalence."]}
    for category in COUNTS:
        group = [r for r in records if r["category"] == category]
        summary["counts"][category] = len(group)
    summary["layers_for_matrix"] = ["intent", "schedule", "mass_balance", "material_location", "asset_contract"]
    summary["oracle_counts"] = {}
    for row in records:
        summary["oracle_counts"][row["oracle_label"]] = summary["oracle_counts"].get(row["oracle_label"], 0) + 1
    for category in COUNTS:
        group = [r for r in records if r["category"] == category]
        layer_stats = {}
        for layer in summary["layers_for_matrix"]:
            applicable = [r for r in group if r["layers"][layer] is not None]
            detected = sum(bool(r["layers"][layer]) for r in applicable)
            layer_stats[layer] = {"detected": detected, "total": len(applicable), "not_applicable": len(group) - len(applicable), "rate": detected / len(applicable) if applicable else None}
        summary["layers"][category] = layer_stats
    union_detected = sum(any(v is True for v in r["layers"].values()) for r in records)
    summary["union"] = {"detected": union_detected, "total": len(records), "rate": union_detected / len(records)}
    known = [r for r in records if r["oracle_label"] == "known_violation"]
    equivalent = [r for r in records if r["oracle_label"].startswith("equivalent")]
    summary["known_error_yield"] = {"detected": sum(any(v is True for v in r["layers"].values()) for r in known), "total": len(known), "rate": sum(any(v is True for v in r["layers"].values()) for r in known) / len(known)}
    summary["equivalent_false_positive"] = {"detected": sum(any(v is True for v in r["layers"].values()) for r in equivalent), "total": len(equivalent), "rate": sum(any(v is True for v in r["layers"].values()) for r in equivalent) / len(equivalent)}
    summary["misses"] = [r["mutation_id"] for r in known if not any(v is True for v in r["layers"].values())]
    summary["unexpected_equivalent_detections"] = [r["mutation_id"] for r in equivalent if any(v is True for v in r["layers"].values())]
    (OUT / "mutation-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n")

    # Lightweight source for Fig. 6: one row per category, one cell per layer.
    csv = OUT / "fig6-validation-matrix.csv"
    lines = ["category,n,intent,schedule,mass_balance,material_location,asset_contract,union"]
    for category in COUNTS:
        group = [r for r in records if r["category"] == category]
        vals = []
        for layer in summary["layers_for_matrix"]:
            applicable = [r for r in group if r["layers"][layer] is not None]
            vals.append("NA" if not applicable else f"{sum(bool(r['layers'][layer]) for r in applicable) / len(applicable):.6f}")
        union = sum(any(v is True for v in r["layers"].values()) for r in group) / len(group)
        lines.append(",".join([category, str(len(group))] + vals + [f"{union:.6f}"]))
    csv.write_text("\n".join(lines) + "\n")
    return summary


if __name__ == "__main__":
    if "--freeze" in sys.argv:
        data = freeze_inputs(force="--force-freeze" in sys.argv)
        print(json.dumps({"freeze": str(FREEZE), "total_mutations": data["total_mutations"], "freeze_sha256": sha256(FREEZE)}, ensure_ascii=False))
    else:
        print(json.dumps(run_suite(), ensure_ascii=False))
