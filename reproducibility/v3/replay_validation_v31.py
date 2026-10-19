#!/usr/bin/env python3
"""Replay the frozen v3.1 validators from the portable metadata bundle.

This runner executes the unchanged ``benchmarks/v3/mutation.py`` and
``benchmarks/v3/validation.py`` source files.  It does not re-count the saved
booleans in ``raw/mutations/mutants.jsonl``.  A temporary virtual-lab root is
assembled around the portable contracts, assembly references and simulator
snapshot; only the modules' source-tree path globals are rebound.  Replay
products are written to the required, caller-provided output directory.

The public bundle intentionally omits normalized GLBs.  ``Binding`` hashes the
configured GLB path during construction but does not parse geometry in the
contract/mutation execution path.  Deterministic placeholder files are staged
only in the temporary root so the unchanged constructor can complete.  This
adapter and its limits are recorded in ``replay-report.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "biofoundry.v3.1.frozen-replay/1"
PAPER_REL = Path("docs/paper/biofoundry-preprint")
MUTATION_REL = Path("benchmarks/v3/mutation.py")
VALIDATION_REL = Path("benchmarks/v3/validation.py")
FREEZE_REL = Path("raw/mutation-freeze.json")
MUTANTS_REL = Path("raw/mutations/mutants.jsonl")
CONTRACT_LIFECYCLE_REL = Path("raw/validation/contract-lifecycle.json")
WORKFLOW_PROBE_REL = Path("raw/validation/workflow-action-probe.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def load_module(name: str, path: Path):
    """Import source bytes directly; the frozen source files are never edited."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def locate_bundle(explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    script_dir = Path(__file__).resolve().parent
    candidates.extend([script_dir / "portable-v3.1", script_dir, Path.cwd() / "portable-v3.1", Path.cwd()])
    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / "asset-library.json").is_file() and (candidate / FREEZE_REL).is_file():
            return candidate
    raise FileNotFoundError("Could not locate portable-v3.1; pass --bundle /path/to/portable-v3.1")


def locate_source_paper(bundle: Path, explicit: Path | None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    if os.environ.get("BIOFOUNDRY_PAPER"):
        candidates.append(Path(os.environ["BIOFOUNDRY_PAPER"]).expanduser())
    # <virtual-lab>/docs/paper/biofoundry-preprint/reproducibility/v3/portable-v3.1
    candidates.append(bundle.parents[2])
    candidates.extend(parent / PAPER_REL for parent in [Path.cwd(), bundle, *bundle.parents])
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        required = [
            candidate / MUTATION_REL,
            candidate / VALIDATION_REL,
            candidate / "benchmarks/v2/scorer.py",
            candidate / "benchmarks/v2/repair.py",
            candidate / "source-data/v2/catalog.json",
            candidate / "source-data/v2/language-diagnostics.json",
            candidate / "source-data/v2/repair/plans",
        ]
        if all(path.exists() for path in required):
            return candidate
    raise FileNotFoundError(
        "A full frozen source tree is required for checker replay; pass --source-paper "
        "/path/to/docs/paper/biofoundry-preprint"
    )


def contained_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if not relative or rel.is_absolute() or '..' in rel.parts or '\\' in relative:
        raise ValueError('Unsafe asset path: ' + relative)
    target = root / rel
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('Asset path escapes temporary export: ' + relative)
    return target


def validate_bundle(bundle: Path) -> dict[str, Any]:
    catalog = read_json(bundle / "asset-library.json")
    assets = catalog.get("assets", [])
    contracts = sorted((bundle / "library").glob("*/asset.contract.json"))
    references = sorted((bundle / "library").glob("*/assembly-reference.json"))
    if len(assets) != 71 or len(contracts) != 71 or len(references) != 71:
        raise RuntimeError(f"Expected 71 assets/contracts/references, got {len(assets)}/{len(contracts)}/{len(references)}")
    seen_ids, seen_models = set(), set()
    for asset in assets:
        asset_id = asset["asset_id"]
        if not isinstance(asset_id, str) or asset_id in {'.','..'} or '/' in asset_id or '\\' in asset_id or not asset_id or asset_id in seen_ids:
            raise ValueError('Invalid or duplicate asset id')
        seen_ids.add(asset_id)
        model = contained_path(bundle, asset['normalized_glb'])
        if model.suffix.lower() != '.glb' or str(model) in seen_models:
            raise ValueError('Invalid or duplicate GLB reference')
        seen_models.add(str(model))
        if not (bundle / "library" / asset_id / "asset.contract.json").is_file():
            raise RuntimeError(f"Missing contract for {asset_id}")
        if not (bundle / "library" / asset_id / "assembly-reference.json").is_file():
            raise RuntimeError(f"Missing assembly reference for {asset_id}")
    for required in ("sim/library_protocols.py", FREEZE_REL, MUTANTS_REL, CONTRACT_LIFECYCLE_REL, WORKFLOW_PROBE_REL):
        if not (bundle / required).is_file():
            raise RuntimeError(f"Missing portable replay input: {bundle / required}")
    return {
        "asset_library_entries": len(assets),
        "asset_contracts": len(contracts),
        "assembly_references": len(references),
        "normalized_glb_files_present": sum((bundle / a["normalized_glb"]).is_file() for a in assets),
    }


def stage_virtual_root(bundle: Path, source_paper: Path, runtime_root: Path) -> dict[str, Any]:
    """Stage metadata and JSON source while leaving all frozen source bytes intact."""
    paper_link = runtime_root / PAPER_REL
    paper_link.parent.mkdir(parents=True, exist_ok=True)
    paper_link.symlink_to(source_paper, target_is_directory=True)
    (runtime_root / "sim").symlink_to(bundle / "sim", target_is_directory=True)

    export = runtime_root / "exports/biofoundry"
    library = export / "library"
    library.mkdir(parents=True)
    (export / "asset-library.json").symlink_to(bundle / "asset-library.json")
    if (bundle / "facility-inventory.json").is_file():
        (export / "facility-inventory.json").symlink_to(bundle / "facility-inventory.json")

    placeholder = b"biofoundry-v3.1-portable-glb-placeholder\n"
    staged = []
    for asset in read_json(bundle / "asset-library.json")["assets"]:
        asset_id = asset["asset_id"]
        asset_dir = library / asset_id
        asset_dir.mkdir(parents=True)
        for filename in ("asset.contract.json", "assembly-reference.json"):
            (asset_dir / filename).symlink_to(bundle / "library" / asset_id / filename)
        # Binding.__init__ hashes this path but never parses it on this path.
        glb = contained_path(export, asset["normalized_glb"])
        if glb.is_symlink():
            raise ValueError('Refusing a GLB symlink target')
        glb.parent.mkdir(parents=True, exist_ok=True)
        glb.write_bytes(placeholder)
        staged.append(str(glb.relative_to(runtime_root)))
    return {
        "runtime_root": str(runtime_root),
        "links": {
            "docs/paper/biofoundry-preprint": str(source_paper),
            "sim": str(bundle / "sim"),
            "exports/biofoundry/asset-library.json": str(bundle / "asset-library.json"),
        },
        "normalized_glb_adapter": {
            "mode": "deterministic_placeholder_files",
            "count": len(staged),
            "sha256": sha256_bytes(placeholder),
            "reason": "The unchanged Library constructor hashes normalized_glb paths; this replay path does not parse geometry or compare model fingerprints.",
            "paths": staged,
        },
    }


def rebase_module_globals(module: Any, *, runtime_root: Path, runtime_paper: Path, export: Path, output: Path, freeze: Path) -> None:
    """Rebase source-tree globals only; no source code or checker logic is patched."""
    module.ROOT = runtime_root
    module.VLAB = runtime_root
    module.PAPER = runtime_paper
    if hasattr(module, "EXPORT"):
        module.EXPORT = export
    if hasattr(module, "V2"):
        module.V2 = runtime_paper / "benchmarks/v2"
    if hasattr(module, "PLAN_DIR"):
        module.PLAN_DIR = runtime_paper / "source-data/v2/repair/plans"
    if hasattr(module, "CATALOG"):
        module.CATALOG = runtime_paper / "source-data/v2/catalog.json"
    if hasattr(module, "LANGUAGE_DIAGNOSTICS"):
        module.LANGUAGE_DIAGNOSTICS = runtime_paper / "source-data/v2/language-diagnostics.json"
    if hasattr(module, "PROTOCOL"):
        module.PROTOCOL = runtime_paper / "benchmarks/v3/VALIDATION_PROTOCOL.md"
    if hasattr(module, "OUT"):
        module.OUT = output
    if hasattr(module, "FREEZE"):
        module.FREEZE = freeze


def canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items() if key.lower() not in {"fullpath", "full_path"}}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def first_difference(expected: Any, actual: Any, path: str = "$") -> dict[str, Any] | None:
    if type(expected) is not type(actual):
        return {"path": path, "expected_type": type(expected).__name__, "actual_type": type(actual).__name__}
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                return {"path": f"{path}.{key}", "expected_present": key in expected, "actual_present": key in actual}
            result = first_difference(expected[key], actual[key], f"{path}.{key}")
            if result:
                return result
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return {"path": path, "expected_length": len(expected), "actual_length": len(actual)}
        for index, (left, right) in enumerate(zip(expected, actual)):
            result = first_difference(left, right, f"{path}[{index}]")
            if result:
                return result
        return None
    return None if expected == actual else {"path": path, "expected": expected, "actual": actual}


def compare_json(expected_path: Path, actual_path: Path, sort_key: str | None = None) -> dict[str, Any]:
    expected = canonical(read_json(expected_path))
    actual = canonical(read_json(actual_path))
    if sort_key and isinstance(expected, list) and isinstance(actual, list):
        expected = sorted(expected, key=lambda row: row.get(sort_key, ""))
        actual = sorted(actual, key=lambda row: row.get(sort_key, ""))
    equal = expected == actual
    result: dict[str, Any] = {
        "expected": str(expected_path),
        "actual": str(actual_path),
        "expected_sha256": sha256(expected_path),
        "actual_sha256": sha256(actual_path),
        "scientific_fields_equal": equal,
    }
    if not equal:
        result["first_difference"] = first_difference(expected, actual)
    return result


def compare_mutations(expected_path: Path, actual_path: Path) -> dict[str, Any]:
    def rows(path: Path) -> list[dict[str, Any]]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected = sorted((canonical(row) for row in rows(expected_path)), key=lambda row: row.get("mutation_id", ""))
    actual = sorted((canonical(row) for row in rows(actual_path)), key=lambda row: row.get("mutation_id", ""))
    equal = expected == actual
    result: dict[str, Any] = {
        "expected": str(expected_path),
        "actual": str(actual_path),
        "expected_records": len(expected),
        "actual_records": len(actual),
        "scientific_fields_equal": equal,
    }
    if not equal:
        result["first_difference"] = first_difference(expected, actual)
    return result


def require_new_output(output: Path, bundle: Path, source_paper: Path) -> None:
    output = output.resolve()
    forbidden = [bundle.resolve(), source_paper.resolve() / "source-data/v3"]
    if any(output == path or is_relative_to(output, path) for path in forbidden):
        raise ValueError(f"Refusing to overwrite frozen inputs: {output}")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Replay output must be a new or empty directory: {output}")
    output.mkdir(parents=True, exist_ok=True)


def run_replay(bundle: Path, source_paper: Path, output: Path) -> dict[str, Any]:
    bundle, source_paper, output = bundle.resolve(), source_paper.resolve(), output.resolve()
    inventory = validate_bundle(bundle)
    require_new_output(output, bundle, source_paper)
    freeze = bundle / FREEZE_REL
    source_mutation, source_validation = source_paper / MUTATION_REL, source_paper / VALIDATION_REL
    source_hashes = {
        "mutation_sha256": sha256(source_mutation),
        "validation_sha256": sha256(source_validation),
        "library_protocols_bundle_sha256": sha256(bundle / "sim/library_protocols.py"),
    }

    with tempfile.TemporaryDirectory(prefix="biofoundry-v3.1-replay-") as temp_dir:
        runtime_root = Path(temp_dir) / "virtual-lab"
        adapter = stage_virtual_root(bundle, source_paper, runtime_root)
        runtime_paper, export = runtime_root / PAPER_REL, runtime_root / "exports/biofoundry"
        mutation = load_module("biofoundry_v31_replay_mutation", source_mutation)
        rebase_module_globals(mutation, runtime_root=runtime_root, runtime_paper=runtime_paper, export=export, output=output, freeze=freeze)

        original_loader = mutation.load_module
        def load_and_rebase(name: str, path: Path):
            loaded = original_loader(name, path)
            if name == "biofoundry_v3_validation":
                rebase_module_globals(loaded, runtime_root=runtime_root, runtime_paper=runtime_paper, export=export, output=output, freeze=freeze)
            return loaded
        mutation.load_module = load_and_rebase

        frozen = mutation.assert_frozen()
        validation = load_module("biofoundry_v31_replay_validation", source_validation)
        rebase_module_globals(validation, runtime_root=runtime_root, runtime_paper=runtime_paper, export=export, output=output, freeze=freeze)
        validation_rows = validation.run_validation(output / "validation")
        mutation_summary = mutation.run_suite()

    validation_compare = compare_json(bundle / CONTRACT_LIFECYCLE_REL, output / "validation/contract-lifecycle.json", "asset_id")
    workflow_compare = compare_json(bundle / WORKFLOW_PROBE_REL, output / "validation/workflow-action-probe.json")
    mutation_compare = compare_mutations(bundle / MUTANTS_REL, output / "mutations/mutants.jsonl")
    summary_compare = compare_json(bundle / "raw/mutation-summary.json", output / "mutation-summary.json")
    if len(validation_rows) != 26:
        raise RuntimeError(f"Expected 26 positive traces, found {len(validation_rows)}")
    negative_count = sum(len(row.get("cases", [])) for row in validation_rows)
    if negative_count != 156:
        raise RuntimeError(f"Expected 156 negative traces, found {negative_count}")
    if mutation_summary.get("union", {}).get("total") != 407:
        raise RuntimeError("Fresh mutation replay did not produce 407 records")

    report = {
        "schema": SCHEMA,
        "bundle": str(bundle),
        "source_paper": str(source_paper),
        "output_dir": str(output),
        "source_hashes": source_hashes,
        "frozen_record": {"freeze_sha256": sha256(freeze), "inputs_verified_by_original_assert_frozen": True, "total_mutations": frozen["total_mutations"]},
        "bundle_inventory": inventory,
        "adapter": {
            "original_modules_imported_unchanged": True,
            "rebased_globals": ["ROOT", "VLAB", "PAPER", "EXPORT", "V2", "PLAN_DIR", "CATALOG", "LANGUAGE_DIAGNOSTICS", "PROTOCOL", "OUT", "FREEZE"],
            "modulefilelogicalpath": "No such global exists in the frozen source; module __file__ was left unchanged for source hashing.",
            **adapter,
        },
        "replay": {
            "contract_lifecycle": {"positive_traces": len(validation_rows), "negative_traces": negative_count, "comparison": validation_compare},
            "workflow_action_probe": workflow_compare,
            "mutations": {"records": mutation_compare, "summary": summary_compare, "fresh_checker_execution": True},
        },
        "pass": all(result.get("scientific_fields_equal", False) for result in (validation_compare, workflow_compare, mutation_compare, summary_compare)),
        "notes": [
            "The validation and mutation checkers executed from frozen source files; raw JSONL booleans were not re-scored.",
            "Full paths are excluded from scientific-field comparison; stable records are sorted by asset_id or mutation_id.",
            "Placeholder GLBs are adapter files only and provide no geometry or collision evidence.",
        ],
    }
    write_json(output / "replay-report.json", report)
    if not report["pass"]:
        raise RuntimeError("Frozen replay differs from portable records; see replay-report.json")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=None, help="portable-v3.1 bundle directory")
    parser.add_argument("--source-paper", type=Path, default=None, help="full docs/paper/biofoundry-preprint source tree")
    parser.add_argument("--output-dir", type=Path, required=True, help="new output directory; frozen inputs are never overwritten")
    args = parser.parse_args()
    bundle = locate_bundle(args.bundle)
    source_paper = locate_source_paper(bundle, args.source_paper)
    report = run_replay(bundle, source_paper, args.output_dir)
    print(json.dumps({
        "pass": report["pass"],
        "output_dir": report["output_dir"],
        "positive_traces": report["replay"]["contract_lifecycle"]["positive_traces"],
        "negative_traces": report["replay"]["contract_lifecycle"]["negative_traces"],
        "mutations": report["replay"]["mutations"]["records"]["actual_records"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
