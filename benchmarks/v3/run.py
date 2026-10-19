"""Run the prospectively frozen v3 scheduling extension.

Outputs are written under ``source-data/v3/scheduling``.  Existing outputs are
never overwritten; use a fresh paper checkout or remove only an unfinished v3
run after inspection.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import importlib.metadata
import platform
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve()
PAPER = HERE.parents[2]
V2 = PAPER / "benchmarks" / "v2"
V3 = PAPER / "benchmarks" / "v3"
OUT = PAPER / "source-data" / "v3" / "scheduling"
SNAP = PAPER / "reproducibility" / "source-v2"
sys.path.insert(0, str(V2))
sys.path.insert(0, str(SNAP))

from common import frozen, read  # noqa: E402
from labscriptai.biofoundry.methods import compile_graph  # noqa: E402
from labscriptai.biofoundry.scheduling import replan, solve, validate_schedule  # noqa: E402
from scorer import score  # noqa: E402
from schedule_audit import audit_replan  # noqa: E402
from sgs import solve_sgs  # noqa: E402


def emit(path: Path, record: dict) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_design(design: dict) -> None:
    """Verify the code, dependencies, inputs and runtime frozen in design.json."""
    sections = ("code_hashes", "dependency_hashes", "inputs")
    mismatches = []
    for section in sections:
        for relative, expected in design.get(section, {}).items():
            path = PAPER / relative
            if not path.exists():
                mismatches.append(f"{section}:{relative}:missing")
                continue
            actual = digest(path)
            if actual != expected:
                mismatches.append(f"{section}:{relative}:expected={expected}:actual={actual}")
    manifest_items = []
    for section in ("code_hashes", "dependency_hashes", "inputs"):
        manifest_items.extend((section, relative, expected) for relative, expected in sorted(design.get(section, {}).items()))
    manifest = hashlib.sha256(json.dumps(manifest_items, separators=(",", ":")).encode()).hexdigest()
    if manifest != design.get("manifest_sha256"):
        mismatches.append(f"manifest:expected={design.get('manifest_sha256')}:actual={manifest}")
    runtime = design.get("runtime", {})
    if runtime.get("python_version") != platform.python_version():
        mismatches.append(f"runtime:python expected={runtime.get('python_version')} actual={platform.python_version()}")
    try:
        ortools_version = importlib.metadata.version("ortools")
    except importlib.metadata.PackageNotFoundError:
        ortools_version = None
    if runtime.get("ortools_version") != ortools_version:
        mismatches.append(f"runtime:ortools expected={runtime.get('ortools_version')} actual={ortools_version}")
    if mismatches:
        raise RuntimeError("v3 prospective freeze verification failed: " + " | ".join(mismatches))


def classification(status: str | None) -> str:
    if status in {"FEASIBLE", "OPTIMAL"}:
        return "feasible_certificate"
    if status == "INFEASIBLE":
        return "infeasible_proof"
    return "unresolved"


def run_cp(graph, case, budget: float):
    started = time.perf_counter()
    error = None
    plan = {}
    try:
        plan = solve(
            graph,
            CATALOG,
            case["layout"],
            "fastest",
            case["bookings"],
            time_limit_s=budget,
        )
    except Exception as exc:  # retain every execution failure in the raw log
        error = repr(exc)
    wall = time.perf_counter() - started
    status = plan.get("status") if plan else "EXCEPTION"
    independent = score(plan, graph, CATALOG, case["bookings"]) if plan else {"returned": False, "valid": False, "violations": ["exception"]}
    return {
        "case": case["id"],
        "split": "heldout",
        "load": case["load"],
        "handling_policy": case["handling_policy"],
        "horizon_s": case["intent"]["deadline_s"],
        "layout": case["layout"],
        "objective": "fastest",
        "solver": "cp_sat",
        "budget_s": budget,
        "wall_s": wall,
        "status": status,
        "classification": classification(status),
        "returned": bool(plan.get("ok")),
        "valid": bool(independent.get("valid")),
        "violations": independent.get("violations", []),
        "proven_optimal": plan.get("proven_optimal"),
        "best_bound": plan.get("best_bound"),
        "objective_value": plan.get("objective_value"),
        "makespan_s": plan.get("makespan_s"),
        "cost_cny": plan.get("cost_cny"),
        "solve_seconds": plan.get("solve_seconds"),
        "model_construction_s": plan.get("model_construction_s"),
        "planning_budget_s": plan.get("planning_budget_s"),
        "code": plan.get("code"),
        "error": error,
    }, plan


def run_sgs_for_case(graph, case, mode: str, rule: str):
    started = time.perf_counter()
    error = None
    plan = {}
    try:
        plan = solve_sgs(
            graph,
            CATALOG,
            case["layout"],
            "fastest",
            case["bookings"],
            mode=mode,
            priority_rule=rule,
            time_limit_s=10,
        )
    except Exception as exc:
        error = repr(exc)
    independent = score(plan, graph, CATALOG, case["bookings"]) if plan else {"returned": False, "valid": False, "violations": ["exception"]}
    return {
        "case": case["id"],
        "split": "heldout",
        "load": case["load"],
        "handling_policy": case["handling_policy"],
        "layout": case["layout"],
        "objective": "fastest",
        "solver": mode + "_sgs",
        "priority_rule": rule,
        "lookahead": "immediate_window_child_forward_check",
        "budget_s": 10,
        "wall_s": time.perf_counter() - started,
        "status": plan.get("status", "EXCEPTION"),
        "returned": bool(plan.get("ok")),
        "valid": bool(independent.get("valid")),
        "violations": independent.get("violations", []),
        "makespan_s": plan.get("makespan_s"),
        "cost_cny": plan.get("cost_cny"),
        "solve_seconds": plan.get("solve_seconds"),
        "error": error,
    }, plan


def select_rule(development, catalog):
    """Choose the fixed rule without reading any held-out outcome."""
    candidates = ["input_order", "minimum_slack", "longest_remaining_path", "earliest_release"]
    rows = []
    for rule in candidates:
        valid = []
        for case in development:
            compiled = compile_graph(case["intent"], catalog)
            if not compiled["ok"]:
                continue
            plan = solve_sgs(compiled["graph"], catalog, case["layout"], "fastest", case["bookings"], mode="serial", priority_rule=rule, time_limit_s=10)
            checked = score(plan, compiled["graph"], catalog, case["bookings"])
            valid.append(bool(checked.get("valid")))
            rows.append({"split": "development", "case": case["id"], "mode": "serial", "rule": rule, "valid": bool(checked.get("valid")), "status": plan.get("status"), "makespan_s": plan.get("makespan_s")})
        valid_rate = sum(valid) / len(valid) if valid else 0
        makespans = [r["makespan_s"] for r in rows if r["rule"] == rule and r["valid"] and r["makespan_s"] is not None]
        rows.append({"split": "development_summary", "rule": rule, "valid_rate": valid_rate, "mean_valid_makespan_s": sum(makespans) / len(makespans) if makespans else None})
    summaries = [r for r in rows if r.get("split") == "development_summary"]
    chosen = min(summaries, key=lambda r: (-r["valid_rate"], r["mean_valid_makespan_s"] if r["mean_valid_makespan_s"] is not None else float("inf"), candidates.index(r["rule"])))
    return chosen["rule"], rows


def run_all() -> None:
    global CATALOG
    frozen()
    design = read(V3 / "design.json")
    verify_design(design)
    workloads = read(V2 / "workloads.json")
    CATALOG = read(PAPER / "source-data" / "v2" / "catalog.json")
    cases = {case["id"]: case for case in workloads["heldout"]}
    development = workloads["development"]
    common_ids = design["common_subset_cases"]
    common = [cases[case_id] for case_id in common_ids]

    OUT.mkdir(parents=True, exist_ok=True)
    paths = {
        "truth": OUT / "cp_sat_truth_runs.jsonl",
        "curve": OUT / "cp_sat_budget_curve.jsonl",
        "sgs": OUT / "sgs_runs.jsonl",
        "outage": OUT / "ks4000_outage.jsonl",
        "dev": OUT / "sgs_development_selection.jsonl",
    }
    for path in paths.values():
        if path.exists():
            raise RuntimeError(f"Refusing to overwrite existing v3 output: {path}")

    chosen_rule, dev_rows = select_rule(development, CATALOG)
    for row in dev_rows:
        emit(paths["dev"], row)
    (V3 / "selected-sgs-rule.json").write_text(json.dumps({"priority_rule": chosen_rule, "development_only": True, "rows": dev_rows}, indent=2, ensure_ascii=False) + "\n")

    graphs = {}
    for case in workloads["heldout"]:
        compiled = compile_graph(case["intent"], CATALOG)
        if not compiled["ok"]:
            raise RuntimeError(f"compiler failed for frozen case {case['id']}: {compiled}")
        graphs[case["id"]] = compiled["graph"]

    # Full 60-case truth status: the 2-s pass is universal; only unresolved
    # statuses escalate.  Every raw attempt remains in this JSONL.
    final_plans = {}
    for case in workloads["heldout"]:
        rec, plan = run_cp(graphs[case["id"]], case, 2)
        emit(paths["truth"], rec)
        last = rec
        while rec["classification"] == "unresolved" and rec["budget_s"] < 60:
            budget = 10 if rec["budget_s"] == 2 else 60
            rec, plan = run_cp(graphs[case["id"]], case, budget)
            emit(paths["truth"], rec)
            last = rec
        if last["returned"] and last["valid"]:
            final_plans[case["id"]] = plan

    # The budget curve is an independent complete 20-case × 3-budget matrix.
    for case in common:
        for budget in (2, 10, 60):
            rec, plan = run_cp(graphs[case["id"]], case, budget)
            rec["curve_case"] = True
            emit(paths["curve"], rec)
            # The outage baseline is strictly the independently valid 60-s
            # run.  A shorter-budget plan is never silently carried forward.
            if budget == 60 and rec["valid"] and plan.get("ok"):
                # Keep the full-budget incumbent for the outage experiment;
                # this is a plan actually returned by the 60-s run, never an
                # imputed carry-forward of a shorter run.
                final_plans[case["id"]] = plan

    # Independent serial/parallel SGS on the exact common subset.
    for case in common:
        for mode in ("serial", "parallel"):
            rec, plan = run_sgs_for_case(graphs[case["id"]], case, mode, chosen_rule)
            emit(paths["sgs"], rec)

    # Replan a known KS4000 outage before a not-yet-started incubate.  Select
    # cases by case id and baseline eligibility only; no outage result is used.
    eligible = []
    for case in common:
        plan = final_plans.get(case["id"])
        if not plan:
            continue
        ks_rows = [r for r in plan.get("rows", []) if r.get("kind") == "operation" and r.get("resource") == "demo:ks4000:1" and r.get("name") in {"incubate", "dark_incubation"}]
        if ks_rows:
            eligible.append((case, plan, min(ks_rows, key=lambda r: r["start_s"])))
    for case, plan, ks_row in eligible[:20]:
        now = max(0, int(ks_row["start_s"]) - 60)
        repair = int(ks_row["start_s"]) + 180
        record = {
            "case": case["id"],
            "fault_resource": "demo:ks4000:1",
            "fault_kind": "known_outage_before_unstarted_step",
            "now_s": now,
            "repair_s": repair,
            "affected_step": ks_row["id"],
            "baseline_budget_s": 60,
            "baseline_independent_valid": True,
            "baseline_makespan_s": plan.get("makespan_s"),
            "baseline_status": plan.get("status"),
        }
        try:
            replanned = replan(copy.deepcopy(plan), CATALOG, now, "demo:ks4000:1", repair, case["bookings"])
            checked = score(replanned, graphs[case["id"]], CATALOG, case["bookings"])
            independent = audit_replan(
                plan,
                replanned,
                now_s=now,
                repair_s=repair,
                failed_resource="demo:ks4000:1",
                scorer_valid=bool(checked.get("valid")),
            )
            record.update({
                "status": replanned.get("status"),
                "returned": bool(replanned.get("ok")),
                "valid": bool(independent["valid"]),
                "violations": list(checked.get("violations", [])) + independent["violations"],
                "independent_checks": independent["independent_checks"],
                "baseline_frozen_rows": independent["baseline_frozen_rows"],
                "replanned_makespan_s": replanned.get("makespan_s"),
                "delta_makespan_s": (replanned.get("makespan_s") - plan.get("makespan_s")) if replanned.get("ok") else None,
                "frozen_steps": replanned.get("replanning", {}).get("frozen_steps", []),
                "modified_unstarted_only": replanned.get("replanning", {}).get("only_unstarted_modified"),
            })
        except Exception as exc:
            independent = audit_replan(
                plan,
                {},
                now_s=now,
                repair_s=repair,
                failed_resource="demo:ks4000:1",
                scorer_valid=False,
            )
            record.update({"status": "EXCEPTION", "returned": False, "valid": False, "violations": ["exception"] + independent["violations"], "error": repr(exc), "independent_checks": independent["independent_checks"], "baseline_frozen_rows": independent["baseline_frozen_rows"]})
        emit(paths["outage"], record)

    reader_outcomes = PAPER / "source-data" / "v2" / "repair" / "outcomes.jsonl"
    reader_faults = PAPER / "source-data" / "v2" / "repair" / "faults.jsonl"
    ref = {
        "source": "v2 reader outage reference retained unchanged",
        "outcomes_sha256": digest(reader_outcomes),
        "faults_sha256": digest(reader_faults),
        "outcome_records": sum(1 for _ in reader_outcomes.open()),
        "fault_records": sum(1 for _ in reader_faults.open()),
        "scope": "v2 reference; no v3 overwrite and no claim of active-operation recovery",
    }
    (OUT / "reader_outage_reference.json").write_text(json.dumps(ref, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"priority_rule": chosen_rule, "truth_attempts": sum(1 for _ in paths["truth"].open()), "curve_runs": sum(1 for _ in paths["curve"].open()), "sgs_runs": sum(1 for _ in paths["sgs"].open()), "outage_runs": sum(1 for _ in paths["outage"].open())}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="execute the frozen v3 batch")
    args = parser.parse_args()
    if not args.run:
        raise SystemExit("Pass --run to execute the frozen batch.")
    run_all()
