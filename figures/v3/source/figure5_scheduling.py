"""Figure 5: workload scaling, solver budgets and meaningful fault re-planning."""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

import matplotlib

matplotlib.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 6.5, "svg.fonttype": "none", "pdf.fonttype": 42, "savefig.dpi": 400,
})
# The shared save_figure helper invokes require_matplotlib_panel_alignment(...) after the final draw.
# Final editable exports: fig.savefig("figure.svg"), fig.savefig("figure.pdf"), fig.savefig("figure.png", dpi=400).

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sharedstyle import (  # noqa: E402
    ASSAY_COLORS,
    COLORS,
    DATA,
    DATA_V3,
    METHOD_COLORS,
    METHOD_LABELS,
    PAPER,
    V3,
    configure_axis,
    figure_size,
    method_color,
    panel,
    read_json,
    read_jsonl,
    save_figure,
)


METHODS = ["cp_sat", "parallel_greedy", "serial_sgs", "serial_fifo"]
SCHEDULE_LABELS = {"cp_sat": "CP-SAT", "serial_sgs": "Serial SGS", "parallel_sgs": "Parallel SGS"}
SCHEDULE_COLORS = {"cp_sat": COLORS["cp_sat"], "serial_sgs": COLORS["serial_sgs"], "parallel_sgs": COLORS["parallel_greedy"]}


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _schedule_rate() -> tuple[Path, list[dict]]:
    path = _first_existing(DATA_V3 / "scheduling-rate.csv", DATA_V3 / "scheduling_rate.csv")
    if path is not None:
        with path.open(newline="", encoding="utf-8") as handle:
            return path, list(csv.DictReader(handle))
    summary_path = DATA_V3 / "scheduling" / "summary-scheduling-v3.json"
    truth_path = DATA_V3 / "scheduling" / "truth-final.json"
    sgs_path = DATA_V3 / "scheduling" / "sgs_v33_runs.jsonl"
    if summary_path.exists() and truth_path.exists():
        truth = read_json(truth_path) if truth_path.suffix == ".json" else read_jsonl(truth_path)
        rows = []
        for load in sorted({int(item.get("load", 0)) for item in truth}):
            subset = [item for item in truth if int(item.get("load", 0)) == load]
            valid = sum(bool(item.get("valid")) and item.get("classification") == "feasible_certificate" for item in subset)
            rows.append({"method": "cp_sat", "load": load, "rate": valid / len(subset) if subset else float("nan"), "n": len(subset), "valid": valid, "objective": "fastest"})
        if sgs_path.exists():
            sgs = read_jsonl(sgs_path)
            for method in sorted({str(item.get("solver", "")) for item in sgs if item.get("solver")}):
                for load in sorted({int(item.get("load", 0)) for item in sgs if item.get("solver") == method}):
                    subset = [item for item in sgs if item.get("solver") == method and int(item.get("load", 0)) == load]
                    valid = sum(bool(item.get("valid")) for item in subset)
                    rows.append({"method": method, "load": load, "rate": valid / len(subset) if subset else float("nan"), "n": len(subset), "valid": valid, "objective": "fastest"})
        return summary_path, rows
    raise FileNotFoundError("A v3 scheduling truth or rate table is required for Fig. 5")


def _matched_validity() -> tuple[dict[str, Path], list[dict]]:
    """Load the matched 20-case comparison used for panel a.

    The budget-effects table contains the same 20 portfolios at each CP-SAT
    budget.  The SGS runs use the identical case list and retain both returned
    and failed schedules, so their denominators remain 20 at every load.
    """
    effects_path = DATA_V3 / "scheduling" / "budget-effects.csv"
    sgs_path = DATA_V3 / "scheduling" / "sgs_v33_runs.jsonl"
    if not effects_path.exists() or not sgs_path.exists():
        raise FileNotFoundError("Matched v3 CP-SAT and SGS records are required for Fig. 5a")
    with effects_path.open(newline="", encoding="utf-8") as handle:
        cp_rows = [row for row in csv.DictReader(handle) if str(row.get("budget_s")) == "2"]
    sgs_rows = read_jsonl(sgs_path)
    cases_cp = {str(row["case"]) for row in cp_rows}
    cases_sgs = {str(row["case"]) for row in sgs_rows}
    if cases_cp != cases_sgs or len(cases_cp) != 20:
        raise ValueError(f"Expected one matched 20-case subset, got CP={len(cases_cp)} SGS={len(cases_sgs)}")
    rows: list[dict] = []
    for load in sorted({int(row["load"]) for row in cp_rows}):
        cp_subset = [row for row in cp_rows if int(row["load"]) == load]
        rows.append({
            "method": "cp_sat", "load": load,
            "valid": sum(str(row.get("valid", "")).lower() == "true" for row in cp_subset),
            "n": len(cp_subset), "source": str(effects_path), "budget_s": 2,
        })
        for method, solver in (("serial_sgs", "serial_sgs_v33"), ("parallel_sgs", "parallel_sgs_v33")):
            subset = [row for row in sgs_rows if row.get("solver") == solver and int(row["load"]) == load and int(row["budget_s"]) == 2]
            rows.append({
                "method": method, "load": load,
                "valid": sum(bool(row.get("valid")) for row in subset),
                "n": len(subset), "source": str(sgs_path),
                "budget_s": 2, "recorded_budget_s": sorted({row.get("budget_s") for row in subset}),
            })
    return {"cp_sat": effects_path, "sgs": sgs_path}, rows


def _budget_sensitivity() -> tuple[dict[str, Path], list[dict]]:
    """Assemble the three-budget curves from independent raw result files."""
    cp_path = DATA_V3 / "scheduling" / "budget-curve.csv"
    sgs_path = DATA_V3 / "scheduling" / "sgs_v33_runs.jsonl"
    for path in (cp_path, sgs_path):
        if not path.exists():
            raise FileNotFoundError(f"Required budget-sensitivity evidence is missing: {path}")
    rows: list[dict] = []
    with cp_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "method": "cp_sat", "budget_s": int(float(row["budget_s"])),
                "valid": int(row["valid"]), "n": int(row["cases"]), "rate": int(row["valid"]) / int(row["cases"]),
                "source": str(cp_path),
            })
    sgs_rows = read_jsonl(sgs_path)
    for mode, method, solver in (("serial", "serial_sgs", "serial_sgs_v33"), ("parallel", "parallel_sgs", "parallel_sgs_v33")):
        for budget in (2, 10, 60):
            subset = [row for row in sgs_rows if row.get("mode") == mode and row.get("solver") == solver and int(row["budget_s"]) == budget]
            rows.append({
                "method": method, "budget_s": budget,
                "valid": sum(bool(row.get("valid")) for row in subset), "n": len(subset),
                "rate": sum(bool(row.get("valid")) for row in subset) / len(subset),
                "source": str(sgs_path), "recorded_budget_s": [budget],
            })
    return {"cp_sat": cp_path, "sgs_v33": sgs_path}, rows


def _budget_table() -> tuple[Path, list[dict]]:
    path = _first_existing(
        DATA_V3 / "budget-sensitivity.csv",
        DATA_V3 / "budget_sensitivity.csv",
        DATA_V3 / "solver-budget-sensitivity.csv",
    )
    if path is None:
        path = _first_existing(DATA_V3 / "scheduling" / "budget-curve.csv", DATA_V3 / "scheduling" / "budget-effects.csv")
    if path is None:
        raise FileNotFoundError("Prospective v3 budget-sensitivity.csv is required for Fig. 5b")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if "method" not in rows[0]:
        # The frozen summary curve is CP-SAT only.  Preserve the recorded
        # case denominator rather than treating an unresolved case as a
        # failed plan.
        grouped = {}
        for row in rows:
            budget = row.get("budget_s")
            if budget in (None, ""):
                continue
            bucket = grouped.setdefault(str(budget), {"budget_s": budget, "method": "cp_sat", "cases": 0, "valid": 0})
            bucket["cases"] += int(float(row.get("cases", 1) or 1))
            bucket["valid"] += int(float(row.get("valid", 0) or 0))
        rows = [{**bucket, "valid_rate": bucket["valid"] / bucket["cases"] if bucket["cases"] else float("nan")} for bucket in grouped.values()]
    required = {"budget_s", "method"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Budget table must contain {sorted(required)} columns; found {sorted(rows[0]) if rows else []}")
    return path, rows


def _ks_outage() -> tuple[Path, dict]:
    path = _first_existing(
        DATA_V3 / "ks4000-outage.json",
        DATA_V3 / "outage-ks4000.json",
        DATA_V3 / "fault-replan-ks4000.json",
    )
    if path is None:
        path = _first_existing(DATA_V3 / "scheduling" / "ks4000-outage-figure.json", DATA_V3 / "scheduling" / "ks4000_outage_figure.json")
    if path is not None:
        return path, read_json(path)

    # The frozen v3 outage table records the outcome and timestamps but not
    # full plan rows.  Reconstruct one representative trace with the same
    # registered compiler/solver/replan implementation, checking its
    # makespan against the recorded v3 outcome before drawing the Gantt.
    outcome_path = DATA_V3 / "scheduling" / "ks4000-outage.csv"
    if not outcome_path.exists():
        raise FileNotFoundError("Prospective v3 KS4000 outage plan records are required for Fig. 5d")
    with outcome_path.open(newline="", encoding="utf-8") as handle:
        outcomes = list(csv.DictReader(handle))
    representative = next((row for row in outcomes if str(row.get("valid", "")).lower() == "true"), None)
    if representative is None:
        raise ValueError("KS4000 outage table has no valid re-plan from which to draw panel d")
    import copy

    benchmark_v2 = PAPER / "benchmarks" / "v2"
    source_v2 = PAPER / "reproducibility" / "source-v2"
    for source in (benchmark_v2, source_v2):
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))
    from common import read  # noqa: PLC0415
    from labscriptai.biofoundry.methods import compile_graph  # noqa: PLC0415
    from labscriptai.biofoundry.scheduling import replan, solve  # noqa: PLC0415

    workloads = read(benchmark_v2 / "workloads.json")
    case = next(item for item in workloads["heldout"] if item["id"] == representative["case"])
    catalog = read(DATA / "catalog.json")
    graph = compile_graph(case["intent"], catalog)["graph"]
    baseline = solve(graph, catalog, case["layout"], "fastest", case["bookings"], time_limit_s=60)
    baseline_makespan = int(float(representative["baseline_makespan_s"]))
    if int(baseline.get("makespan_s", -1)) != baseline_makespan:
        raise ValueError("Reconstructed v3 outage baseline does not match recorded makespan")
    now_s = int(float(representative["now_s"]))
    repair_s = int(float(representative["repair_s"]))
    replanned = replan(copy.deepcopy(baseline), catalog, now_s, "demo:ks4000:1", repair_s, case["bookings"])
    if not replanned.get("ok"):
        raise ValueError("Recorded valid KS4000 outage case could not be reconstructed")
    return outcome_path, {
        "original": baseline,
        "replanned": replanned,
        "outage": {
            "start_s": now_s,
            "end_s": repair_s,
            "case": representative["case"],
            "affected_step": representative.get("affected_step", ""),
            "recorded_delta_makespan_s": representative.get("delta_makespan_s", ""),
        },
    }


def _number(row: dict, *keys: str, default=float("nan")) -> float:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            try:
                return float(row[key])
            except (TypeError, ValueError):
                pass
    return default


def _draw_validity(ax, rows: list[dict]):
    """Draw a matched-subset grouped rate comparison by portfolio load."""
    loads = sorted({int(row["load"]) for row in rows})
    methods = ["cp_sat", "serial_sgs", "parallel_sgs"]
    offsets = np.array([-0.24, 0.0, 0.24])
    width = 0.21
    for offset, method in zip(offsets, methods):
        subset = {int(row["load"]): row for row in rows if row["method"] == method}
        values = [100.0 * float(subset[load]["valid"]) / float(subset[load]["n"]) for load in loads]
        bars = ax.bar(
            np.arange(len(loads)) + offset,
            values,
            width=width,
            color=SCHEDULE_COLORS[method],
            edgecolor="white",
            linewidth=0.35,
            label=SCHEDULE_LABELS[method],
            zorder=2,
        )
        for bar, load in zip(bars, loads):
            row = subset[load]
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                max(5.0, float(bar.get_height()) - 5.0),
                f"{row['valid']}/{row['n']}",
                ha="center", va="top", fontsize=5.8, color="white", zorder=3,
            )
    ax.set_ylim(0, 108)
    ax.set_ylabel("Valid plan rate (%)")
    ax.set_xlabel("Experiments per portfolio")
    ax.set_xticks(np.arange(len(loads)), [str(load) for load in loads])
    ax.legend(frameon=False, fontsize=5.8, loc="upper right", handlelength=1.2, ncol=1)
    configure_axis(ax, grid=False)
    ax.text(0.0, -0.22, "Matched subset: 20 portfolios (four per load); labels show valid / tested.",
            transform=ax.transAxes, fontsize=5.8, color=COLORS["muted"])
    panel(ax, "a", "Constraint validity on a matched workload subset")


def _draw_budget(ax, rows: list[dict]):
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row["method"]), []).append(row)
    for method in ("cp_sat", "serial_sgs", "parallel_sgs"):
        subset = sorted(grouped.get(method, []), key=lambda row: _number(row, "budget_s"))
        if not subset:
            continue
        x = [_number(row, "budget_s") for row in subset]
        y = [100 * _number(row, "rate") for row in subset]
        color = SCHEDULE_COLORS[method]
        ax.plot(x, y, "o-", color=color, ms=3.2, lw=0.9,
                label=SCHEDULE_LABELS[method], zorder=3)
        for xi, yi in zip(x, y):
            ax.annotate(f"{int(round(yi / 5))}/20", (xi, yi), xytext=(0, 4), textcoords="offset points",
                        ha="center", va="bottom", fontsize=5.6, color=color)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("Planning budget (s)")
    ax.set_ylabel("Valid plan rate (%)")
    ax.set_ylim(-3, 105)
    ax.set_xticks([2, 10, 60])
    ax.set_xticklabels(["2", "10", "60"])
    ax.legend(frameon=False, fontsize=5.8, loc="lower right", handlelength=1.2)
    configure_axis(ax, grid=False)
    ax.text(0.0, -0.22, "Same 20 cases rerun at 2, 10 and 60 s; points are valid / tested.",
            transform=ax.transAxes, fontsize=5.8, color=COLORS["muted"])
    panel(ax, "b", "Longer allowances preserve return counts in this subset")


def _truth_counts() -> tuple[Path, list[dict], dict]:
    truth_path = DATA_V3 / "scheduling" / "truth-final.json"
    followup_path = DATA_V3 / "scheduling" / "cp_sat_unknown_300s_followup.json"
    if not truth_path.exists() or not followup_path.exists():
        raise FileNotFoundError("Final v3 truth and unresolved-case follow-up are required for Fig. 5c")
    truth = read_json(truth_path)
    followup = read_json(followup_path)
    rows: list[dict] = []
    for load in sorted({int(row["load"]) for row in truth}):
        subset = [row for row in truth if int(row["load"]) == load]
        rows.append({
            "load": load,
            "feasible": sum(row.get("classification") == "feasible_certificate" for row in subset),
            "infeasible": sum(row.get("classification") == "infeasible_proof" for row in subset),
            "unresolved": sum(row.get("classification") == "unresolved" for row in subset),
            "n": len(subset),
            "source": str(truth_path),
        })
    return truth_path, rows, {"path": followup_path, **followup}


def _draw_feasibility(ax, rows: list[dict], followup: dict):
    loads = [int(row["load"]) for row in rows]
    x = np.arange(len(loads))
    bottom = np.zeros(len(loads), dtype=float)
    statuses = [
        ("feasible", "Feasible certificate", COLORS["pass"]),
        ("infeasible", "Proven infeasible", COLORS["warning"]),
        ("unresolved", "Unresolved in staged run", "white"),
    ]
    for key, label, color in statuses:
        values = np.array([int(row[key]) for row in rows], dtype=float)
        bars = ax.bar(x, values, bottom=bottom, width=0.56, color=color,
                      edgecolor=COLORS["ink"] if key == "unresolved" else "white",
                      linewidth=0.55, label=label, zorder=2)
        for bar, value in zip(bars, values):
            if value <= 0:
                continue
            text_color = "white" if key != "unresolved" else COLORS["ink"]
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_y() + value / 2,
                    f"{int(value)}", ha="center", va="center", fontsize=5.8,
                    color=text_color, zorder=3)
        bottom += values
    ax.set_xticks(x, [str(load) for load in loads])
    ax.set_xlabel("Experiments per portfolio")
    ax.set_ylabel("Number of portfolios")
    ax.set_ylim(0, 14.5)
    # A compact text key stays above the bars and avoids placing a legend
    # handle across the unresolved segment of the load-9 bar.
    ax.text(0.48, 1.12, "feasible", transform=ax.transAxes, fontsize=5.6, color=COLORS["pass"], ha="left")
    ax.text(0.66, 1.12, "infeasible", transform=ax.transAxes, fontsize=5.6, color=COLORS["warning"], ha="left")
    ax.text(0.84, 1.12, "unresolved", transform=ax.transAxes, fontsize=5.6, color=COLORS["ink"], ha="left")
    configure_axis(ax, grid=False)
    followup_s = float(followup.get("wall_s", 0.0))
    ax.annotate(
        f"Staged run up to 60 s: 1 unresolved\nfollow-up proof at {followup_s:.1f} s",
        xy=(3, 12.0), xycoords="data", xytext=(2.3, 14.1), textcoords="data",
        arrowprops={"arrowstyle": "-", "color": COLORS["muted"], "lw": 0.6},
        fontsize=5.6, color=COLORS["muted"], ha="left", va="top",
    )
    ax.text(0.0, -0.36,
            "Staged run up to 60 s: 53 feasible / 6 infeasible / 1 unresolved\nfollow-up proof at 93.6 s.",
            transform=ax.transAxes, fontsize=5.8, color=COLORS["muted"])
    panel(ax, "c", "Model feasibility across 60 portfolios")


def _rows_from_outage(data: dict) -> tuple[dict, dict, dict]:
    """Accept the compact v3 outage schema or a pair of recorded plans."""
    if "original" in data and "replanned" in data:
        return data["original"], data["replanned"], data.get("outage", {})
    if "before" in data and "after" in data:
        return data["before"], data["after"], data.get("fault", {})
    raise ValueError("KS4000 outage JSON must contain original/replanned plan records")


def _outage_summary() -> tuple[Path, Path, dict]:
    prespecified = DATA_V3 / "scheduling" / "ks4000-outage.csv"
    exploratory = DATA_V3 / "scheduling" / "ks4000-outage-900s.csv"
    if not prespecified.exists() or not exploratory.exists():
        raise FileNotFoundError("KS4000 outage summary tables are required for Fig. 5d")
    with prespecified.open(newline="", encoding="utf-8") as handle:
        rows_180 = list(csv.DictReader(handle))
    with exploratory.open(newline="", encoding="utf-8") as handle:
        rows_900 = list(csv.DictReader(handle))
    summary = {
        "prespecified_cases": len(rows_180),
        "prespecified_valid": sum(str(row.get("valid", "")).lower() == "true" for row in rows_180),
        "exploratory_cases": len(rows_900),
        "exploratory_valid": sum(str(row.get("valid", "")).lower() == "true" for row in rows_900),
        "delta_s": sorted({int(float(row["delta_makespan_s"])) for row in rows_180 if row.get("delta_makespan_s")}),
        "prespecified_source": str(prespecified),
        "exploratory_source": str(exploratory),
    }
    return prespecified, exploratory, summary


def _draw_outage(ax, outage: dict, summary: dict):
    original, replanned, fault = _rows_from_outage(outage)
    plans = [original, replanned]
    names = ["Before outage", "After bounded re-plan"]
    resources = ["device:19", "device:18", "demo:ks4000:1", "device:67", "bench", "operator"]
    labels = ["Fluent 1080", "Fluent 780", "KS4000", "iD5", "Human bench", "Operator"]
    methods_by_plan = [
        {str(ex["id"]): str(ex["method"]) for ex in plan.get("graph", {}).get("experiments", [])}
        for plan in plans
    ]
    for i, plan in enumerate(plans):
        for row in plan.get("rows", []):
            if row.get("kind") != "operation" or row.get("resource") not in resources:
                continue
            y = i * 6 + resources.index(row["resource"])
            method = methods_by_plan[i].get(str(row.get("experiment")), "gfp")
            color = COLORS.get(method, ASSAY_COLORS.get(method, COLORS["neutral"]))
            ax.broken_barh([(row["start_s"] / 3600.0, (row["end_s"] - row["start_s"]) / 3600.0)], (y - 0.25, 0.50), facecolor=color, edgecolor="white", lw=0.2)
    outage_start = _number(fault, "start_s", "outage_start_s", default=float("nan"))
    outage_end = _number(fault, "end_s", "outage_end_s", default=float("nan"))
    if np.isfinite(outage_start) and np.isfinite(outage_end):
        ax.axvspan(outage_start / 3600.0, outage_end / 3600.0, color="#F3D7D9", alpha=0.75, zorder=0)
        # The shaded band and the inset carry the outage marker; omitting a
        # label on the full Gantt keeps the annotation clear of the band edge.
    ax.set_yticks([2.5, 8.5], names)
    ax.set_ylim(11.8, -0.8)
    ax.set_xlabel("Time after 09:00 (h)")
    ax.grid(axis="x", color="#E8EAEC", lw=0.45)
    ax.set_axisbelow(True)
    ax.tick_params(length=2, pad=2)
    panel(ax, "d", "Bottleneck outage and bounded replanning")
    ax.text(
        0.0, -0.25,
        f"180-s: {summary['prespecified_valid']}/{summary['prespecified_cases']} valid; Δmakespan +180 s\n"
        f"900-s exploratory: {summary['exploratory_valid']}/{summary['exploratory_cases']} valid.",
        transform=ax.transAxes, fontsize=5.7, color=COLORS["muted"],
    )
    return plans, fault


def _draw_outage_inset(fig, plans: list[dict], fault: dict):
    """Show the first 20 min so the known outage and local shift are visible."""
    inset = fig.add_axes((0.785, 0.315, 0.155, 0.085), facecolor="white")
    resources = ["demo:ks4000:1", "bench", "operator"]
    labels = ["KS4000", "Bench", "Operator"]
    methods_by_plan = [
        {str(ex["id"]): str(ex["method"]) for ex in plan.get("graph", {}).get("experiments", [])}
        for plan in plans
    ]
    for i, plan in enumerate(plans):
        for row in plan.get("rows", []):
            if row.get("kind") != "operation" or row.get("resource") not in resources:
                continue
            if float(row.get("start_s", 0)) > 1200 or float(row.get("end_s", 0)) < 0:
                continue
            y = i * len(resources) + resources.index(row["resource"])
            method = methods_by_plan[i].get(str(row.get("experiment")), "gfp")
            color = ASSAY_COLORS.get(method, COLORS["neutral"])
            inset.broken_barh(
                [(max(0.0, row["start_s"]) / 60.0, (min(1200.0, row["end_s"]) - max(0.0, row["start_s"])) / 60.0)],
                (y - 0.22, 0.44), facecolor=color, edgecolor="white", lw=0.18,
            )
    start = _number(fault, "start_s", "outage_start_s", default=float("nan")) / 60.0
    end = _number(fault, "end_s", "outage_end_s", default=float("nan")) / 60.0
    if np.isfinite(start) and np.isfinite(end):
        inset.axvspan(start, min(20.0, end), color="#F3D7D9", alpha=0.7, zorder=0)
    inset.set_xlim(0, 20)
    inset.set_ylim(8.8, -0.8)
    inset.set_yticks([])
    inset.set_xticks([0, 20], ["0", "20"])
    inset.tick_params(labelsize=5.8, length=0, pad=1)
    for spine in ("top", "right"):
        inset.spines[spine].set_visible(False)
    return inset


def main() -> None:
    validity_sources, validity_rows = _matched_validity()
    budget_sources, budget_rows = _budget_sensitivity()
    truth_path, feasibility_rows, followup = _truth_counts()
    outage_prespecified_path, outage_exploratory_path, outage_summary = _outage_summary()
    outage_path, outage = _ks_outage()
    fig = plt.figure(figsize=figure_size(160), facecolor="white")
    a = fig.add_axes((0.095, 0.59, 0.37, 0.30), facecolor="white")
    b = fig.add_axes((0.59, 0.59, 0.37, 0.30), facecolor="white")
    c = fig.add_axes((0.095, 0.13, 0.37, 0.30), facecolor="white")
    d = fig.add_axes((0.59, 0.13, 0.37, 0.30), facecolor="white")
    _draw_validity(a, validity_rows)
    _draw_budget(b, budget_rows)
    _draw_feasibility(c, feasibility_rows, followup)
    outage_plans, outage_fault = _draw_outage(d, outage, outage_summary)
    _draw_outage_inset(fig, outage_plans, outage_fault)
    V3.mkdir(parents=True, exist_ok=True)
    with (V3 / "fig5_scheduling-source.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["table", "source", "method", "load", "budget_s", "rate", "valid", "n", "makespan_s", "cost_cny"])
        for row in validity_rows:
            writer.writerow(["matched_validity", row.get("source"), row.get("method"), row.get("load"), row.get("budget_s"), float(row.get("valid", 0)) / float(row.get("n", 1)), row.get("valid"), row.get("n"), "", ""])
        for row in budget_rows:
            writer.writerow(["budget", row.get("source"), row.get("method"), row.get("load", ""), row.get("budget_s"), row.get("rate", ""), row.get("valid"), row.get("n"), "", ""])
        for row in feasibility_rows:
            writer.writerow(["feasibility_truth", row.get("source"), "", row.get("load"), "", "", f"feasible={row['feasible']};infeasible={row['infeasible']};unresolved={row['unresolved']}", row.get("n"), "", ""])
        writer.writerow(["followup", followup.get("path"), "cp_sat", 9, 300, "", followup.get("classification"), "", "", ""])
        writer.writerow(["outage", outage_summary.get("prespecified_source"), "ks4000", "", 180, outage_summary.get("prespecified_valid", 0) / outage_summary.get("prespecified_cases", 1), outage_summary.get("prespecified_valid"), outage_summary.get("prespecified_cases"), outage.get("replanned", {}).get("makespan_s", ""), ""])
        writer.writerow(["outage_exploratory", outage_summary.get("exploratory_source"), "ks4000", "", 900, outage_summary.get("exploratory_valid", 0) / outage_summary.get("exploratory_cases", 1), outage_summary.get("exploratory_valid"), outage_summary.get("exploratory_cases"), "", ""])
    save_figure(
        fig,
        "fig5_scheduling",
        [a, b, c, d],
        panel_ids=["validity", "budget", "frontier", "outage"],
        row_groups=[["validity", "budget"], ["frontier", "outage"]],
        column_groups=[["validity", "frontier"], ["budget", "outage"]],
        height_mm=160,
    )


if __name__ == "__main__":
    main()
