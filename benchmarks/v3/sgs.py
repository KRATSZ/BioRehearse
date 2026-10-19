"""Independent Kolisch-style serial and parallel SGS baselines.

The implementation consumes the compiled task graph and catalog but does not
call the production CP-SAT model.  All hard constraints are represented in the
candidate placement routine; the v2 independent arithmetic scorer is used only
after a plan has been produced.
"""
from __future__ import annotations

import copy
import math
import time
from collections import defaultdict


def _transport(catalog, layout, source, destination):
    points = catalog["layouts"][layout]["positions"]
    cfg = catalog["transport"]
    distance = sum(abs(a - b) for a, b in zip(points[source], points[destination]))
    seconds = math.ceil(distance / cfg["speed_m_s"])
    seconds += cfg["handoff_s"] if source != destination else cfg["same_station_s"]
    return seconds, distance


def _options(task, catalog):
    """Copy the registered option equations without importing production code."""
    out = []
    for key in task["candidates"]:
        device = catalog["devices"][key]
        caps = device.get("capabilities", {})
        if not (
            device.get("selectable")
            and caps.get(task["capability"]) is True
            and all(c in device.get("containers", []) for c in task.get("required_labware", [task["container"]]))
            and type(device.get("capacity")) is int
            and device["capacity"] >= task["demand"]
            and device.get("available_s")
            and device.get("cost_cny_per_hour") is not None
        ):
            continue
        temperature = task.get("temperature_c")
        if temperature is not None and temperature not in caps.get("temperature_c", []):
            continue
        if any(
            not isinstance(caps.get(field), list)
            or not caps[field][0] <= value <= caps[field][1]
            for field, value in task.get("optics", {}).items()
        ):
            continue
        if task["name"] == "dark_incubation" and not device.get("conditions", {}).get("dark_cover"):
            continue
        factor = device.get("duration_factor", 1) if task["capability"] == "liquid" else 1
        process = math.ceil(task["process_s"] * factor)
        duration = task["load_s"] + process + task["clean_s"]
        operator = duration if task["manual"] or (key == "bench" and task["capability"] == "liquid") else task["load_s"] + task["clean_s"]
        machine_cents = math.ceil(duration * device["cost_cny_per_hour"] / 36)
        labor_cents = math.ceil(operator * catalog["costs"]["operator_per_hour"] / 36)
        out.append(
            {
                "resource": key,
                "duration_s": duration,
                "process_s": process,
                "operator_s": operator,
                "cost_cents": machine_cents + labor_cents,
                "machine_cents": machine_cents,
                "labor_cents": labor_cents,
            }
        )
    return out


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def _available(device, start, end):
    return any(a <= start and end <= b for a, b in device.get("available_s", []))


def _find_start(earliest, latest, duration, spans, busy, catalog):
    """Find the first start satisfying all resource and availability intervals."""
    if earliest > latest:
        return None
    start = max(0, int(math.ceil(earliest)))
    for _ in range(10000):
        if start > latest:
            return None
        proposed = [(resource, start + offset, start + offset + length) for resource, offset, length in spans if length]
        move = start
        for resource, interval_start, interval_end in proposed:
            interval = (interval_start, interval_end)
            for occupied in busy.get(resource, []):
                if _overlap(interval, occupied):
                    # Shift the whole placement until the conflicting span
                    # begins after the occupied interval.  Subtracting the
                    # span duration here would leave the original start and
                    # create an operator overlap at the next iteration.
                    move = max(move, occupied[1] - (interval_start - start))
        device_resource = next((r for r, _, _ in spans if r != "operator"), None)
        if device_resource and not _available(catalog["devices"][device_resource], start, start + duration):
            windows = catalog["devices"][device_resource].get("available_s", [])
            move = max(move, min((a for a, b in windows if b >= start + duration), default=latest + 1))
        if move == start:
            return start
        start = move
    return None


def _remaining_path(tasks):
    by_id = {t["id"]: t for t in tasks}
    downstream = defaultdict(list)
    for task in tasks:
        for dep in task["depends_on"]:
            downstream[dep].append(task["id"])
    memo = {}

    def visit(tid):
        if tid in memo:
            return memo[tid]
        t = by_id[tid]
        value = t["process_s"] + t["load_s"] + t["clean_s"]
        if downstream[tid]:
            value += max(visit(child) for child in downstream[tid])
        memo[tid] = value
        return value

    for tid in by_id:
        visit(tid)
    return memo


def _priority(task, start, rule, task_index, remaining):
    """Return a task-level priority shared by all device placements.

    The duration used for minimum-slack ordering is the registered nominal
    task duration.  Device-dependent duration factors are considered only
    after the task has been selected, so a slower device cannot win by
    manufacturing a smaller option-specific slack value.
    """
    nominal_duration = task["load_s"] + task["process_s"] + task["clean_s"]
    slack = task["deadline_s"] - start - nominal_duration
    if rule == "minimum_slack":
        return (slack, task_index[task["id"]], task["id"])
    if rule == "longest_remaining_path":
        return (-remaining[task["id"]], task_index[task["id"]], task["id"])
    if rule == "earliest_release":
        return (task["release_s"], start, task_index[task["id"]], task["id"])
    return (task_index[task["id"]], task["id"])


def _candidate(task, graph, catalog, layout, busy, rows, objective, rule, task_index, remaining, max_start=None, *, lookahead=True, stop_time=None):
    candidates = []
    tasks_by_id = {t["id"]: t for t in graph["tasks"]}
    for option in _options(task, catalog):
        if stop_time is not None and time.perf_counter() >= stop_time:
            return None
        temporary = {resource: list(intervals) for resource, intervals in busy.items()}
        earliest = task["release_s"]
        transfer_rows = []
        # The transfer order is deterministic and starts with the earliest
        # predecessor completion; all transfers consume the shared operator.
        deps = sorted(task["depends_on"], key=lambda dep: (rows[dep]["end_s"], dep))
        for dep in deps:
            source = rows[dep]["resource"]
            seconds, distance = _transport(catalog, layout, source, option["resource"])
            transfer_start = max(earliest, rows[dep]["end_s"])
            transfer_start = _find_start(
                transfer_start,
                graph["deadline_s"] - seconds,
                seconds,
                [("operator", 0, seconds)],
                temporary,
                catalog,
            )
            if transfer_start is None:
                break
            transfer_end = transfer_start + seconds
            temporary.setdefault("operator", []).append((transfer_start, transfer_end))
            transfer_rows.append(
                {
                    "id": dep + "→" + task["id"],
                    "name": "manual_transfer",
                    "kind": "transfer",
                    "experiment": task["experiment"],
                    "resource": "operator",
                    "source": source,
                    "destination": option["resource"],
                    "depends_on": [dep],
                    "to_task": task["id"],
                    "start_s": transfer_start,
                    "end_s": transfer_end,
                    "duration_s": seconds,
                    "distance_m": distance,
                    "cost_cents": math.ceil(seconds * catalog["costs"]["operator_per_hour"] / 36),
                    "plate_id": task["plate_id"],
                    "transfers": [],
                    "manual": True,
                }
            )
            earliest = transfer_end
        else:
            latest = task["deadline_s"] - option["duration_s"]
            window = task.get("window")
            if window:
                source = tasks_by_id[window["from"]]
                reference = rows[source["id"]]["end_s"] - source["clean_s"]
                earliest = max(earliest, reference + window.get("min_s", 0) - task["load_s"])
                latest = min(latest, reference + window.get("max_s", 0) - task["load_s"])
            if max_start is not None:
                latest = min(latest, max_start)
            spans = [(option["resource"], 0, option["duration_s"])]
            if option["operator_s"] == option["duration_s"]:
                spans.append(("operator", 0, option["duration_s"]))
            else:
                if task["load_s"]:
                    spans.append(("operator", 0, task["load_s"]))
                if task["clean_s"]:
                    spans.append(("operator", option["duration_s"] - task["clean_s"], task["clean_s"]))
            start = _find_start(earliest, latest, option["duration_s"], spans, temporary, catalog)
            # Maximum waiting windows are non-regular time-lag constraints.
            # A plain serial SGS can dispatch a predecessor too early and then
            # discover that its successor has no slot.  Forward-check immediate
            # windowed children and move this operation to the next feasible
            # insertion point; this is still a deterministic serial SGS, but
            # avoids reporting avoidable dead ends as baseline failures.
            if start is not None and lookahead:
                for _ in range(500):
                    if stop_time is not None and time.perf_counter() >= stop_time:
                        return None
                    if start is None:
                        break
                    fake = {
                        **copy.deepcopy(task),
                        **option,
                        "kind": "operation",
                        "start_s": start,
                        "end_s": start + option["duration_s"],
                        "process_start_s": start + task["load_s"],
                        "process_end_s": start + option["duration_s"] - task["clean_s"],
                    }
                    future_rows = dict(rows)
                    future_rows[task["id"]] = fake
                    future_busy = {resource: list(intervals) for resource, intervals in temporary.items()}
                    for resource, offset, length in spans:
                        if length:
                            future_busy.setdefault(resource, []).append((start + offset, start + offset + length))
                    feasible = True
                    for child in graph["tasks"]:
                        window = child.get("window")
                        if not window or window.get("from") != task["id"]:
                            continue
                        if not all(dep in future_rows for dep in child["depends_on"]):
                            continue
                        child_candidate = _candidate(
                            child,
                            graph,
                            catalog,
                            layout,
                            future_busy,
                            future_rows,
                            objective,
                            rule,
                            task_index,
                            remaining,
                            lookahead=False,
                            stop_time=stop_time,
                        )
                        if child_candidate is None:
                            feasible = False
                            break
                    if feasible:
                        break
                    # Windows in this benchmark are engineering bounds of
                    # 120–600 s, so a 60-s insertion grid keeps forward
                    # checking bounded while preserving the same integer-time
                    # resource constraints used by the scorer.
                    start = _find_start(start + 60, latest, option["duration_s"], spans, temporary, catalog)
                else:
                    start = None
            if start is not None:
                end = start + option["duration_s"]
                rows_out = transfer_rows + [
                    {
                        **copy.deepcopy(task),
                        **option,
                        "kind": "operation",
                        "start_s": start,
                        "end_s": end,
                        "process_start_s": start + task["load_s"],
                        "process_end_s": end - task["clean_s"],
                    }
                ]
                reservations = [(r["resource"], r["start_s"], r["end_s"]) for r in transfer_rows]
                reservations += [(resource, start + offset, start + offset + length) for resource, offset, length in spans if length]
                total_cents = option["cost_cents"] + sum(r["cost_cents"] for r in transfer_rows)
                candidates.append(
                    {
                        "task": task,
                        "option": option,
                        "start": start,
                        "end": end,
                        "rows": rows_out,
                        "reservations": reservations,
                        "cost_cents": total_cents,
                        "priority": _priority(task, start, rule, task_index, remaining),
                    }
                )
    if not candidates:
        return None
    if objective == "cheapest":
        return min(candidates, key=lambda c: (c["priority"], c["cost_cents"], c["end"], c["option"]["resource"]))
    return min(candidates, key=lambda c: (c["priority"], c["end"], c["cost_cents"], c["option"]["resource"]))


def _commit(candidate, busy, rows, reservations):
    for resource, start, end in candidate["reservations"]:
        busy.setdefault(resource, []).append((start, end))
        reservations.append({"task_id": next(r["id"] for r in candidate["rows"] if r.get("resource") == resource and r["start_s"] == start and r["end_s"] == end) if False else None})
    for row in candidate["rows"]:
        rows[row["id"]] = row
    # Rebuild reservations from row identities.  This avoids accidentally
    # attaching a device interval to a transfer when times coincide.
    reservations.clear()
    for row in rows.values():
        reservations.append({"task_id": row["id"], "resource": row["resource"], "start_s": row["start_s"], "end_s": row["end_s"]})
        if row["kind"] == "operation":
            task = row
            if row["operator_s"] == row["duration_s"]:
                reservations.append({"task_id": row["id"], "resource": "operator", "start_s": row["start_s"], "end_s": row["end_s"]})
            else:
                if task["load_s"]:
                    reservations.append({"task_id": row["id"], "resource": "operator", "start_s": row["start_s"], "end_s": row["start_s"] + task["load_s"]})
                if task["clean_s"]:
                    reservations.append({"task_id": row["id"], "resource": "operator", "start_s": row["end_s"] - task["clean_s"], "end_s": row["end_s"]})


def solve_sgs(graph, catalog, layout="compact", objective="fastest", bookings=(), *, mode="serial", priority_rule="input_order", time_limit_s=2):
    """Return a scorer-compatible plan from a fixed serial/parallel SGS rule."""
    started = time.perf_counter()
    if mode not in ("serial", "parallel"):
        raise ValueError(mode)
    tasks = list(graph["tasks"])
    task_index = {task["id"]: i for i, task in enumerate(tasks)}
    remaining = _remaining_path(tasks)
    busy = defaultdict(list)
    for block in bookings:
        busy[block["resource"]].append((block["start_s"], block["end_s"]))
    rows = {}
    reservations = []
    pending = {task["id"]: task for task in tasks}
    total_cents = round(graph["consumables_cny"] * 100)
    event = 0
    while pending:
        if time.perf_counter() - started > time_limit_s:
            return {"ok": False, "status": "SGS_BUDGET_EXHAUSTED", "code": "SOLVER_UNRESOLVED", "solve_seconds": time.perf_counter() - started}
        ready = [task for task in pending.values() if all(dep in rows for dep in task["depends_on"])]
        if not ready:
            return {"ok": False, "status": "NO_SGS_PLAN", "code": "PRECEDENCE_CYCLE"}
        candidates = [
            candidate
            for task in ready
            if (candidate := _candidate(task, graph, catalog, layout, busy, rows, objective, priority_rule, task_index, remaining, stop_time=started + time_limit_s)) is not None
        ]
        if not candidates:
            return {"ok": False, "status": "NO_SGS_PLAN", "code": "NO_FEASIBLE_READY_TASK"}
        if mode == "parallel":
            # Parallel SGS advances to the next event and commits all eligible
            # tasks that can begin at that event.  Re-evaluation after each
            # commit preserves exact device/operator exclusivity.
            target = min(c["start"] for c in candidates)
            eligible = [c for c in candidates if c["start"] == target]
            if not eligible:
                eligible = [min(candidates, key=lambda c: (c["start"], c["priority"], c["end"]))]
            chosen = min(eligible, key=lambda c: (c["priority"], c["end"], c["cost_cents"]))
        else:
            chosen = min(candidates, key=lambda c: (c["priority"], c["end"], c["cost_cents"]))
        _commit(chosen, busy, rows, reservations)
        total_cents += chosen["cost_cents"]
        if total_cents > math.floor(graph["budget_cny"] * 100):
            return {"ok": False, "status": "NO_SGS_PLAN", "code": "BUDGET"}
        pending.pop(chosen["task"]["id"])
        event = max(event, chosen["end"])

    ordered = sorted(rows.values(), key=lambda row: (row["start_s"], row["id"]))
    makespan = max(row["end_s"] for row in ordered)
    used = {r["resource"] for r in ordered}
    utilization = {resource: round(sum(b - a for row in ordered for a, b in [(row["start_s"], row["end_s"])] if row["resource"] == resource) / makespan, 4) for resource in used}
    return {
        "schema": "biofoundry.schedule.v2",
        "mode": "simulation",
        "ok": True,
        "status": f"{'SERIAL' if mode == 'serial' else 'PARALLEL'}_SGS",
        "proven_optimal": False,
        "objective": objective,
        "objective_value": makespan if objective == "fastest" else total_cents,
        "best_bound": None,
        "solver": "independent Kolisch SGS",
        "solve_seconds": round(time.perf_counter() - started, 6),
        "planning_budget_s": time_limit_s,
        "layout": layout,
        "rows": ordered,
        "reservations": reservations,
        "makespan_s": makespan,
        "cost_cny": total_cents / 100,
        "cost_breakdown_cny": {"consumables": graph["consumables_cny"], "machine_and_operator": total_cents / 100 - graph["consumables_cny"], "model_api": None},
        "transport_distance_m": round(sum(row.get("distance_m", 0) for row in ordered), 2),
        "transport_seconds": sum(row.get("duration_s", 0) for row in ordered if row["kind"] == "transfer"),
        "utilization": utilization,
        "bottleneck": max(utilization, key=utilization.get),
        "graph": graph,
        "priority_rule": priority_rule,
        "sgs_mode": mode,
    }
