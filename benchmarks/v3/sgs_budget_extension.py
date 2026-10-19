"""Run the fixed-rule SGS budget extension without changing the v3 freeze.

This is a post-freeze, independent budget sensitivity packet for the already
fixed 20-case common subset.  It runs every serial/parallel SGS case at both
10 s and 60 s; it never copies a shorter-budget result into a longer-budget
row.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve()
PAPER = HERE.parents[2]
V2 = PAPER / "benchmarks" / "v2"
V3 = PAPER / "benchmarks" / "v3"
OUT = PAPER / "source-data" / "v3" / "scheduling"
RAW = OUT / "sgs_budget_extension.jsonl"
SUMMARY = OUT / "sgs_budget_extension_summary.json"
PROTOCOL = V3 / "protocol-sgs-budget-extension.json"
sys.path.insert(0, str(V3))
sys.path.insert(1, str(V2))
sys.path.insert(2, str(PAPER / "reproducibility" / "source-v2"))

from common import frozen, read  # noqa: E402
from labscriptai.biofoundry.methods import compile_graph  # noqa: E402
from scorer import score  # noqa: E402
from sgs import solve_sgs  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        mismatches.append("v3 freeze id does not match the packet")
    if protocol["runtime"]["python_version"] != platform.python_version():
        mismatches.append("python runtime mismatch")
    ortools_version = importlib.metadata.version("ortools")
    if protocol["runtime"]["ortools_version"] != ortools_version:
        mismatches.append("OR-Tools runtime mismatch")
    if mismatches:
        raise RuntimeError("SGS budget extension freeze verification failed: " + " | ".join(mismatches))


def emit(record: dict) -> None:
    with RAW.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def main() -> None:
    if RAW.exists() or SUMMARY.exists():
        raise RuntimeError(f"Refusing to overwrite existing SGS extension outputs: {RAW} / {SUMMARY}")
    frozen()
    design = read(V3 / "design.json")
    protocol = read(PROTOCOL)
    verify_packet(protocol, design)
    workloads = read(V2 / "workloads.json")
    catalog = read(PAPER / "source-data" / "v2" / "catalog.json")
    cases = {case["id"]: case for case in workloads["heldout"]}
    common = [cases[case_id] for case_id in design["common_subset_cases"]]
    graphs = {}
    for case in common:
        compiled = compile_graph(case["intent"], catalog)
        if not compiled["ok"]:
            raise RuntimeError(f"compiler failed for frozen case {case['id']}: {compiled}")
        graphs[case["id"]] = compiled["graph"]
    OUT.mkdir(parents=True, exist_ok=True)
    for case in common:
        for mode in ("serial", "parallel"):
            for budget in (10, 60):
                started = time.perf_counter()
                error = None
                plan = {}
                try:
                    plan = solve_sgs(
                        graphs[case["id"]],
                        catalog,
                        case["layout"],
                        "fastest",
                        case["bookings"],
                        mode=mode,
                        priority_rule="input_order",
                        time_limit_s=budget,
                    )
                except Exception as exc:  # retain every failure as data
                    error = repr(exc)
                wall = time.perf_counter() - started
                checked = score(plan, graphs[case["id"]], catalog, case["bookings"]) if plan else {"returned": False, "valid": False, "violations": ["exception"]}
                emit(
                    {
                        "case": case["id"],
                        "load": case["load"],
                        "handling_policy": case["handling_policy"],
                        "solver": f"{mode}_sgs",
                        "mode": mode,
                        "priority_rule": "input_order",
                        "lookahead": "immediate_window_child_forward_check",
                        "budget_s": budget,
                        "wall_s": wall,
                        "status": plan.get("status", "EXCEPTION"),
                        "returned": bool(plan.get("ok")),
                        "valid": bool(checked.get("valid")),
                        "violations": checked.get("violations", []),
                        "makespan_s": plan.get("makespan_s"),
                        "cost_cny": plan.get("cost_cny"),
                        "solve_seconds": plan.get("solve_seconds"),
                        "planning_budget_s": plan.get("planning_budget_s"),
                        "error": error,
                    }
                )
    records = [json.loads(line) for line in RAW.read_text().splitlines() if line.strip()]
    if len(records) != 80:
        raise RuntimeError(f"expected 80 independent SGS runs, found {len(records)}")
    groups = []
    for mode in ("serial", "parallel"):
        for budget in (10, 60):
            group = [r for r in records if r["mode"] == mode and r["budget_s"] == budget]
            groups.append(
                {
                    "mode": mode,
                    "budget_s": budget,
                    "cases": len(group),
                    "returned": sum(r["returned"] for r in group),
                    "valid": sum(r["valid"] for r in group),
                    "status": dict(Counter(r["status"] for r in group)),
                    "median_wall_s": median(r["wall_s"] for r in group),
                    "max_wall_s": max(r["wall_s"] for r in group),
                }
            )
    summary = {
        "schema": "biorehearse.sgs-budget-extension.v3",
        "v3_freeze_id": design["freeze_id"],
        "runs": len(records),
        "cases": 20,
        "budgets_s": [10, 60],
        "modes": ["serial", "parallel"],
        "priority_rule": "input_order",
        "lookahead": "immediate_window_child_forward_check",
        "independent_runs": "Each case/mode/budget combination was solved separately; no 2-s result was copied into a longer-budget row and no sleep was added.",
        "groups": groups,
        "source_hashes": protocol["source_hashes"],
        "runtime": protocol["runtime"],
        "scope": "Fixed heuristic budget sensitivity only; results do not establish that all greedy methods are budget-insensitive.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"raw": str(RAW), "summary": str(SUMMARY), "runs": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
