"""Non-primary retry ledger for transient free-model availability."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from language_eval import MODEL, TRACE_DIR, cases, record, run_one, write_json


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True, choices=["r1", "r2", "r3-v3b"])
    ap.add_argument("--wait-s", type=int, default=0)
    args = ap.parse_args()
    target = TRACE_DIR / f"retry-{args.round}"
    if target.exists():
        raise RuntimeError(f"Refusing to overwrite retry directory: {target}")
    target.mkdir(parents=True)
    if args.wait_s:
        time.sleep(args.wait_s)
    selected = cases("development")
    rows = []
    stop_reason = None
    for index, case in enumerate(selected, start=1):
        data, error, wall = run_one(case, retry_429=0)
        raw = target / f"{index:03d}-{case['id']}.json"
        write_json(raw, {"case": case, "result": data, "error": error, "wall_s": wall})
        row = record(case, data, error, wall, raw)
        rows.append(row)
        print(json.dumps({"round": args.round, "index": index, "case": case["id"], "ok": row["accepted"], "code": row["code"], "error": error}, ensure_ascii=False), flush=True)
        if index == 1 and error:
            stop_reason = "first_probe_provider_error; remaining three probes were withheld"
            break
    if stop_reason is None:
        stop_reason = "all four development probes completed"
    write_json(
        target / "summary.json",
        {
            "schema": "biorehearse.v3.glm-language-retry/1",
            "round": args.round,
            "wait_s": args.wait_s,
            "n": len(rows),
            "accepted": sum(int(r["accepted"]) for r in rows),
            "provider_errors": sum(int(bool(r["error"])) for r in rows),
            "stop_reason": stop_reason,
            "model": MODEL,
            "route": "https://open.bigmodel.cn/api/paas/v4",
            "fallback": None,
            "records": [str((target / f"{i:03d}-{case['id']}.json").relative_to(target.parent.parent.parent.parent)) for i, case in enumerate(selected[: len(rows)], start=1)],
        },
    )


if __name__ == "__main__":
    main()
