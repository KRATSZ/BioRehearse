"""Contract-backed validation for the fifth (asset-lifecycle) layer.

This module deliberately calls the delivered digital asset contracts through
``sim.library_protocols``.  It does not infer a door, tray or hood from a
mesh name and it does not claim a hardware adapter.  The positive trace is
the same open -> load -> close -> start -> finish -> open -> unload -> close
workflow used by the v2 contract audit.  Negative traces are generated from
that contract's declared access joints and are labelled by construction; the
runner's rejection is reported separately.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

# .../virtual-lab/docs/paper/biofoundry-preprint/benchmarks/v3/validation.py
ROOT = Path(__file__).resolve().parents[5]
VLAB = Path(os.environ.get("BIOFOUNDRY_VLAB", str(ROOT)))
PAPER = ROOT / "docs" / "paper" / "biofoundry-preprint"
EXPORT = VLAB / "exports" / "biofoundry"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_library_protocols():
    path = VLAB / "sim" / "library_protocols.py"
    spec = importlib.util.spec_from_file_location("biofoundry_v3_library_protocols", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(VLAB))
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, path


def access_bindings():
    """Return only assets whose delivered binding declares access lifecycle."""
    mod, runner = load_library_protocols()
    library = mod.Library(EXPORT)
    rows = []
    for asset_id in sorted(library.assets):
        binding = library.select(asset_id=asset_id)
        if not binding.access:
            continue
        contract_path = EXPORT / "library" / asset_id / "asset.contract.json"
        contract = json.loads(contract_path.read_text())
        rows.append({
            "asset_id": asset_id,
            "device_id": binding.device_id,
            "contract_path": str(contract_path.relative_to(VLAB)),
            "contract_sha256": sha256(contract_path),
            "access_joint_names": [binding.joints[jid]["name"] for jid in binding.access],
            "access_node_ids": list(binding.access),
            "profile_source": (
                "asset.contract.json:digital_protocol_profile"
                if contract.get("digital_protocol_profile", {}).get("access_joint_names")
                else "sim/library_protocols.py:PROFILES"
            ),
            "protocol_scope": contract.get("protocol", {}).get("protocol_scope"),
            "protocol_access_lifecycle_tested": contract.get("protocol", {}).get("access_lifecycle_tested"),
        })
    return mod, runner, rows


def _reject(mod, run, name, expected_code, command, **kwargs):
    before = copy.deepcopy(run.state)
    observed = None
    error = None
    try:
        run.act(command, **kwargs)
    except mod.Blocked as exc:
        observed = exc.code
        error = str(exc)
    return {
        "case": name,
        "oracle_label": "known_violation",
        "expected_code_from_contract": expected_code,
        "observed_code": observed,
        "rejected": observed is not None,
        "oracle_independent_of_checker": True,
        "state_unchanged": before == run.state,
        "error": error,
    }


def run_contract_trace(mod, binding):
    """Run a valid contract trace and a fixed set of contract-derived faults."""
    run = mod.Run(binding, mod.demo_samples())
    run.act("open")
    run.act("load", sample_id="sample", origin="prep:sample")
    run.act("close")
    run.act("start")
    run.act("finish")
    run.act("open")
    origin = run.state["samples"]["sample"]["location"]
    run.act("unload", sample_id="sample", origin=origin, destination="prep:sample")
    run.act("close")
    positive = {
        "passed": True,
        "final_running": run.state["running"],
        "final_loaded": list(run.state["loaded"]),
        "event_count": len(run.state["events"]),
        "pose_count": len(run.state["pose_trace"]),
    }

    # Each case is a mutation of a fresh, known initial state.  The label is
    # assigned from the predeclared contract semantics, rather than from the
    # rejection code returned by Run.act.
    cases = []
    cases.append(_reject(mod, mod.Run(binding, mod.demo_samples()), "load_with_closed_access", "ACCESS_CLOSED", "load", sample_id="sample", origin="prep:sample"))
    run2 = mod.Run(binding, mod.demo_samples()); run2.act("open")
    cases.append(_reject(mod, run2, "load_with_wrong_origin", "WRONG_LOCATION", "load", sample_id="sample", origin="prep:wrong"))
    run3 = mod.Run(binding, mod.demo_samples()); run3.act("open"); run3.act("load", sample_id="sample", origin="prep:sample")
    cases.append(_reject(mod, run3, "start_with_access_open", "ACCESS_OPEN", "start"))
    run4 = mod.Run(binding, mod.demo_samples()); run4.act("open"); run4.act("load", sample_id="sample", origin="prep:sample"); run4.act("close"); run4.act("start")
    cases.append(_reject(mod, run4, "open_while_running", "BUSY", "open"))
    run5 = mod.Run(binding, mod.demo_samples()); run5.act("open"); run5.act("load", sample_id="sample", origin="prep:sample"); run5.act("close")
    cases.append(_reject(mod, run5, "load_twice", "ACCESS_CLOSED", "load", sample_id="sample", origin="device:sample"))
    run6 = mod.Run(binding, mod.demo_samples()); run6.act("open")
    cases.append(_reject(mod, run6, "unload_without_load", "NOT_LOADED", "unload", sample_id="sample", origin="prep:sample", destination="prep:other"))

    return positive, cases, run


def run_validation(output: Path | None = None):
    output = Path(output or PAPER / "source-data" / "v3" / "validation")
    output.mkdir(parents=True, exist_ok=True)
    mod, runner, bindings = access_bindings()
    rows = []
    for item in bindings:
        binding = mod.Library(EXPORT).select(asset_id=item["asset_id"])
        try:
            positive, cases, trace = run_contract_trace(mod, binding)
            rows.append({**item, "positive": positive, "cases": cases, "runner_source_sha256": sha256(runner), "status": "passed"})
        except Exception as exc:  # preserve failures as evidence rather than hiding them
            rows.append({**item, "status": "failed", "error_type": type(exc).__name__, "error": str(exc), "runner_source_sha256": sha256(runner)})
    (output / "contract-lifecycle.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    # A separate selected-asset workflow probe makes the boundary explicit:
    # this is a Workflow.act action trace over the delivered KS4000 binding,
    # not a claim that the compiled GFP/BCA/PicoGreen portfolio passed this
    # fifth layer.
    binding = mod.Library(EXPORT).select(asset_id="ika_ks4000")
    station = "ks4000"
    flow = mod.Workflow({station: binding}, mod.demo_samples())
    initial = copy.deepcopy(flow.state)
    try:
        flow.act(station, "load", sample_id="sample", origin="prep:sample")
        closed_code = None
        closed_state_unchanged = False
    except mod.Blocked as exc:
        closed_code = exc.code
        closed_state_unchanged = flow.state == initial
    flow.act(station, "open")
    flow.act(station, "load", sample_id="sample", origin="prep:sample")
    flow.act(station, "close")
    flow.act(station, "start")
    flow.act(station, "finish")
    flow.act(station, "open")
    origin = flow.state["samples"]["sample"]["location"]
    flow.act(station, "unload", sample_id="sample", origin=origin, destination="prep:sample")
    flow.act(station, "close")
    (output / "workflow-action-probe.json").write_text(json.dumps({
        "schema": "biofoundry.v3.asset-workflow-action-probe/1",
        "input_type": "asset_action_probe",
        "asset_id": binding.asset_id,
        "station": station,
        "interface": "sim.library_protocols.Workflow.act",
        "state_source": "sim.library_protocols.demo_samples()",
        "contract_sha256": sha256(EXPORT / "library" / "ika_ks4000" / "asset.contract.json"),
        "closed_door_load_expected": "ACCESS_CLOSED",
        "closed_door_load_observed": closed_code,
        "closed_door_load_rejected_atomically": closed_code == "ACCESS_CLOSED" and closed_state_unchanged,
        "positive_trace": ["open", "load", "close", "start", "finish", "open", "unload", "close"],
        "final_running": flow.state["stations"][station]["running"],
        "final_loaded": flow.state["stations"][station]["loaded"],
        "event_count": len(flow.state["events"]),
    }, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return rows


if __name__ == "__main__":
    result = run_validation()
    print(json.dumps({"assets": len(result), "passed": sum(r["status"] == "passed" for r in result)}, ensure_ascii=False))
