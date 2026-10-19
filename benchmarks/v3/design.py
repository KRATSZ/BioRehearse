"""Prospective v3 scheduling design.

The v2 workload and scorer are immutable.  This module creates a new design
record that fixes the cases, solver budgets, baseline rules and outage policy
before any v3 held-out result is inspected.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path


HERE = Path(__file__).resolve()
PAPER = HERE.parents[2]
V2 = PAPER / "benchmarks" / "v2"
OUT = PAPER / "benchmarks" / "v3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def tracked_hashes() -> tuple[dict[str, str], dict[str, str]]:
    """Return the v3 implementation and read-only dependency manifests."""
    code_paths = [
        OUT / "design.py",
        OUT / "run.py",
        OUT / "sgs.py",
        OUT / "schedule_audit.py",
        OUT / "analyse.py",
        OUT / "ks4000_exploratory.py",
    ]
    dependency_paths = [
        V2 / "common.py",
        V2 / "scorer.py",
        V2 / "frozen.json",
    ]
    dependency_paths.extend(sorted((PAPER / "reproducibility" / "source-v2" / "labscriptai").rglob("*.py")))
    code = {str(path.relative_to(PAPER)): sha256(path) for path in code_paths}
    dependencies = {str(path.relative_to(PAPER)): sha256(path) for path in dependency_paths}
    return code, dependencies


def manifest_hash(code: dict[str, str], dependencies: dict[str, str], inputs: dict[str, str]) -> str:
    items = []
    for section in ("code_hashes", "dependency_hashes", "inputs"):
        values = {"code_hashes": code, "dependency_hashes": dependencies, "inputs": inputs}[section]
        items.extend((section, relative, expected) for relative, expected in sorted(values.items()))
    return hashlib.sha256(json.dumps(items, separators=(",", ":")).encode()).hexdigest()


def balanced_subset(cases: list[dict], per_load: int = 4) -> list[dict]:
    """Select a deterministic, load-balanced subset without solver outcomes."""
    selected = []
    for load in (1, 3, 6, 9, 12):
        group = [c for c in cases if c["load"] == load]
        # The held-out stream is ordered as standard/tight × horizon × repeats.
        # Taking four evenly spaced cases keeps both handling policies and both
        # horizons represented without looking at a result file.
        indices = [0, 3, 6, 9]
        selected.extend(group[i] for i in indices[:per_load])
    return selected


def main() -> None:
    workloads = load(V2 / "workloads.json")
    heldout = workloads["heldout"]
    development = workloads["development"]
    assert len(heldout) == 60
    subset = balanced_subset(heldout)
    assert len(subset) == 20

    # Freeze the exact input identities and hashes.  The run script refuses to
    # continue if these files are changed after this design has been created.
    code_hashes, dependency_hashes = tracked_hashes()
    inputs = {
        "benchmarks/v2/workloads.json": sha256(V2 / "workloads.json"),
        "source-data/v2/catalog.json": sha256(PAPER / "source-data" / "v2" / "catalog.json"),
    }
    design = {
        "schema": "biorehearse.scheduling-design.v3",
        "freeze_id": "v3-final-2026-10-19",
        "created": "2026-10-19",
        "purpose": "prospective scheduling validation; v2 artifacts remain immutable",
        "primary_claim": "A constraint-aware planner can produce valid schedules under shared-device, operator, transport, release and sample-window constraints; standard SGS provides an independent parallel scheduling comparator.",
        "test_split": "v2 heldout workloads; this is a retrospectively extended analysis of an existing computational test stream, prospectively frozen here before v3 runs",
        "all_test_cases": [c["id"] for c in heldout],
        "common_subset_cases": [c["id"] for c in subset],
        "development_cases": [c["id"] for c in development],
        "objectives": ["fastest"],
        "cp_sat_budgets_s": [2, 10, 60],
        "budget_curve_cases": "all 20 common-subset cases are run independently at each of 2, 10 and 60 s; a 60-s run is not imputed from a shorter run",
        "budget_policy": {
            "truth_escalation": "For the 60-case status table, run 2 s first and extend only cases still unresolved to 10 s and then 60 s. The separate 20-case budget curve runs every case at all three budgets.",
            "classification": {
                "feasible_certificate": ["FEASIBLE", "OPTIMAL"],
                "infeasible_proof": ["INFEASIBLE"],
                "unresolved": ["UNKNOWN", "BUDGET_EXHAUSTED", "SOLVER_UNRESOLVED"],
            },
            "rule": "A solver timeout or UNKNOWN is never reclassified as infeasible.",
        },
        "sgs": {
            "family": "Kolisch serial and parallel resource-constrained project scheduling schemes",
            "variants": ["serial_sgs", "parallel_sgs"],
            "candidate_priority_rules": [
                "input_order",
                "minimum_slack",
                "longest_remaining_path",
                "earliest_release",
            ],
            "selection": "Select one fixed rule on the six development cases using valid-plan rate, then mean makespan among valid plans, with input_order as deterministic tie-break. Freeze before test execution.",
            "lookahead": "A bounded forward-check for immediate maximum-wait children is enabled to avoid dispatching a predecessor that has no legal successor slot; this is an explicit extension to the Kolisch SGS skeleton and is reported separately from the original scheme.",
            "constraints": [
                "registered device capability and labware",
                "device availability and one-instance occupancy",
                "shared operator occupancy",
                "precedence and explicit transport reservations",
                "release times and deadlines",
                "assay-specific sample waiting windows",
                "nominal operating budget",
            ],
            "scorer": "benchmarks/v2/scorer.py, loaded read-only and unchanged",
        },
        "ks4000_outage": {
            "policy": "known outage before an unstarted KS4000 incubate step; replan only unstarted steps and preserve all rows completed by now",
            "repair_window_s": 180,
            "selection": "up to 20 common-subset cases with a valid baseline containing KS4000 incubate; choose earliest eligible case IDs without using post-outage results",
            "interpretation": "This is bounded digital rescheduling under a known calendar outage, not automatic recovery from an active hardware failure.",
        },
        "reader_reference": {
            "source": "source-data/v2/repair/outcomes.jsonl and faults.jsonl",
            "preserve": True,
            "interpretation": "The v2 reader-outage result is retained as a negative/zero-delay reference; v3 does not overwrite it.",
        },
        "execution": {
            "single_solver_worker": True,
            "random_seed": 7,
            "repeats": 1,
            "reason": "The planners are deterministic under a fixed catalog and seed; this extension measures budget/status sensitivity, not stochastic variance.",
            "wall_clock_note": "Wall time is recorded and may overlap native rendering on the host; it is not treated as a hardware throughput measurement.",
        },
        "code_hashes": code_hashes,
        "dependency_hashes": dependency_hashes,
        "inputs": inputs,
        "runtime": {
            "python_version": platform.python_version(),
            "ortools_version": importlib.metadata.version("ortools"),
            "single_solver_worker": True,
        },
    }
    design["manifest_sha256"] = manifest_hash(code_hashes, dependency_hashes, inputs)
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "design.json"
    if target.exists():
        raise RuntimeError(f"Refusing to overwrite frozen design: {target}")
    target.write_text(json.dumps(design, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"design": str(target), "all_cases": 60, "common_cases": 20}, ensure_ascii=False))


if __name__ == "__main__":
    main()
