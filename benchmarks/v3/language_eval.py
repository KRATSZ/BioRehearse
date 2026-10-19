"""Prospective GLM-4.7-Flash language extension.

The v2 request file, primary semantic scorer and authoring prompt are read
without modification.  This runner has one provider route and one model
whitelist: GLM-4.7-Flash at the official BigModel OpenAI-compatible endpoint.
It never falls back to a paid model or a coding-plan credential.

Stages are deliberately separate.  ``--stage development`` runs four
pre-specified probes; ``--stage full`` runs all 96 v2 requests once, but only
after the route and prompt freeze has been written.  Results and provider
errors are retained even when the free endpoint is temporarily overloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
PAPER = HERE.parents[2]
PROJECT = Path(os.environ.get("BIOFOUNDRY_PROJECT", "/Users/gaoyuan/Documents/test/Flexagent/Opentrons-Lab-Agent"))
WEBDEMO = PROJECT / "labscriptai" / "webdemo"
RUNNER = PAPER / "benchmarks" / "v3" / "language_runner.ts"
V2 = PAPER / "benchmarks" / "v2"
REQUESTS = V2 / "language.json"
CATALOG = PAPER / "source-data" / "v2" / "catalog.json"
METHODS = PAPER / "source-data" / "v3" / "language" / "methods.json"
# Reuse the frozen v2 decision function for the primary success field.  The
# GLM route may still retain its route-level `accepted` field for diagnostics.
sys.path.insert(0, str(V2))
from language import correct as strict_correct

OUT = PAPER / "source-data" / "v3" / "language"
MODEL = os.environ.get("BIOFOUNDRY_GLM_MODEL", "glm-4.7-flash")
TRACE_DIR = OUT / MODEL
AUDIT = PAPER / "audit" / "v3"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
FORCE_TOOL_CHOICE = os.environ.get("BIOFOUNDRY_FORCE_TOOL_CHOICE", "")
FREEZE_OVERRIDE = os.environ.get("BIOFOUNDRY_LANGUAGE_FREEZE")
if FREEZE_OVERRIDE:
    FREEZE = Path(FREEZE_OVERRIDE)
    if not FREEZE.is_absolute():
        FREEZE = OUT / FREEZE
elif MODEL == "glm-4.7-flash" and not FORCE_TOOL_CHOICE:
    FREEZE = OUT / "freeze.json"
elif FORCE_TOOL_CHOICE:
    FREEZE = OUT / f"freeze-{MODEL}-forced.json"
else:
    FREEZE = OUT / f"freeze-{MODEL}.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def model_route() -> dict:
    route = {
        "provider": "zai",
        "model": MODEL,
        "api": "openai-completions",
        "base_url": BASE_URL,
        "free_model_whitelist": [MODEL],
        "fallback": None,
        "max_output_tokens": 8192,
        "nominal_price_cny_per_million": {"input": 0, "output": 0, "cache_read": 0},
        "invoice_status": "not queried; provider pricing page records this model as free",
    }
    if MODEL != "glm-4.7-flash" or FORCE_TOOL_CHOICE:
        route["tool_choice"] = FORCE_TOOL_CHOICE or "auto"
    return route


def freeze() -> dict:
    """Write a prospective input/route freeze; refuse accidental replacement."""
    data = {
        "schema": "biorehearse.v3.language-freeze/1",
        "created": "2026-10-19",
        "stage_policy": {
            "development": "four first requests in the existing v2 file; adapter probes only",
            "full": "all development and held-out requests in the existing v2 file, one GLM run each",
            "repeats": 1,
            "post_hoc_extension": True,
        },
        "request_file": str(REQUESTS.relative_to(PAPER)),
        "request_file_sha256": digest(REQUESTS),
        "methods_file": str(METHODS.relative_to(PAPER)),
        "methods_file_sha256": digest(METHODS),
        "catalog_file": str(CATALOG.relative_to(PAPER)),
        "catalog_file_sha256": digest(CATALOG),
        "author_source": str((PROJECT / "labscriptai/webdemo/server/src/biofoundry-author.ts").resolve()),
        "author_source_sha256": digest(PROJECT / "labscriptai/webdemo/server/src/biofoundry-author.ts"),
        "runner_sha256": digest(RUNNER),
        "primary_scorer": str((V2 / "language.py").relative_to(PAPER)),
        "primary_scorer_sha256": digest(V2 / "language.py"),
        "model_route": model_route(),
        "budget_guard": {
            "allowed_credentials": ["GLM_API_KEY"],
            "forbidden_credentials": ["ANTHROPIC_AUTH_TOKEN"],
            "forbidden_models": ["glm-4.7", "glm-5", "deepseek-flash", "deepseek-v4-pro"],
            "fallback": None,
        },
        "official_sources": {
            "pricing": "https://docs.bigmodel.cn/cn/guide/start/pricing",
            "model_overview": "https://docs.bigmodel.cn/cn/guide/start/model-overview",
            "chat_completions": "https://open.bigmodel.cn/api/paas/v4",
        },
    }
    if FREEZE.exists():
        existing = json.loads(FREEZE.read_text())
        if existing != data:
            raise RuntimeError("Existing GLM language freeze differs; preserve it and inspect the input change")
        return existing
    write_json(FREEZE, data)
    return data


def cases(stage: str) -> list[dict]:
    spec = json.loads(REQUESTS.read_text())
    all_cases = list(spec["development"]) + list(spec["heldout"])
    if stage == "development":
        return all_cases[:4]
    if stage == "full":
        return all_cases
    raise ValueError(stage)


def sources() -> dict:
    return {"methods": json.loads(METHODS.read_text()), "catalog": json.loads(CATALOG.read_text())}


def run_one(case: dict, retry_429: int = 1) -> tuple[dict, str | None, float]:
    payload = {"request": case["request"], "sources": sources()}
    started = time.perf_counter()
    error = None
    stdout = ""
    stderr = ""
    for attempt in range(retry_429 + 1):
        try:
            # The executable is resolved from the production webdemo; it is
            # called with the paper directory as cwd so GLM_API_KEY remains
            # available in the task environment.  No key is placed in args or
            # logs, and the runner has no other provider route.
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import json,sys; print(json.dumps(json.load(sys.stdin)))",
                ],
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                check=True,
            )
            normalized = result.stdout
            # Use the Node/tsx executable explicitly.  The tiny Python step
            # above ensures the request is encoded once before crossing into
            # the TypeScript harness and avoids shell interpolation.
            node = WEBDEMO / "node_modules" / ".bin" / "tsx"
            result = subprocess.run(
                [str(node), str(RUNNER)],
                input=normalized,
                text=True,
                capture_output=True,
                timeout=180,
                cwd=PAPER,
                env=os.environ.copy(),
                check=False,
            )
            stdout, stderr = result.stdout, result.stderr
            if result.returncode == 0:
                break
            error = (stderr or f"runner exit {result.returncode}").strip()[-2000:]
        except Exception as exc:  # retain provider/transport failures as data
            error = repr(exc)
        if attempt < retry_429 and "429" in (error or stdout):
            time.sleep(12)
        else:
            break
    wall = time.perf_counter() - started
    if stdout.strip():
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            data = {}
            error = (error or "") + " non-JSON runner output"
    else:
        data = {}
    # A provider error can still be represented in a valid runner response;
    # keep both the structured response and process-level stderr.
    if data.get("trace"):
        errors = [
            e.get("message", {}).get("errorMessage")
            for e in data["trace"]
            if e.get("type") == "message_end" and e.get("message", {}).get("errorMessage")
        ]
        if errors:
            error = "; ".join(str(e) for e in errors)
    return data, error, wall


def usage(data: dict) -> dict:
    rows = []
    for event in data.get("trace", []):
        message = event.get("message", {})
        if event.get("type") == "message_end" and message.get("role") == "assistant":
            u = message.get("usage") or {}
            if u:
                rows.append(u)
    fields = {
        "input_tokens": "input",
        "output_tokens": "output",
        "cache_read_tokens": "cacheRead",
        "cache_write_tokens": "cacheWrite",
        "reasoning_tokens": "reasoning",
        "total_tokens": "totalTokens",
    }
    return {key: sum(int(u.get(source, 0) or 0) for u in rows) for key, source in fields.items()}


def record(case: dict, data: dict, error: str | None, wall: float, raw_path: Path) -> dict:
    response_models = sorted(
        {
            e.get("message", {}).get("model")
            for e in data.get("trace", [])
            if e.get("type") == "message_end" and e.get("message", {}).get("model")
        }
    )
    rec = {
        "case": case["id"],
        "split": "development" if case["id"].startswith("development-") else "heldout",
        "cluster": case["cluster"],
        "style": case["style"],
        "decision": case["decision"],
        "model": MODEL,
        "provider": "zai",
        "repeat": 1,
        "accepted": bool(data.get("ok")),
        "success": bool(strict_correct(case, data, error)),
        "code": data.get("code"),
        "wall_s": wall,
        "error": error,
        "raw_file": str(raw_path.relative_to(PAPER)),
        "model_responses": len(
            [e for e in data.get("trace", []) if e.get("type") == "message_end" and e.get("message", {}).get("role") == "assistant"]
        ),
        "tool_proposals": sum(1 for e in data.get("trace", []) if e.get("type") == "tool_execution_start"),
        "response_models": response_models,
        "nominal_cost_cny": 0.0,
        "invoice_cost_cny": None,
        "request_sha256": hashlib.sha256(case["request"].encode()).hexdigest(),
        "prompt_sha256": data.get("prompt_sha256"),
    }
    rec.update(usage(data))
    return rec


def run(stage: str) -> dict:
    freeze()
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    score_path = TRACE_DIR / f"{stage}-scores.jsonl"
    raw_root = TRACE_DIR / f"{stage}-raw"
    if score_path.exists():
        raise RuntimeError(f"Refusing to overwrite frozen stage output: {score_path}")
    records = []
    for index, case in enumerate(cases(stage), start=1):
        data, error, wall = run_one(case)
        raw_path = raw_root / f"{index:03d}-{case['id']}.json"
        write_json(raw_path, {"case": case, "result": data, "error": error, "wall_s": wall})
        rec = record(case, data, error, wall, raw_path)
        append_jsonl(score_path, rec)
        records.append(rec)
        print(json.dumps({"stage": stage, "index": index, "case": case["id"], "ok": rec["accepted"], "success": rec["success"], "code": rec["code"], "error": error}, ensure_ascii=False), flush=True)
    summary = {
        "schema": "biorehearse.v3.glm-language-summary/1",
        "stage": stage,
        "model_route": model_route(),
        "n": len(records),
        "accepted": sum(int(r["accepted"]) for r in records),
        "success": sum(int(r["success"]) for r in records),
        "provider_errors": sum(int(bool(r["error"])) for r in records),
        "tool_proposals": sum(r["tool_proposals"] for r in records),
        "nominal_cost_cny": sum(r["nominal_cost_cny"] for r in records),
        "invoice_cost_cny": None,
        "records": str(score_path.relative_to(PAPER)),
        "interpretation": "Post-hoc cross-provider extension on the existing v2 author-constructed request suite; not an independent external request set.",
    }
    write_json(TRACE_DIR / f"{stage}-summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--stage", choices=["development", "full"])
    args = parser.parse_args()
    if args.freeze:
        print(json.dumps(freeze(), ensure_ascii=False, indent=2))
        return
    if not args.stage:
        parser.error("--stage is required unless --freeze is used")
    summary = run(args.stage)
    AUDIT.mkdir(parents=True, exist_ok=True)
    write_json(AUDIT / f"LANGUAGE_GLM_{args.stage.upper()}.json", summary)


if __name__ == "__main__":
    main()
