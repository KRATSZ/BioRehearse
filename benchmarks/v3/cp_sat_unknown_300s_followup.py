"""Single-case 300-s follow-up for the one unresolved v3 truth case.

The 60-s v3 truth table remains immutable.  This packet only asks whether the
same registered CP-SAT model and seed can produce a certificate with a longer
wall budget; it does not change the primary classification.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve()
PAPER = HERE.parents[2]
V2 = PAPER / "benchmarks" / "v2"
V3 = PAPER / "benchmarks" / "v3"
OUT = PAPER / "source-data" / "v3" / "scheduling"
RAW = OUT / "cp_sat_unknown_300s_followup.json"
SUMMARY = OUT / "cp_sat_unknown_300s_followup_summary.json"
PROTOCOL = V3 / "protocol-cp-sat-unknown-300s-followup.json"
TRUTH = OUT / "cp_sat_truth_runs.jsonl"
sys.path.insert(0, str(V2))
sys.path.insert(1, str(PAPER / "reproducibility" / "source-v2"))

from common import frozen, read, digest  # noqa: E402
from labscriptai.biofoundry.methods import compile_graph  # noqa: E402
from labscriptai.biofoundry.scheduling import solve  # noqa: E402
from scorer import score  # noqa: E402


def verify_packet(protocol: dict, design: dict) -> None:
    mismatches = []
    for relative, expected in protocol["source_hashes"].items():
        path = HERE if relative == "<script>" else PAPER / relative
        actual = digest(path)
        if actual != expected:
            mismatches.append(f"{relative}: expected {expected}, actual {actual}")
    for relative, expected in protocol["input_hashes"].items():
        actual = digest(PAPER / relative)
        if actual != expected:
            mismatches.append(f"input:{relative}: expected {expected}, actual {actual}")
    if design.get("freeze_id") != protocol["v3_freeze_id"]:
        mismatches.append("v3 freeze id mismatch")
    if protocol["runtime"]["python_version"] != platform.python_version():
        mismatches.append("python runtime mismatch")
    if protocol["runtime"]["ortools_version"] != importlib.metadata.version("ortools"):
        mismatches.append("OR-Tools runtime mismatch")
    if mismatches:
        raise RuntimeError("300-s follow-up freeze verification failed: " + " | ".join(mismatches))


def main() -> None:
    if RAW.exists() or SUMMARY.exists():
        raise RuntimeError(f"Refusing to overwrite existing follow-up output: {RAW}")
    frozen()
    design = read(V3 / "design.json")
    protocol = read(PROTOCOL)
    verify_packet(protocol, design)
    truth_rows = [json.loads(line) for line in TRUTH.read_text().splitlines() if line.strip()]
    prior = [row for row in truth_rows if row["case"] == "heldout-047"]
    if not prior or prior[-1]["budget_s"] != 60 or prior[-1]["classification"] != "unresolved":
        raise RuntimeError("heldout-047 is no longer the frozen final UNKNOWN case")
    case = next(row for row in read(V2 / "workloads.json")["heldout"] if row["id"] == "heldout-047")
    catalog = read(PAPER / "source-data" / "v2" / "catalog.json")
    compiled = compile_graph(case["intent"], catalog)
    if not compiled["ok"]:
        raise RuntimeError(f"compiler failed: {compiled}")
    started = time.perf_counter()
    error = None
    plan = {}
    try:
        plan = solve(compiled["graph"], catalog, case["layout"], "fastest", case["bookings"], time_limit_s=300)
    except Exception as exc:
        error = repr(exc)
    wall = time.perf_counter() - started
    checked = score(plan, compiled["graph"], catalog, case["bookings"]) if plan else {"returned": False, "valid": False, "violations": ["exception"]}
    record = {
        "case": case["id"],
        "load": case["load"],
        "handling_policy": case["handling_policy"],
        "solver": "cp_sat",
        "objective": "fastest",
        "budget_s": 300,
        "wall_s": wall,
        "status": plan.get("status", "EXCEPTION"),
        "classification": "feasible_certificate" if plan.get("status") in {"FEASIBLE", "OPTIMAL"} else ("infeasible_proof" if plan.get("status") == "INFEASIBLE" else "unresolved"),
        "returned": bool(plan.get("ok")),
        "valid": bool(checked.get("valid")),
        "violations": checked.get("violations", []),
        "proven_optimal": plan.get("proven_optimal"),
        "objective_value": plan.get("objective_value"),
        "best_bound": plan.get("best_bound"),
        "relative_bound_gap": ((plan.get("objective_value") - plan.get("best_bound")) / plan.get("objective_value") if plan.get("objective_value") is not None and plan.get("best_bound") is not None else None),
        "makespan_s": plan.get("makespan_s"),
        "cost_cny": plan.get("cost_cny"),
        "error": error,
        "primary_truth_unchanged": True,
        "primary_truth_source_sha256": digest(TRUTH),
        "primary_truth_final_60s_status": prior[-1]["status"],
        "primary_truth_final_60s_classification": prior[-1]["classification"],
    }
    RAW.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    summary = {
        "schema": "biorehearse.cp-sat-unknown-followup.v3",
        "case": "heldout-047",
        "budget_s": 300,
        "record": RAW.name,
        "primary_truth_unchanged": True,
        "outcome": {k: record[k] for k in ("status", "classification", "returned", "valid", "wall_s", "objective_value", "best_bound", "relative_bound_gap")},
        "source_hashes": protocol["source_hashes"],
        "runtime": protocol["runtime"],
        "scope": "Post-hoc single-case budget extension; it is not part of the 60-case primary truth table.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"case": case["id"], "status": record["status"], "classification": record["classification"], "wall_s": wall}, ensure_ascii=False))


if __name__ == "__main__":
    main()
