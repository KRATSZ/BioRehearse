"""Independent checks for the known-outage scheduling experiment.

The production replanner and the ordinary schedule scorer validate a plan
against the registered calendar.  They do not, by themselves, prove that a
case-specific outage is absent from the returned rows or that work already
started at the outage announcement was preserved.  This module performs those
two checks from the baseline and repaired row tables and records the evidence
used by the v3 audit.
"""
from __future__ import annotations

import hashlib
import json


def _overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def frozen_rows(plan: dict, now_s: int) -> list[dict]:
    """Return the identity/timing fields that must remain frozen at ``now_s``."""
    return [
        {
            "id": row["id"],
            "resource": row["resource"],
            "start_s": row["start_s"],
            "end_s": row["end_s"],
        }
        for row in sorted(plan.get("rows", []), key=lambda item: item["id"])
        if row["start_s"] <= now_s
    ]


def rows_digest(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def audit_replan(
    baseline: dict,
    result: dict,
    *,
    now_s: int,
    repair_s: int,
    failed_resource: str,
    scorer_valid: bool,
) -> dict:
    """Audit outage and preservation conditions independently of replan claims."""
    baseline_frozen = frozen_rows(baseline, now_s)
    baseline_active = [
        row["id"]
        for row in baseline.get("rows", [])
        if row["resource"] == failed_resource and row["start_s"] <= now_s < row["end_s"]
    ]
    violations: list[str] = []
    if baseline_active:
        violations.extend(f"baseline_active_fault_step:{row_id}" for row_id in baseline_active)

    returned = bool(result.get("ok"))
    outage_nonoverlap = None
    started_rows_preserved = None
    if returned:
        outage_hits = [
            row["id"]
            for row in result.get("rows", [])
            if row["resource"] == failed_resource
            and _overlap(row["start_s"], row["end_s"], now_s, repair_s)
        ]
        outage_nonoverlap = not outage_hits
        if outage_hits:
            violations.extend(f"outage_overlap:{row_id}" for row_id in outage_hits)

        repaired = {row["id"]: row for row in result.get("rows", [])}
        changed: list[str] = []
        for expected in baseline_frozen:
            actual = repaired.get(expected["id"])
            if actual is None:
                changed.append(f"missing_started_row:{expected['id']}")
                continue
            for field in ("resource", "start_s", "end_s"):
                if actual.get(field) != expected[field]:
                    changed.append(f"started_row_changed:{expected['id']}:{field}")
        started_rows_preserved = not changed
        violations.extend(changed)

    audit_passed = returned and not violations and bool(scorer_valid)
    return {
        "valid": audit_passed,
        "violations": violations,
        "independent_checks": {
            "baseline_active_fault_rows": baseline_active,
            "baseline_started_row_count": len(baseline_frozen),
            "baseline_started_rows_digest": rows_digest(baseline_frozen),
            "replan_returned": returned,
            "replan_scorer_valid": bool(scorer_valid),
            "outage_nonoverlap": outage_nonoverlap,
            "started_rows_preserved": started_rows_preserved,
        },
        "baseline_frozen_rows": baseline_frozen,
    }
