#!/usr/bin/env python3
"""Aggregate held-out biofoundry scheduling economics with the standard library.
Usage: --paper PAPER_ROOT --output NEW_DIR, or --self-test.
"""
import argparse, csv, gzip, hashlib, json, math, os, random, statistics, sys
from collections import defaultdict
EXPECTED_CASES, EXPECTED_RECORDS, BOOTSTRAP_DRAWS, BOOTSTRAP_SEED = 60, 1080, 10000, 20261019
OUT_FILES = ("outcomes.csv", "workload-metrics.csv", "paired-effects.csv", "utilization.csv", "summary.json")
F_OUT = "case,load,objective,method,repeat,valid,n_samples,makespan_s,time_h,cost_CNY,model_EPI,status,error".split(",")
F_WM = "case,load,objective,method,n_runs,n_valid,mean_time_h,mean_cost_CNY,mean_model_EPI".split(",")
F_PAIR = "objective,comparison,baseline,metric,n_workloads,paired_mean_pct_reduction,paired_median_pct_reduction,min_pct_reduction,max_pct_reduction,bootstrap_CI95_low,bootstrap_CI95_high".split(",")
F_UTIL = "case,objective,method,repeat,valid,resource,busy_seconds,makespan_seconds,utilization_fraction".split(",")
def key(row): return str(row["case"]), str(row["objective"]), str(row["method"]), int(row["repeat"])
def stream_jsonl(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip(): yield line_no, json.loads(line)
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""): h.update(block)
    return h.hexdigest()
def mean(values): return statistics.fmean(values) if values else None
def median(values): return statistics.median(values) if values else None
def pct_reduction(new, base): return None if new is None or base is None or base == 0 else 100.0 * (float(base) - float(new)) / float(base)
def epi(time_h, cost_cny, n_samples): return None if time_h is None or cost_cny is None or not n_samples else math.sqrt((float(time_h) / n_samples) * (float(cost_cny) / n_samples))
def union_seconds(intervals):
    merged = []
    for start, end in sorted((float(a), float(b)) for a, b in intervals if float(b) > float(a)):
        if merged and start <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], end)
        else: merged.append([start, end])
    return sum(end - start for start, end in merged)
def resource_busy(reservations):
    by_resource = defaultdict(list)
    for r in reservations or []:
        if isinstance(r, dict) and all(r.get(k) is not None for k in ("resource", "start_s", "end_s")): by_resource[str(r["resource"])].append((r["start_s"], r["end_s"]))
    return {resource: union_seconds(parts) for resource, parts in by_resource.items()}
def match_plans(records, plans):
    record_keys, plan_keys = {key(r) for r in records}, set(plans)
    missing, extra = record_keys - plan_keys, plan_keys - record_keys
    if missing: raise ValueError(f"missing plans for {len(missing)} scheduling keys, e.g. {sorted(missing)[:3]}")
    if extra: raise ValueError(f"{len(extra)} plans have no scheduling record, e.g. {sorted(extra)[:3]}")
def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore"); writer.writeheader()
        for row in rows: writer.writerow({f: "" if row.get(f) is None else (f"{row[f]:.10g}" if isinstance(row[f], float) else row[f]) for f in fields})
def bootstrap_mean_ci(values, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    if not values: return None, None
    rng, n = random.Random(seed), len(values)
    means = sorted(statistics.fmean(values[rng.randrange(n)] for _ in range(n)) for _ in range(draws))
    return means[int(0.025 * (draws - 1))], means[int(0.975 * (draws - 1))]
def load_cases(path):
    raw = json.load(open(path, encoding="utf-8")); items = raw.get("heldout", raw) if isinstance(raw, dict) else raw
    if not isinstance(items, list): raise ValueError("workloads JSON must contain a heldout list")
    cases = {}
    for item in items:
        case = str(item["id"])
        if case in cases: raise ValueError(f"duplicate workload case {case}")
        experiments = (item.get("intent") or {}).get("experiments") or []
        cases[case] = {"load": item.get("load"), "n_samples": sum(int(e.get("samples", 0) or 0) for e in experiments)}
    if len(cases) != EXPECTED_CASES: raise ValueError(f"expected {EXPECTED_CASES} heldout workloads, found {len(cases)}")
    return cases
def read_records(path):
    records, seen = [], {}
    for line_no, record in stream_jsonl(path):
        k = key(record)
        if k in seen: raise ValueError(f"key collision at scheduling lines {seen[k]} and {line_no}: {k}")
        seen[k] = line_no; records.append(record)
    if len(records) != EXPECTED_RECORDS: raise ValueError(f"expected {EXPECTED_RECORDS} scheduling records, found {len(records)}")
    return records
def read_plans(path):
    plans, seen = {}, {}
    for line_no, row in stream_jsonl(path):
        k = key(row)
        if k in seen: raise ValueError(f"plan key collision at lines {seen[k]} and {line_no}: {k}")
        seen[k] = line_no; plans[k] = row.get("plan") or row
    return plans
def per_load_summary(outcomes, cases):
    result, by_load = {}, defaultdict(list)
    for case, info in cases.items(): by_load[info["load"]].append(case)
    for load, ids in sorted(by_load.items(), key=lambda x: (x[0] is None, x[0])):
        rows = [r for r in outcomes if r["case"] in ids]; valid = [r for r in rows if r["valid"]]
        result[str(load)] = {"n_workloads": len(ids), "n_runs": len(rows), "n_valid_runs": len(valid),
            "n_fully_valid_workloads": sum(all(r["valid"] for r in rows if r["case"] == c) for c in ids),
            "mean_time_h": mean([r["time_h"] for r in valid]), "mean_cost_CNY": mean([r["cost_CNY"] for r in valid]),
            "mean_model_EPI": mean([r["model_EPI"] for r in valid])}
    return result
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper", help="read-only paper root"); parser.add_argument("--output", help="new output directory"); parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test: self_test(); return 0
    if not args.paper or not args.output: parser.error("--paper and --output are required unless --self-test is used")
    paper, output = os.path.abspath(args.paper), os.path.abspath(args.output)
    if os.path.exists(output): raise SystemExit(f"refusing existing output: {output}")
    paths = {"workloads": os.path.join(paper, "benchmarks/v2/workloads.json"), "scheduling": os.path.join(paper, "source-data/v2/heldout/scheduling.jsonl"), "plans": os.path.join(paper, "heldout/plans.jsonl.gz"), "catalog": os.path.join(paper, "source-data/v2/catalog.json")}
    if not os.path.exists(paths["plans"]): paths["plans"] = os.path.join(paper, "source-data/v2/heldout/plans.jsonl.gz")
    cases, records = load_cases(paths["workloads"]), read_records(paths["scheduling"]); plans = read_plans(paths["plans"])
    expected={(cid,obj,method,rep) for cid in cases for obj in ('fastest','cheapest') for method in ('cp_sat','parallel_greedy','serial_fifo') for rep in range(3)}
    actual={key(r) for r in records}
    if actual != expected:
        raise ValueError(f'incomplete expected run grid: missing={len(expected-actual)}, extra={len(actual-expected)}')
    match_plans(records, plans)
    if len(plans) != EXPECTED_RECORDS: raise ValueError(f"expected {EXPECTED_RECORDS} plans, found {len(plans)}")
    catalog = json.load(open(paths["catalog"], encoding="utf-8")); devices = {str(d) for d in (catalog.get("devices") or {})}
    observed = {str(r["resource"]) for p in plans.values() for r in (p.get("reservations") or []) if r.get("resource") is not None}
    resources = sorted(devices | observed | {"operator", "bench"}); os.makedirs(output); outcomes = []
    for record in records:
        case, objective, method, repeat = key(record)
        if case not in cases: raise ValueError(f"scheduling case absent from workloads: {case}")
        valid, n_samples = record.get("valid") is True, cases[case]["n_samples"]
        if valid and (record.get("makespan_s") is None or record.get("cost_cny") is None or n_samples <= 0): raise ValueError(f"valid record lacks complete metrics/sample denominator: {key(record)}")
        makespan = float(record["makespan_s"]) if record.get("makespan_s") is not None else None
        time_h, cost = (makespan / 3600.0 if valid else None), (float(record["cost_cny"]) if valid and record.get("cost_cny") is not None else None)
        outcomes.append(dict(case=case, load=cases[case]["load"], objective=objective, method=method, repeat=repeat, valid=valid, n_samples=n_samples,
            makespan_s=makespan, time_h=time_h, cost_CNY=cost, model_EPI=epi(time_h, cost, n_samples), status=record.get("status"), error=record.get("error")))
    write_csv(os.path.join(output, OUT_FILES[0]), F_OUT, outcomes); grouped = defaultdict(list)
    for row in outcomes: grouped[(row["case"], row["objective"], row["method"])].append(row)
    workload_metrics = []
    for (case, objective, method), rows in sorted(grouped.items()):
        eligible = [r for r in rows if r["valid"] and r["model_EPI"] is not None]
        workload_metrics.append(dict(case=case, load=cases[case]["load"], objective=objective, method=method, n_runs=len(rows), n_valid=len(eligible),
            mean_time_h=mean([r["time_h"] for r in eligible]), mean_cost_CNY=mean([r["cost_CNY"] for r in eligible]), mean_model_EPI=mean([r["model_EPI"] for r in eligible])))
    write_csv(os.path.join(output, OUT_FILES[1]), F_WM, workload_metrics); wm = {(r["case"], r["objective"], r["method"]): r for r in workload_metrics}
    methods = sorted({r["method"] for r in outcomes}); cp_methods = [m for m in methods if m.lower().startswith("cp")]
    if len(cp_methods) != 1: raise ValueError(f"expected one CP method, found {cp_methods}")
    cp_method, paired = cp_methods[0], []
    for objective in sorted({r["objective"] for r in outcomes}):
        for baseline in [m for m in methods if m != cp_method]:
            pairs = []
            for case in sorted(cases):
                cp, base = wm.get((case, objective, cp_method)), wm.get((case, objective, baseline))
                if cp and base and cp["n_runs"] == cp["n_valid"] and base["n_runs"] == base["n_valid"]: pairs.append((cp, base))
            if not pairs: raise ValueError(f"no jointly valid workloads for {objective}/{baseline}")
            for metric, label in (("mean_time_h", "time"), ("mean_cost_CNY", "cost"), ("mean_model_EPI", "EPI")):
                reductions = [x for x in (pct_reduction(cp[metric], base[metric]) for cp, base in pairs) if x is not None]
                row = dict(objective=objective, comparison=f"{cp_method}_vs_{baseline}", baseline=baseline, metric=label, n_workloads=len(reductions),
                    paired_mean_pct_reduction=mean(reductions), paired_median_pct_reduction=median(reductions), min_pct_reduction=min(reductions) if reductions else None, max_pct_reduction=max(reductions) if reductions else None)
                if label == "EPI": row["bootstrap_CI95_low"], row["bootstrap_CI95_high"] = bootstrap_mean_ci(reductions)
                paired.append(row)
    write_csv(os.path.join(output, OUT_FILES[2]), F_PAIR, paired); utilization = []
    for record, row in zip(records, outcomes):
        plan = plans[key(record)]; busy = resource_busy(plan.get("reservations"))
        makespan = row["makespan_s"] if row["makespan_s"] is not None else plan.get("makespan_s"); makespan = float(makespan) if makespan is not None else None
        for resource in resources:
            busy_s = busy.get(resource, 0.0)
            utilization.append(dict(case=row["case"], objective=row["objective"], method=row["method"], repeat=row["repeat"], valid=row["valid"], resource=resource,
                busy_seconds=busy_s, makespan_seconds=makespan, utilization_fraction=busy_s / makespan if makespan else None))
    write_csv(os.path.join(output, OUT_FILES[3]), F_UTIL, utilization); recipes = {}
    for plan in plans.values():
        for name, spec in ((plan.get("graph") or {}).get("methods") or {}).items():
            spec = spec or {}; recipes.setdefault(name, {"id": spec.get("id") or name, "version": spec.get("version"), "parameters": spec.get("parameters") or {}})
    counts = {"workloads": len(cases), "scheduling_records": len(records), "plans": len(plans), "outcomes": len(outcomes), "valid_records": sum(r["valid"] for r in outcomes),
        "invalid_records": sum(not r["valid"] for r in outcomes), "workload_metric_groups": len(workload_metrics), "paired_effect_rows": len(paired), "utilization_rows": len(utilization), "catalog_devices": len(devices)}
    assumptions = ["Recipes and rates are the supplied benchmark's demo planning assumptions, not vendor quotes or measured facility tariffs.",
        "EPI = sqrt((time_h/n_samples)*(cost_CNY/n_samples)); it is simulated and not a full techno-economic assessment.", "Costs are nominal and no economic realized savings are inferred.",
        "Assay mix varies with load; heterogeneous sample counts are not comparable biological output.", "Failed outcomes are retained with null computed time/cost/EPI; failure costs and times are never imputed."]
    summary = {"counts": counts, "labels": {"costs": "nominal planning costs (CNY), not realized savings", "EPI": "simulated model-based screening index, not a full techno-economic assessment", "sample_denominator": "sum of intent.experiments[].samples; controls and technical replicates excluded"},
        "recipes_assumed": recipes, "rates_assumed": catalog.get("costs") or {}, "assumptions": assumptions,
        "schema_notes": {"outcomes": "one row per matched record; invalid outcomes retained with null computed metrics", "workload-metrics.csv": "means within case/objective/method over repeated valid runs; n_runs and n_valid reported",
            "paired-effects.csv": "CP versus each baseline for each objective, restricted to workloads jointly valid for every repeat of both methods; reduction=(baseline-CP)/baseline*100", "utilization.csv": "union of busy reservation seconds per resource / makespan; zero-busy catalog devices included; null ratio if no makespan", "bootstrap": f"{BOOTSTRAP_DRAWS} workload draws with replacement, seed {BOOTSTRAP_SEED}, percentile 95% CI for mean EPI reduction"},
        "bootstrap": {"draws": BOOTSTRAP_DRAWS, "seed": BOOTSTRAP_SEED, "unit": "workload", "statistic": "paired mean EPI percent reduction"}, "per_load": per_load_summary(outcomes, cases), "paired_effects": paired,
        "source_files": {name: os.path.abspath(path) for name, path in paths.items()}, "input_sha256": {name: sha256(paths[name]) for name in ("workloads", "scheduling", "plans")}, "supporting_input_sha256": {"catalog": sha256(paths["catalog"])}}
    with open(os.path.join(output, OUT_FILES[4]), "w", encoding="utf-8") as fh: json.dump(summary, fh, indent=2, sort_keys=True); fh.write("\n")
    print(f"counts: {counts}")
    for row in paired:
        if row["metric"] == "EPI": print(f"{row['objective']} {row['comparison']}: mean EPI reduction {row['paired_mean_pct_reduction']:.2f}% (95% bootstrap CI {row['bootstrap_CI95_low']:.2f} to {row['bootstrap_CI95_high']:.2f}, n={row['n_workloads']})")
    print("recipes assumed: " + ", ".join(sorted(recipes))); print("rates assumed: " + json.dumps(summary["rates_assumed"], sort_keys=True))
    print("Note: costs are nominal; EPI is simulated screening, not full TEA; assay mix varies with load."); print(f"wrote {output}")
    return 0
def self_test():
    assert union_seconds([(0, 5), (3, 8), (10, 12)]) == 10.0 and union_seconds([]) == 0.0
    assert abs(epi(2.0, 8.0, 4) - 1.0) < 1e-12 and epi(None, 8.0, 4) is None and epi(2.0, 8.0, 0) is None
    try: match_plans([{"case": "c", "objective": "o", "method": "m", "repeat": 0}], {})
    except ValueError as exc: assert "missing plans" in str(exc)
    else: raise AssertionError("no-match error was not raised")
    print("self-test: ok")
if __name__ == "__main__":
    try: sys.exit(main())
    except (ValueError, KeyError, FileNotFoundError) as exc: print(f"error: {exc}", file=sys.stderr); sys.exit(2)
