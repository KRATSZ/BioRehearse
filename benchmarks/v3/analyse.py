"""Summarise v3 scheduling evidence without changing raw JSONL attempts."""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve()
PAPER = HERE.parents[2]
OUT = PAPER / "source-data" / "v3" / "scheduling"
V2 = PAPER / "source-data" / "v2"
V3 = PAPER / "benchmarks" / "v3"


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_csv(path: Path, records: list[dict], fields: list[str]):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def main():
    truth = rows(OUT / "cp_sat_truth_runs.jsonl")
    curve = rows(OUT / "cp_sat_budget_curve.jsonl")
    sgs = rows(OUT / "sgs_runs.jsonl")
    outage = rows(OUT / "ks4000_outage.jsonl")
    exploratory_path = OUT / "ks4000_outage_900s.jsonl"
    exploratory = rows(exploratory_path) if exploratory_path.exists() else []
    workloads = json.loads((V3 / "design.json").read_text())
    case_meta = {c["id"]: c for c in json.loads((PAPER / "benchmarks" / "v2" / "workloads.json").read_text())["heldout"]}

    # The last escalation attempt is the final truth status; earlier failures
    # remain available in the raw JSONL and are counted separately below.
    final = {}
    for record in truth:
        final[record["case"]] = record
    final_rows = []
    for case_id in sorted(final):
        record = dict(final[case_id])
        record["truth_attempts"] = sum(r["case"] == case_id for r in truth)
        record["load"] = case_meta[case_id]["load"]
        if record.get("objective_value") is not None and record.get("best_bound") is not None:
            record["relative_bound_gap"] = (record["objective_value"] - record["best_bound"]) / record["objective_value"]
        else:
            record["relative_bound_gap"] = None
        final_rows.append(record)

    budget_rows = []
    for budget in (2, 10, 60):
        subset = [r for r in curve if r["budget_s"] == budget]
        budget_rows.append(
            {
                "budget_s": budget,
                "cases": len(subset),
                "returned": sum(r["returned"] for r in subset),
                "valid": sum(r["valid"] for r in subset),
                "feasible_certificate": sum(r["classification"] == "feasible_certificate" for r in subset),
                "infeasible_proof": sum(r["classification"] == "infeasible_proof" for r in subset),
                "unresolved": sum(r["classification"] == "unresolved" for r in subset),
                "optimal": sum(r["status"] == "OPTIMAL" for r in subset),
                "feasible_nonoptimal": sum(r["status"] == "FEASIBLE" for r in subset),
                "median_wall_s": statistics.median(r["wall_s"] for r in subset),
                "max_wall_s": max(r["wall_s"] for r in subset),
            }
        )
    write_csv(OUT / "budget-curve.csv", budget_rows, list(budget_rows[0]))

    curve_effects = []
    for case_id in sorted({r["case"] for r in curve}):
        for record in sorted((r for r in curve if r["case"] == case_id), key=lambda r: r["budget_s"]):
            curve_effects.append(
                {
                    "case": case_id,
                    "load": case_meta[case_id]["load"],
                    "handling_policy": case_meta[case_id]["handling_policy"],
                    "budget_s": record["budget_s"],
                    "status": record["status"],
                    "classification": record["classification"],
                    "valid": record["valid"],
                    "makespan_s": record["makespan_s"],
                    "objective_value": record["objective_value"],
                    "best_bound": record["best_bound"],
                    "relative_bound_gap": ((record["objective_value"] - record["best_bound"]) / record["objective_value"] if record.get("objective_value") is not None and record.get("best_bound") is not None else None),
                    "wall_s": record["wall_s"],
                }
            )
    write_csv(OUT / "budget-effects.csv", curve_effects, list(curve_effects[0]))

    truth_summary = {
        "cases": len(final_rows),
        "raw_attempts": len(truth),
        "escalated_cases": sum(sum(r["case"] == case_id for r in truth) > 1 for case_id in final),
        "final": dict(Counter(r["classification"] for r in final_rows)),
        "final_status": dict(Counter(r["status"] for r in final_rows)),
        "by_load": {
            str(load): {
                "cases": sum(r["load"] == load for r in final_rows),
                "classification": dict(Counter(r["classification"] for r in final_rows if r["load"] == load)),
                "status": dict(Counter(r["status"] for r in final_rows if r["load"] == load)),
            }
            for load in (1, 3, 6, 9, 12)
        },
        "unresolved_final_cases": [r["case"] for r in final_rows if r["classification"] == "unresolved"],
        "raw_unresolved_attempts": sum(r["classification"] == "unresolved" for r in truth),
    }

    # Paired effects use only jointly valid plans and never impute a missing SGS
    # plan.  The comparison is descriptive because SGS is a fixed-rule baseline.
    paired = []
    by_case = defaultdict(dict)
    for r in sgs:
        by_case[(r["case"], r["solver"])] = r
    for case_id in sorted({r["case"] for r in sgs}):
        cp = next((r for r in curve if r["case"] == case_id and r["budget_s"] == 60), None)
        if not cp or not cp["valid"]:
            continue
        for solver in ("serial_sgs", "parallel_sgs"):
            baseline = by_case.get((case_id, solver))
            if baseline and baseline["valid"]:
                paired.append(
                    {
                        "case": case_id,
                        "load": case_meta[case_id]["load"],
                        "baseline": solver,
                        "cp_makespan_s": cp["makespan_s"],
                        "baseline_makespan_s": baseline["makespan_s"],
                        "cp_minus_baseline_s": cp["makespan_s"] - baseline["makespan_s"],
                        "baseline_cost_cny": baseline["cost_cny"],
                        "cp_cost_cny": cp["cost_cny"],
                    }
                )
    if paired:
        write_csv(OUT / "sgs-paired-effects.csv", paired, list(paired[0]))
    sgs_summary = {
        solver: {
            "cases": sum(r["solver"] == solver for r in sgs),
            "returned": sum(r["solver"] == solver and r["returned"] for r in sgs),
            "valid": sum(r["solver"] == solver and r["valid"] for r in sgs),
            "valid_rate": sum(r["solver"] == solver and r["valid"] for r in sgs) / 20,
            "status": dict(Counter(r["status"] for r in sgs if r["solver"] == solver)),
            "paired_valid_cases": sum(r["baseline"] == solver for r in paired),
            "median_makespan_s": statistics.median([r["baseline_makespan_s"] for r in paired if r["baseline"] == solver]) if any(r["baseline"] == solver for r in paired) else None,
        }
        for solver in ("serial_sgs", "parallel_sgs")
    }

    outage_summary = {
        "cases": len(outage),
        "valid_replans": sum(r["valid"] for r in outage),
        "failed_replans": sum(not r["valid"] for r in outage),
        "status": dict(Counter(r["status"] for r in outage)),
        "delta_makespan_s": dict(Counter(r["delta_makespan_s"] for r in outage if r["delta_makespan_s"] is not None)),
        "scope": "Known 180-s outage placed 60 s before an unstarted KS4000 incubate; infeasible re-plans are retained, not imputed.",
    }
    outage_rows = [dict(r, load=case_meta[r["case"]]["load"], handling_policy=case_meta[r["case"]]["handling_policy"]) for r in outage]
    write_csv(OUT / "ks4000-outage.csv", outage_rows, list(outage_rows[0]))

    exploratory_summary = None
    if exploratory:
        exploratory_rows = [
            dict(r, load=case_meta[r["case"]]["load"], handling_policy=case_meta[r["case"]]["handling_policy"])
            for r in exploratory
        ]
        write_csv(OUT / "ks4000-outage-900s.csv", exploratory_rows, list(exploratory_rows[0]))
        exploratory_summary = {
            "cases": len(exploratory),
            "valid_replans": sum(r.get("valid") is True for r in exploratory),
            "failed_replans": sum(r.get("valid") is not True for r in exploratory),
            "status": dict(Counter(r.get("status") for r in exploratory)),
            "delta_makespan_s": dict(Counter(r.get("delta_makespan_s") for r in exploratory if r.get("delta_makespan_s") is not None)),
            "prespecified": False,
            "scope": "Exploratory 900-s known outage on the same fixed common subset; it was run after the prespecified 180-s analysis and is not used to select cases.",
        }

    summary = {
        "schema": "biorehearse.scheduling-summary.v3",
        "design": "benchmarks/v3/design.json",
        "truth": truth_summary,
        "budget_curve": budget_rows,
        "sgs": sgs_summary,
        "outage": outage_summary,
        "exploratory_outage_900s": exploratory_summary,
        "reader_reference": json.loads((OUT / "reader_outage_reference.json").read_text()),
        "scope": [
            "All outcomes are digital schedules under the registered catalog and assumptions.",
            "A feasible certificate is a returned plan independently scored as valid; an infeasible proof is an explicit CP-SAT INFEASIBLE status; UNKNOWN remains unresolved.",
            "SGS lookahead is a reported extension to the Kolisch skeleton, not a claim of a verbatim implementation of the original algorithm.",
            "The KS4000 test is known-outage rescheduling before an unstarted step; it does not demonstrate active hardware recovery.",
        ],
    }
    (OUT / "summary-scheduling-v3.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (OUT / "truth-final.json").write_text(json.dumps(final_rows, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
