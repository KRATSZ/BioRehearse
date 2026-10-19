"""Exploratory stronger KS4000 outage, separate from the frozen 180-s test."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PAPER = HERE.parents[2]
V2 = PAPER / "benchmarks" / "v2"
V3 = PAPER / "benchmarks" / "v3"
OUT = PAPER / "source-data" / "v3" / "scheduling" / "ks4000_outage_900s.jsonl"
sys.path.insert(0, str(V2))
sys.path.insert(0, str(PAPER / "reproducibility" / "source-v2"))
from common import read  # noqa: E402
from labscriptai.biofoundry.methods import compile_graph  # noqa: E402
from labscriptai.biofoundry.scheduling import replan, solve  # noqa: E402
from scorer import score  # noqa: E402
from run import verify_design  # noqa: E402
from schedule_audit import audit_replan  # noqa: E402


def main():
    if OUT.exists():
        raise RuntimeError(f"Refusing to overwrite {OUT}")
    design = read(V3 / "design.json")
    verify_design(design)
    workloads = read(V2 / "workloads.json")
    cases = {c["id"]: c for c in workloads["heldout"]}
    common = [cases[cid] for cid in design["common_subset_cases"]]
    catalog = read(PAPER / "source-data" / "v2" / "catalog.json")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    for case in common:
        graph = compile_graph(case["intent"], catalog)["graph"]
        baseline = solve(graph, catalog, case["layout"], "fastest", case["bookings"], time_limit_s=60)
        checked = score(baseline, graph, catalog, case["bookings"])
        ks = [r for r in baseline.get("rows", []) if r.get("kind") == "operation" and r.get("resource") == "demo:ks4000:1" and r.get("name") in {"incubate", "dark_incubation"}]
        if not (baseline.get("ok") and checked.get("valid") and ks):
            continue
        row = min(ks, key=lambda r: r["start_s"])
        now = max(0, int(row["start_s"]) - 60)
        repair = int(row["start_s"]) + 900
        record = {
            "case": case["id"],
            "load": case["load"],
            "handling_policy": case["handling_policy"],
            "fault_resource": "demo:ks4000:1",
            "fault_kind": "exploratory_known_outage_before_unstarted_step",
            "prespecified": False,
            "repair_window_s": 900,
            "now_s": now,
            "repair_s": repair,
            "affected_step": row["id"],
            "baseline_status": baseline.get("status"),
            "baseline_makespan_s": baseline.get("makespan_s"),
            "baseline_budget_s": 60,
            "baseline_independent_valid": True,
        }
        try:
            result = replan(copy.deepcopy(baseline), catalog, now, "demo:ks4000:1", repair, case["bookings"])
            result_score = score(result, graph, catalog, case["bookings"])
            independent = audit_replan(
                baseline,
                result,
                now_s=now,
                repair_s=repair,
                failed_resource="demo:ks4000:1",
                scorer_valid=bool(result_score.get("valid")),
            )
            record.update({
                "status": result.get("status"),
                "returned": bool(result.get("ok")),
                "valid": bool(independent["valid"]),
                "violations": list(result_score.get("violations", [])) + independent["violations"],
                "independent_checks": independent["independent_checks"],
                "baseline_frozen_rows": independent["baseline_frozen_rows"],
                "replanned_makespan_s": result.get("makespan_s"),
                "delta_makespan_s": result.get("makespan_s") - baseline.get("makespan_s") if result.get("ok") else None,
                "frozen_steps": result.get("replanning", {}).get("frozen_steps", []),
                "modified_unstarted_only": result.get("replanning", {}).get("only_unstarted_modified"),
            })
        except Exception as exc:
            independent = audit_replan(
                baseline,
                {},
                now_s=now,
                repair_s=repair,
                failed_resource="demo:ks4000:1",
                scorer_valid=False,
            )
            record.update({"status": "EXCEPTION", "returned": False, "valid": False, "violations": ["exception"] + independent["violations"], "error": repr(exc), "independent_checks": independent["independent_checks"], "baseline_frozen_rows": independent["baseline_frozen_rows"]})
        with OUT.open("a") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        count += 1
    print(json.dumps({"file": str(OUT), "records": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
