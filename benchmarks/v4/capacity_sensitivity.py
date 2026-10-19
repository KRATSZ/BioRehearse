#!/usr/bin/env python3
"""Retrospective capacity-sensitivity study: baseline vs cloned shaker/reader.
Writes protocol.json before any solve, raw.jsonl (flushed per record),
plans.jsonl.gz (all plans) and summary.json into a fresh --output directory.
No original paper file is modified. --limit runs a labelled smoke subset.
"""
import argparse, copy, gzip, hashlib, json, statistics, sys, time
from datetime import datetime, timezone
from pathlib import Path
SCENARIOS = ("baseline", "add_shaker", "add_reader")
CLONES = {"add_shaker": ("demo:ks4000:1", "demo:ks4000:2", [0.6, 0.0]),
          "add_reader": ("device:67", "sensitivity:reader:2", [0.0, 0.6])}
SOURCE_FILES = [
    "reproducibility/source-v2/labscriptai/biofoundry/methods.py",
    "reproducibility/source-v2/labscriptai/biofoundry/scheduling.py",
    "reproducibility/source-v2/labscriptai/biofoundry/portfolio.py",
    "reproducibility/source-v2/labscriptai/biofoundry/workflow.py",
    "reproducibility/source-v2/labscriptai/biofoundry/capabilities.py",
    "benchmarks/v2/scorer.py", "benchmarks/scorer.py", "benchmarks/v2/common.py"]
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def objhash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def load(path):
    return json.loads(Path(path).read_text())
def emit(path, rec):
    with path.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False, allow_nan=False) + "\n")
        f.flush()
def modify(intent, catalog, scenario):
    """Deep-copy intent/catalog and clone one scalar resource for a scenario."""
    if scenario == "baseline":
        return copy.deepcopy(intent), copy.deepcopy(catalog), None
    source, new_key, offset = CLONES[scenario]
    cat = copy.deepcopy(catalog)
    clone = copy.deepcopy(cat["devices"][source])
    clone["id"] = new_key
    cat["devices"][new_key] = clone
    positions = {}
    for name, layout in cat["layouts"].items():
        pos = [float(a) + b for a, b in zip(layout["positions"][source], offset)]
        layout["positions"][new_key] = pos
        positions[name] = pos
    itt = copy.deepcopy(intent)
    itt["enabled_devices"] = list(itt.get("enabled_devices", [])) + [new_key]
    return itt, cat, {"cloned_from": source, "new_key": new_key, "offset": offset,
                      "device": clone, "layout_positions": positions}
def aggregate(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": statistics.mean(vals), "median": statistics.median(vals),
            "min": min(vals), "max": max(vals)}
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--budget", type=float, default=2.0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    paper, out = Path(args.paper).resolve(), Path(args.output).resolve()
    if args.budget <= 0 or args.limit < 0:
        raise SystemExit("budget must be positive and limit nonnegative")
    if out.exists():
        raise SystemExit(f"refusing existing output directory: {out}")
    out.mkdir(parents=True)
    sys.path.insert(0, str(paper / "benchmarks/v2"))
    sys.path.insert(0, str(paper / "reproducibility/source-v2"))
    from labscriptai.biofoundry.methods import compile_graph
    from labscriptai.biofoundry.scheduling import solve
    from labscriptai.biofoundry.portfolio import prepare_plan
    from scorer import score, states
    workloads = load(paper / "benchmarks/v2/workloads.json")["heldout"]
    if args.limit:
        workloads = workloads[:args.limit]
    catalog = load(paper / "source-data/v2/catalog.json")
    n = len(workloads)
    suite = "formal" if not args.limit else f"smoke{n}"
    hashes = {"workloads": {"path": "benchmarks/v2/workloads.json", "sha256": sha(paper / "benchmarks/v2/workloads.json")},
              "catalog": {"path": "source-data/v2/catalog.json", "sha256": sha(paper / "source-data/v2/catalog.json")}}
    protocol = {
        "study": "capacity_sensitivity", "suite": suite,
        "generated_utc": datetime.now(timezone.utc).isoformat(), "paper": str(paper),
        "budget_s_per_solve": args.budget, "planned_runs": n * len(SCENARIOS), "formal_planned_runs": 180,
        "scenarios": list(SCENARIOS), "inputs": hashes,
        "run_order": f"original case order 0..{n - 1}; each case baseline/add_shaker/add_reader",
        "source": {rel: sha(paper / rel) for rel in SOURCE_FILES},
        "runner_sha256": sha(Path(__file__)),
        "frozen_v2_manifest_sha256": sha(paper / "benchmarks/v2/frozen.json"),
        "unit_and_descriptive_analysis": (
            "Units: seconds (wall clock, makespan), CNY (cost), samples/hour (throughput). Descriptive only: "
            "per-scenario/load counts and paired within-case reductions where baseline and scenario are jointly "
            "valid; no inferential statistics."),
        "cloning_limitation": (
            "add_shaker/add_reader are hypothetical scalar-resource clones of demo:ks4000:1 and device:67 with "
            "identical properties and layout coordinates offset by [0.6,0] / [0,0.6]. They are not live "
            "installations; geometry/transport effects are modelled, not measured."),
        "procurement_roi": "Not assessed: no procurement cost, lead time or ROI analysis is performed.",
        "budget_note": "The same --budget solver time limit applies to every run and scenario.",
        "scorer": "benchmarks/v2/scorer.py independent arithmetic scorer + states audit",
    }
    (out / "protocol.json").write_text(json.dumps(protocol, indent=2, ensure_ascii=False) + "\n")
    records, raw_path = [], out / "raw.jsonl"
    with gzip.open(out / "plans.jsonl.gz", "wt") as plans:
        for index, case in enumerate(workloads):
            for scenario in SCENARIOS:
                started = time.perf_counter()
                intent, cat, snapshot = modify(case["intent"], catalog, scenario)
                plan, error, audit, exception, compiled = {}, None, None, False, False
                scored = {"returned": False, "valid": False, "violations": []}
                try:
                    comp = compile_graph(intent, cat)
                    compiled = bool(comp.get("ok"))
                    if compiled:
                        plan = solve(comp["graph"], cat, case["layout"], "fastest", case.get("bookings"),
                                     time_limit_s=args.budget)
                        scored = score(plan, comp["graph"], cat, case.get("bookings"))
                    else:
                        plan = {"ok": False, "status": "COMPILER_REJECT", "code": comp.get("code"),
                                "detail": comp.get("detail")}
                    if plan.get("ok"):
                        prepare_plan(plan, cat)
                        state = states(plan)
                        audit = {"material_valid": state["material_valid"], "mass_valid": state["mass_valid"],
                                 "location_issues": len(state["location_issues"]),
                                 "mass_issues": len(state["mass_issues"]), "event_count": state["event_count"]}
                    if compiled and not scored.get("valid"):
                        error = error or "scorer_invalid:" + ",".join(scored.get("violations", []))
                    if audit and not (audit["material_valid"] and audit["mass_valid"]):
                        error = error or "state_audit_failed"
                except Exception as exc:
                    error, exception = repr(exc), True
                    scored = {"returned": bool(plan.get("ok")), "valid": False, "violations": ["exception"]}
                wall = time.perf_counter() - started
                valid = bool(plan.get("ok") and scored.get("valid") and audit
                             and audit["material_valid"] and audit["mass_valid"] and not exception)
                rec = {"suite": suite, "case": case["id"], "case_index": index, "load": case["load"],
                       "handling_policy": case.get("handling_policy"), "layout": case["layout"], "scenario": scenario,
                       "budget_s": args.budget, "wall_s": wall, "compiled": compiled, "ok": bool(plan.get("ok")),
                       "status": plan.get("status"), "code": plan.get("code"), "error": error, "exception": exception,
                       "returned": scored.get("returned"), "score_valid": scored.get("valid"),
                       "violations": scored.get("violations"), "valid": valid, "makespan_s": plan.get("makespan_s"),
                       "cost_cny": plan.get("cost_cny"), "samples_per_hour": plan.get("samples_per_hour"),
                       "wells_per_hour": plan.get("wells_per_hour"), "proven_optimal": plan.get("proven_optimal"),
                       "solve_seconds": plan.get("solve_seconds"), "audit": audit, "intent_snapshot": intent,
                       "catalog_snapshot": snapshot,
                       "input_hashes": {"workloads": hashes["workloads"]["sha256"],
                                        "catalog_original": hashes["catalog"]["sha256"],
                                        "catalog_used": objhash(cat), "intent_used": objhash(intent)}}
                records.append(rec)
                emit(raw_path, rec)
                plans.write(json.dumps({"suite": suite, "case": case["id"], "scenario": scenario, "plan": plan},
                                       ensure_ascii=False, allow_nan=False) + "\n")
                plans.flush()
                print(f"[{len(records)}/{n * len(SCENARIOS)}] {case['id']} load={case['load']} {scenario} "
                      f"ok={rec['ok']} status={rec['status']} valid={valid} wall={wall:.2f}s", flush=True)
    loads = sorted({r["load"] for r in records})
    def subset(scenario, load=None):
        return [r for r in records if r["scenario"] == scenario and (load is None or r["load"] == load)]
    def counts(rs):
        ok = [r for r in rs if r["valid"]]
        return {"runs": len(rs), "returned": sum(1 for r in rs if r["ok"]), "valid": len(ok),
                "no_return": sum(1 for r in rs if not r["ok"]),
                "infeasible": sum(1 for r in rs if r["status"] == "INFEASIBLE"),
                "compiler_reject": sum(1 for r in rs if r["status"] == "COMPILER_REJECT"),
                "exceptions": sum(1 for r in rs if r["exception"]),
                "mean_wall_s": statistics.mean([r["wall_s"] for r in rs]) if rs else None,
                "mean_makespan_s_valid": statistics.mean([r["makespan_s"] for r in ok]) if ok else None,
                "mean_cost_cny_valid": statistics.mean([r["cost_cny"] for r in ok]) if ok else None}
    summary = {"suite": suite, "generated_utc": datetime.now(timezone.utc).isoformat(),
               "planned_runs": n * len(SCENARIOS), "records": len(records), "budget_s": args.budget,
               "counts_by_scenario_and_load": {s: {str(ld): counts(subset(s, ld)) for ld in loads} for s in SCENARIOS},
               "counts_by_scenario": {s: counts(subset(s)) for s in SCENARIOS},
               "status_counts": {s: {st: sum(1 for r in subset(s) if r["status"] == st)
                                    for st in sorted({r["status"] for r in records if r["status"]})}
                                 for s in SCENARIOS},
               "paired_vs_baseline_jointly_valid": {}, "newly_feasible_over_no_baseline_return": {}}
    by_case = {(r["case"], r["scenario"]): r for r in records}
    paired = ("makespan_reduction_s", "cost_reduction_cny", "samples_per_hour_delta")
    for scenario in ("add_shaker", "add_reader"):
        pairs, newly = [], []
        for case in workloads:
            base, scen = by_case.get((case["id"], "baseline")), by_case.get((case["id"], scenario))
            if not base or not scen:
                continue
            if not base["ok"] and scen["valid"]:
                newly.append({"case": case["id"], "load": case["load"], "baseline_status": base["status"]})
            if base["valid"] and scen["valid"]:
                pairs.append({"case": case["id"], "load": case["load"],
                              "makespan_reduction_s": base["makespan_s"] - scen["makespan_s"],
                              "cost_reduction_cny": base["cost_cny"] - scen["cost_cny"],
                              "samples_per_hour_delta": scen["samples_per_hour"] - base["samples_per_hour"]})
        summary["paired_vs_baseline_jointly_valid"][scenario] = {
            "overall": {"n_paired_valid": len(pairs), **{k: aggregate([p[k] for p in pairs]) for k in paired}},
            "by_load": {str(ld): {"n_paired_valid": len([p for p in pairs if p["load"] == ld]),
                                  **{k: aggregate([p[k] for p in pairs if p["load"] == ld]) for k in paired}}
                        for ld in loads}}
        summary["newly_feasible_over_no_baseline_return"][scenario] = {
            "rule": ("scenario valid while baseline returned no plan; baseline only called infeasible when "
                     "status==INFEASIBLE"),
            "count": len(newly), "by_load": {str(ld): sum(1 for x in newly if x["load"] == ld) for ld in loads},
            "cases": newly}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"suite": suite, "records": len(records), "output": str(out)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
