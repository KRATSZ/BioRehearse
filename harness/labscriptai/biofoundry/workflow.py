"""One simulation state machine, shared by CLI, UI and harness tools.

Every accepted command commits one atomic state/event snapshot. A rejected
command changes neither volumes nor locations. There is no hardware adapter.
"""
from __future__ import annotations

import copy
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path

from labscriptai.planir.schema import load_plan
from labscriptai.planir.virtual_deck import evaluate_virtual_deck
from .baseline import cards


class Blocked(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)


def require(condition, code, detail):
    if not condition:
        raise Blocked(code, detail)


def baseline(replicates=3):
    require(type(replicates) is int and 1 <= replicates <= 4, "CAPACITY", "Demo racks support 1–4 replicates per group")
    config = cards()
    config["demo_configuration"]["replicates_per_group"] = replicates
    config["devices"] = {"liquid": "Fluent1080", "reader": "SpectraMax_iD5", "plate": "black_96_flat", "tips_ul": 200}
    config["tips_available"] = 96
    containers = {}

    def add(cid, kind, location, capacity, volume=0, component=None, parent=None):
        containers[cid] = {"id": cid, "kind": kind, "location": location,
                           "capacity_ul": capacity, "volume_ul": volume,
                           "components_ul": {component: volume} if component else {},
                           "sample_ids": [f"sample:{cid}"] if kind == "reaction_tube" else [],
                           "parent": parent, "dead_volume_ul": 0, "closure": "open" if kind in ("stock_tube","reaction_tube") else None}

    for cid, volume in config["demo_configuration"]["source_inventory_ul"].items():
        add(cid, "stock_tube", f"prep.stock:{cid}", 1500, volume, cid)
        containers[cid]["dead_volume_ul"] = config["demo_configuration"]["reserved_dead_volume_ul"][cid]
    add("P01", "read_plate", "prep.plate:1", 0)
    for i in range(1, replicates*2+1):
        add(f"T{i}", "reaction_tube", f"prep.rack:{i}", 1500)
        containers[f"T{i}"]["group"] = "sfGFP" if i <= replicates else "no-template"
        add(f"P01:A{i}", "well", f"P01:A{i}", 360, parent="P01")

    steps = []

    def step(sid, title, kind, *, moves=None, transfers=None, containers=None, duration_s=0):
        steps.append({"id": sid, "title": title, "kind": kind,
                      "depends_on": [steps[-1]["id"]] if steps else [],
                      "moves": moves or [], "transfers": transfers or [],
                      "containers": containers or [], "duration_s": duration_s})

    tube_ids = [f"T{i}" for i in range(1, replicates*2+1)]
    stocks = ["MIX", "DNA", "WATER"]
    step("mix_ready", "人工确认 MIX 已预配、标签与示例库存；所有试剂保持冰上", "manual",
         containers=stocks + tube_ids + ["P01"])
    step("load_fluent", f"人工将原液与 {len(tube_ids)} 支反应管装入 Fluent 冷源示意管架", "manual",
         containers=stocks + tube_ids,
         moves=[[c, f"prep.stock:{c}", f"fluent.stock:{c}"] for c in stocks] +
               [[c, f"prep.rack:{i}", f"fluent.rack:{i}"] for i, c in enumerate(tube_ids, 1)])
    transfers = []
    for i, cid in enumerate(tube_ids, 1):
        transfers += [["MIX", cid, 45], ["DNA" if i <= replicates else "WATER", cid, 5]]
    step("fluent_dispense", "Fluent 模拟：每管 45 µL MIX + 5 µL DNA/水", "liquid", transfers=transfers)
    step("to_incubator", f"人工封管并交接 {len(tube_ids)} 管至温控工位；核对冷源与容器标签", "manual",
         containers=tube_ids,
         moves=[[c, f"fluent.rack:{i}", f"incubator.rack:{i}"] for i, c in enumerate(tube_ids, 1)])
    step("incubate", "模拟温控：30°C、充分振荡、3 h；rpm 和装置待核实", "incubate",
         containers=tube_ids, duration_s=10800)
    step("stop_on_ice", f"人工确认温控结束并将 {len(tube_ids)} 管置冰停止反应", "manual", containers=tube_ids,
         moves=[[c, f"incubator.rack:{i}", f"cold.rack:{i}"] for i, c in enumerate(tube_ids, 1)])
    manual_transfers = []
    for i, cid in enumerate(tube_ids, 1):
        manual_transfers += [[cid, f"P01:A{i}", 20], ["WATER", f"P01:A{i}", 80]]
    step("prepare_plate", f"人工转读数板：A1–A{len(tube_ids)} 各 20 µL 样品 + 80 µL 水（5 倍稀释演示）", "manual",
         containers=tube_ids + ["WATER", "P01"],
         moves=[[c, f"cold.rack:{i}", f"prep.rack:{i}"] for i, c in enumerate(tube_ids, 1)] +
               [["WATER", "fluent.stock:WATER", "prep.stock:WATER"]], transfers=manual_transfers)
    step("to_reader", "人工将 P01 从 E1 流程区域交接至 E2 iD5 示意托盘", "manual", containers=["P01"],
         moves=[["P01", "prep.plate:1", "id5.tray:1"]])
    step("read_plate", "iD5 模拟读板：Ex 488 / Em 525 nm；真实读数暂缺", "read", containers=["P01"])
    steps[3]["closures"] = {cid:"closed" for cid in tube_ids}
    steps[6]["closures"] = {cid:"open" for cid in tube_ids}
    steps[4].update(temperature_c=30, shaking="vigorous; rpm unknown")
    return {"schema": "biofoundry.workflow.v1", "id": f"cellfree-gfp-r{replicates}-v2",
            "mode": "simulation", **config, "initial_containers": containers, "steps": steps,
            "plate_map": [{"well": f"A{i}", "tube": f"T{i}", "sample_id": f"sample:T{i}",
                           "group": "sfGFP" if i <= replicates else "no-template", "replicate": (i-1) % replicates + 1}
                          for i in range(1, replicates*2+1)]}


def liquid_plan(transfers, containers, plan_id, tip_offset=0):
    """Lower the liquid substep into the existing PlanIR with a fresh tip per transfer."""
    referenced = sorted({cid for src, dst, _ in transfers for cid in [src, dst]})
    aliases = {cid: f"container{i}" for i, cid in enumerate(referenced)}
    resources = [{"id": aliases[cid], "type": "plate", "slot": str(i+1),
                  "max_volume_ul": containers[cid]["capacity_ul"]} for i, cid in enumerate(referenced)]
    resources.append({"id": "tips200ul", "type": "tiprack", "slot": "tips", "max_volume_ul": 200})
    operations = []
    for i, (src, dst, vol) in enumerate(transfers):
        for primitive, args in [
            ("PICK_TIPS", {"tip_rack": "tips200ul", "tip_positions": [f"{chr(65+(i+tip_offset)%8)}{(i+tip_offset)//8+1}"]}),
            ("ASPIRATE", {"source": f"{aliases[src]}:A1", "volume_ul": vol}),
            ("DISPENSE", {"destination": f"{aliases[dst]}:A1", "volume_ul": vol}),
            ("DROP_TIPS", {"to_waste": True}),
        ]:
            sid = f"lh{len(operations)+1:03}"
            operations.append({"step_id": sid, "primitive_type": primitive,
                               "dependencies": [operations[-1]["step_id"]] if operations else [], **args})
    return {"schema": "bpl.plan_ir.lh.v0", "plan_id": plan_id, "backend": "serializing",
            "target": "pylabrobot", "protocol_name": "Volume-only container abstraction; not Fluent coordinates",
            "resources": resources, "initial_volumes_ul": {f"{aliases[c]}:A1": containers[c]["volume_ul"] for c in referenced},
            "steps": operations}


def totals(containers):
    result = {}
    for c in containers.values():
        for component, volume in c["components_ul"].items():
            result[component] = result.get(component, 0) + volume
    return result


def validate(containers, expected):
    occupied = {}
    for cid, c in containers.items():
        require(c["id"] == cid, "IDENTITY", cid)
        require(isinstance(c["location"], str), "LOCATION_CONFLICT", f"{cid} must have one location")
        loc = c["location"]
        require(loc not in occupied, "LOCATION_CONFLICT", f"{cid} and {occupied.get(loc)} occupy {loc}")
        occupied[loc] = cid
        volume, capacity, dead = c["volume_ul"], c["capacity_ul"], c["dead_volume_ul"]
        require(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in [volume, capacity, dead]), "INVALID_VOLUME", cid)
        require(0 <= dead <= volume <= capacity, "INVALID_VOLUME", f"{cid}: {volume} / capacity {capacity}, dead {dead}")
        require(all(math.isfinite(v) and v >= 0 for v in c["components_ul"].values()), "INVALID_VOLUME", cid)
        require(abs(sum(c["components_ul"].values()) - volume) < 1e-7, "COMPONENT_BALANCE", cid)
        if c["parent"]:
            require(c["parent"] in containers and c["parent"] != cid and
                    containers[c["parent"]]["kind"] == "read_plate" and loc == cid,
                    "PARENT_LOCATION", cid)
    actual = totals(containers)
    require(actual.keys() == expected.keys() and all(abs(actual[k]-v) < 1e-7 for k, v in expected.items()),
            "VOLUME_CONSERVATION", f"{actual} != {expected}")


def move(containers, cid, origin, destination):
    c = containers[cid]
    require(c["parent"] is None, "PARENT_LOCATION", f"{cid} moves with its parent")
    require(c["location"] == origin, "WRONG_LOCATION", f"{cid}: expected {origin}, got {c['location']}")
    require(not any(other["location"] == destination for other in containers.values()),
            "LOCATION_CONFLICT", f"{destination} is occupied")
    allowed={"prep.plate:1","id5.tray:1"}
    allowed.update(f"{station}.stock:{stock}" for station in ('prep','fluent') for stock in ('MIX','DNA','WATER'))
    allowed.update(f"{station}.rack:{i}" for station in ('prep','fluent','incubator','cold') for i in range(1,9))
    require(destination in allowed, 'WRONG_LOCATION', f'Undefined port {destination}')
    c["location"] = destination


def transfer(containers, src, dst, volume, *, minimum=5):
    a, b = containers[src], containers[dst]
    require(all(c.get("closure")=="open" for c in (a,b) if c["kind"] in ("stock_tube","reaction_tube")), "CONTAINER_CLOSED", f"Open {src} and {dst} before liquid transfer")
    require(math.isfinite(volume) and minimum <= volume <= 200, "PIPETTING_RANGE", str(volume))
    require(a["volume_ul"] - volume >= a["dead_volume_ul"]-1e-9, "INSUFFICIENT_VOLUME",
            f"{src}: need {volume} µL + {a['dead_volume_ul']} µL reserve; have {a['volume_ul']}")
    require(b["volume_ul"] + volume <= b["capacity_ul"], "OVERFLOW", dst)
    for component, amount in list(a["components_ul"].items()):
        part = amount * volume / a["volume_ul"]
        a["components_ul"][component] -= part
        b["components_ul"][component] = b["components_ul"].get(component, 0) + part
    a["volume_ul"] -= volume
    b["volume_ul"] += volume
    b["sample_ids"] = sorted(set(b["sample_ids"] + a["sample_ids"]))


class Run:
    def __init__(self, plan=None, state=None):
        self.plan = copy.deepcopy(plan if plan is not None else baseline())
        self.state = copy.deepcopy(state) if state is not None else {
            "simulation_id": f"sim-{uuid.uuid4()}", "mode": "simulation", "cursor": 0,
            "experiment_elapsed_s": 0, "containers": copy.deepcopy(self.plan["initial_containers"]),
            "events": [], "result": {"status": "not_measured", "values": None,
                                      "unit": None, "source": None},
            "tips_used": 0, "status": "waiting_for_manual_confirmation"}
        self.expected = totals(self.plan["initial_containers"])
        validate(self.state["containers"], self.expected)

    def current(self):
        return self.plan["steps"][self.state["cursor"]] if self.state["cursor"] < len(self.plan["steps"]) else None

    def act(self, *, confirmation=None, expected_step=None):
        step = self.current()
        require(step is not None, "RUN_COMPLETE", "All steps already completed")
        require(expected_step == step["id"], "STALE_STEP", f"Expected current step {step['id']}")
        require(self.plan["mode"] == self.state["mode"] == "simulation", "SIMULATION_ONLY", "No hardware backend")
        if step["kind"] == "manual":
            require(confirmation is not None, "MANUAL_CONFIRMATION_REQUIRED", step["id"])
            require(isinstance(confirmation, dict) and isinstance(confirmation.get("container_ids"), list) and
                    isinstance(confirmation.get("actor"), str) and bool(confirmation["actor"].strip()),
                    "WRONG_CONFIRMATION", "Container list and named actor required")
            require(confirmation.get("step_id") == step["id"] and
                    sorted(confirmation.get("container_ids", [])) == sorted(step["containers"]) and
                    confirmation["actor"].strip(), "WRONG_CONFIRMATION", step["id"])
            require(isinstance(confirmation.get("simulated"), bool), "WRONG_CONFIRMATION", "Must declare simulated confirmation")
        else:
            require(confirmation is None, "UNEXPECTED_CONFIRMATION", step["id"])
        from .planning import validate_plan
        validate_plan(self.plan)
        candidate = copy.deepcopy(self.state)
        containers = candidate["containers"]
        validate(containers, self.expected)
        completed = [event["step_id"] for event in candidate["events"]]
        require(all(dep in completed for dep in step["depends_on"]), "DEPENDENCY", step["id"])
        reference = baseline(self.plan['demo_configuration']['replicates_per_group'])['steps'][self.state['cursor']]
        for index, (cid, origin, destination) in enumerate(step["moves"]):
            move(containers, cid, origin, destination)
            require([cid, origin, destination] == reference['moves'][index], 'CONTAINER_MAPPING', f'{step["id"]}: wrong container/port binding')
        for cid, closure in step.get("closures", {}).items():
            containers[cid]["closure"] = closure
        check = None
        if step["transfers"]:
            if step["kind"] == "liquid":
                require(all(containers[c]["location"].startswith("fluent.") for a,b,_ in step["transfers"] for c in [a,b]),
                        "WRONG_LOCATION", "Fluent liquid step requires sources and reaction tubes on its deck")
            subplan = liquid_plan(step["transfers"], containers, step["id"], candidate["tips_used"])
            check = evaluate_virtual_deck(load_plan(subplan)).to_logicpass()
            require(check["outcome"] == "pass", "PLANIR_CHECK_FAILED", json.dumps(check))
            for src, dst, volume in step["transfers"]:
                transfer(containers, src, dst, volume)
            candidate["tips_used"] += len(step["transfers"])
        if step["kind"] == "incubate":
            require(all(containers[c].get("closure")=="closed" for c in step["containers"]), "SOP_CONDITION", "Close tubes before simulated shaking/incubation; actual evaporation control unverified")
            require(all(containers[c]["location"] == f"incubator.rack:{i}" for i,c in enumerate(step["containers"],1)),
                    "WRONG_LOCATION", "All reaction tubes must be at manual temperature station")
            require(step["duration_s"] == 10800, "SOP_CONDITION", "Frozen demo duration is 3h")
        if step["kind"] == "read":
            require(containers["P01"]["location"] == "id5.tray:1", "WRONG_LOCATION", "P01 not in reader")
            require(all(abs(containers[f"P01:{w['well']}"]["volume_ul"]-100) < 1e-7 for w in self.plan["plate_map"]),
                    "READ_VOLUME", "Demo method needs 100 uL in each mapped well")
            candidate["result"] = {"status": "simulated_action_no_measurement", "values": None,
                                   "unit": None, "source": None,
                                   "settings": self.plan["demo_configuration"]["reader"],
                                   "missing": ["actual fluorescence", "gain", "bandwidth", "focal height", "calibration"]}
        validate(containers, self.expected)
        candidate["cursor"] += 1
        candidate["experiment_elapsed_s"] += step["duration_s"]
        following = self.plan["steps"][candidate["cursor"]] if candidate["cursor"] < len(self.plan["steps"]) else None
        candidate["status"] = ("waiting_for_manual_confirmation" if following["kind"] == "manual" else "ready") if following else "complete"
        event = {"seq": len(candidate["events"])+1, "step_id": step["id"], "kind": step["kind"], "title": step["title"],
                 "simulation_id": candidate["simulation_id"], "mode": "simulation",
                 "recorded_at": datetime.now(timezone.utc).isoformat(),
                 "experiment_elapsed_s": candidate["experiment_elapsed_s"],
                 "duration_s": step["duration_s"], "confirmation": confirmation,
                 "transfers": step["transfers"], "moves": step["moves"], "closures": step.get("closures",{}), "PlanIR_logicpass": check,
                 "snapshot": copy.deepcopy(containers), "component_totals_ul": totals(containers),
                 "result": copy.deepcopy(candidate["result"])}
        candidate["events"].append(event)
        self.state = candidate
        return event

    def save(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        # run.json is the authoritative atomic commit; derived exports can be rebuilt.
        write_json(directory / "plan.json", self.plan)
        write_json(directory / "plate-map.json", self.plan["plate_map"])
        (directory / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False)+"\n" for e in self.state["events"]))
        for step in self.plan["steps"]:
            if step["kind"] == "liquid":
                write_json(directory / "fluent.planir.json", liquid_plan(step["transfers"], self.plan["initial_containers"], step["id"]))
        write_json(directory / "run.json", {"plan": self.plan, "state": self.state})
        import csv
        with (directory / "plate-map.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.plan["plate_map"][0]))
            writer.writeheader(); writer.writerows(self.plan["plate_map"])
        with (directory / "tube-map.csv").open("w", newline="") as f:
            writer = csv.writer(f); writer.writerow(["container", "location", "volume_ul", "sample_ids"])
            writer.writerows((c["id"], c["location"], c["volume_ul"], ";".join(c["sample_ids"])) for c in self.state["containers"].values() if c["parent"] is None)
        (directory / "checklist.txt").write_text("SIMULATION ONLY; real measurements absent; onsite guidance not validated.\n" + "\n".join(f"{i+1}. {s['title']} | IDs: {', '.join(s['containers'])} | manual={s['kind']=='manual'}" for i,s in enumerate(self.plan['steps'])) + "\nUNKNOWN:\n" + "\n".join(self.plan['unknowns']))

    @classmethod
    def load(cls, directory):
        saved = json.loads((Path(directory) / "run.json").read_text())
        return cls(saved["plan"], saved["state"])


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")
    temporary.replace(path)


def confirmation(run, actor="acceptance:auto-confirm", simulated=True):
    step = run.current()
    return {"step_id": step["id"], "container_ids": step["containers"], "actor": actor, "simulated": simulated}


def complete(run):
    while run.current():
        run.act(expected_step=run.current()["id"],
                confirmation=confirmation(run) if run.current()["kind"] == "manual" else None)
    return run
