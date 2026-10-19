"""Run the independent v3.2 SGS baseline correction.

The v3.2 packet is post-hoc relative to the final v3 freeze.  It does not
modify the frozen v3 sources or data.  It uses the same fixed 20-case subset,
selects one priority rule per SGS mode on development cases only, and runs
every mode/budget/case combination independently.
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
RAW = OUT / "sgs_v32_runs.jsonl"
DEV_RAW = OUT / "sgs_v32_development_selection.jsonl"
SUMMARY = OUT / "sgs_v32_summary.json"
PROTOCOL = V3 / "protocol-sgs-v32.json"
sys.path.insert(0, str(V3))
sys.path.insert(1, str(V2))
sys.path.insert(2, str(PAPER / "reproducibility" / "source-v2"))

from common import frozen, read  # noqa: E402
from labscriptai.biofoundry.methods import compile_graph  # noqa: E402
from scorer import score  # noqa: E402
from sgs_v32 import solve_sgs  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def verify_protocol(protocol: dict, design: dict) -> None:
    mismatches = []
    for relative, expected in protocol["source_hashes"].items():
        path = HERE if relative == "<driver>" else V3 / "sgs_v32.py" if relative == "<sgs_v32>" else PAPER / relative
        actual = digest(path)
        if actual != expected:
            mismatches.append(f"source:{relative}: expected {expected}, actual {actual}")
    for relative, expected in protocol["input_hashes"].items():
        actual = digest(PAPER / relative)
        if actual != expected:
            mismatches.append(f"input:{relative}: expected {expected}, actual {actual}")
    if canonical_digest(protocol["config"]) != protocol["config_sha256"]:
        mismatches.append("configuration digest mismatch")
    config = protocol["config"]
    if design.get("freeze_id") != config["v3_freeze_id"]:
        mismatches.append("v3 freeze id mismatch")
    if design.get("common_subset_cases") != config["common_subset_cases"]:
        mismatches.append("common subset mismatch")
    if design.get("development_cases") != config["development_cases"]:
        mismatches.append("development cases mismatch")
    if config["budgets_s"] != [2, 10, 60] or config["modes"] != ["serial", "parallel"]:
        mismatches.append("budget/mode configuration mismatch")
    if protocol["runtime"]["python_version"] != platform.python_version():
        mismatches.append("python runtime mismatch")
    if protocol["runtime"]["ortools_version"] != importlib.metadata.version("ortools"):
        mismatches.append("OR-Tools runtime mismatch")
    if mismatches:
        raise RuntimeError("v3.2 SGS freeze verification failed: " + " | ".join(mismatches))


def emit(path: Path, record: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def select_rule(development: list[dict], catalog: dict, mode: str, rule_names: list[str]):
    rows = []
    for rule in rule_names:
        for case in development:
            graph_result = compile_graph(case["intent"], catalog)
            if not graph_result["ok"]:
                raise RuntimeError(f"compiler failed on development case {case['id']}: {graph_result}")
            started = time.perf_counter()
            plan = solve_sgs(
                graph_result["graph"],
                catalog,
                case["layout"],
                "fastest",
                case["bookings"],
                mode=mode,
                priority_rule=rule,
                time_limit_s=10,
            )
            checked = score(plan, graph_result["graph"], catalog, case["bookings"])
            rows.append(
                {
                    "split": "development",
                    "case": case["id"],
                    "mode": mode,
                    "rule": rule,
                    "valid": bool(checked.get("valid")),
                    "status": plan.get("status"),
                    "makespan_s": plan.get("makespan_s"),
                    "wall_s": time.perf_counter() - started,
                }
            )
    summaries = []
    for rule_index, rule in enumerate(rule_names):
        valid_rows = [row for row in rows if row["rule"] == rule and row["valid"]]
        summary = {
            "split": "development_summary",
            "mode": mode,
            "rule": rule,
            "valid_rate": len(valid_rows) / len(development),
            "mean_valid_makespan_s": (sum(row["makespan_s"] for row in valid_rows) / len(valid_rows) if valid_rows else None),
            "rule_index": rule_index,
        }
        summaries.append(summary)
        rows.append(summary)
    chosen = min(
        summaries,
        key=lambda row: (
            -row["valid_rate"],
            row["mean_valid_makespan_s"] if row["mean_valid_makespan_s"] is not None else float("inf"),
            row["rule_index"],
        ),
    )
    return chosen["rule"], rows


def main() -> None:
    if any(path.exists() for path in (RAW, DEV_RAW, SUMMARY)):
        raise RuntimeError("Refusing to overwrite existing v3.2 SGS outputs")
    frozen()
    design = read(V3 / "design.json")
    protocol = read(PROTOCOL)
    verify_protocol(protocol, design)
    config = protocol["config"]
    workloads = read(V2 / "workloads.json")
    catalog = read(PAPER / "source-data" / "v2" / "catalog.json")
    cases = {case["id"]: case for case in workloads["heldout"]}
    common = [cases[case_id] for case_id in config["common_subset_cases"]]
    development = [case for case in workloads["development"] if case["id"] in config["development_cases"]]
    if [case["id"] for case in development] != config["development_cases"]:
        raise RuntimeError("development case order mismatch")
    OUT.mkdir(parents=True, exist_ok=True)

    rules = config["priority_rules"]
    chosen_rules = {}
    development_rows = []
    for mode in config["modes"]:
        chosen, rows = select_rule(development, catalog, mode, rules)
        chosen_rules[mode] = chosen
        development_rows.extend(rows)
    for row in development_rows:
        emit(DEV_RAW, row)

    graphs = {}
    for case in common:
        compiled = compile_graph(case["intent"], catalog)
        if not compiled["ok"]:
            raise RuntimeError(f"compiler failed on frozen case {case['id']}: {compiled}")
        graphs[case["id"]] = compiled["graph"]

    for case in common:
        for mode in config["modes"]:
            for budget in config["budgets_s"]:
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
                        priority_rule=chosen_rules[mode],
                        time_limit_s=budget,
                    )
                except Exception as exc:
                    error = repr(exc)
                wall = time.perf_counter() - started
                checked = score(plan, graphs[case["id"]], catalog, case["bookings"]) if plan else {"valid": False, "violations": ["exception"]}
                emit(
                    RAW,
                    {
                        "case": case["id"],
                        "load": case["load"],
                        "handling_policy": case["handling_policy"],
                        "solver": f"{mode}_sgs_v32",
                        "mode": mode,
                        "priority_rule": chosen_rules[mode],
                        "lookahead": config["lookahead"],
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
                    },
                )

    records = [json.loads(line) for line in RAW.read_text().splitlines() if line.strip()]
    if len(records) != 120 or len({(row["case"], row["mode"], row["budget_s"]) for row in records}) != 120:
        raise RuntimeError(f"expected 120 unique v3.2 runs, found {len(records)}")
    groups = []
    for mode in config["modes"]:
        for budget in config["budgets_s"]:
            group = [row for row in records if row["mode"] == mode and row["budget_s"] == budget]
            groups.append(
                {
                    "mode": mode,
                    "priority_rule": chosen_rules[mode],
                    "budget_s": budget,
                    "cases": len(group),
                    "returned": sum(row["returned"] for row in group),
                    "valid": sum(row["valid"] for row in group),
                    "status": dict(Counter(row["status"] for row in group)),
                    "median_wall_s": median(row["wall_s"] for row in group),
                    "max_wall_s": max(row["wall_s"] for row in group),
                }
            )
    summary = {
        "schema": "biorehearse.sgs-v32-summary.v3",
        "v3_freeze_id": design["freeze_id"],
        "config_sha256": protocol["config_sha256"],
        "runs": len(records),
        "development_runs": len(development_rows),
        "chosen_rules": chosen_rules,
        "groups": groups,
        "independent_runs": "Every case/mode/budget combination was solved separately at 2, 10 and 60 s; no shorter-budget plan was copied.",
        "scope": "Corrected non-delay parallel SGS comparator; post-hoc v3.2 baseline extension, not a replacement of the v3 prespecified baseline.",
        "source_hashes": protocol["source_hashes"],
        "input_hashes": protocol["input_hashes"],
        "runtime": protocol["runtime"],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"runs": len(records), "development_runs": len(development_rows), "chosen_rules": chosen_rules}, ensure_ascii=False))


if __name__ == "__main__":
    main()
