"""Export and re-score the frozen v3.1 records from a relocatable bundle.

The original mutation and validation scripts remain unchanged and retain their
source-tree assumptions.  This helper provides a public adaptation: it copies
the frozen raw records, the 71 contract and assembly-reference JSON files, the
asset-library catalogue and the simulator source snapshot, then recomputes the
layer counts from the raw records without importing the original fixed-path
scripts.  It deliberately does not copy GLB files or claim that the original
asset validation can run from metadata alone.

Examples::

    python benchmarks/v3/portable_v31.py --root /path/to/virtual-lab
    python benchmarks/v3/portable_v31.py --bundle reproducibility/v3/portable-v3.1 --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

PAPER_REL = Path("docs/paper/biofoundry-preprint")
RAW_REL = PAPER_REL / "source-data/v3"
EXPORT_REL = Path("exports/biofoundry")

RAW_FILES = (
    "mutation-freeze.json",
    "mutation-summary.json",
    "fig6-validation-matrix.csv",
    "mutations/mutants.jsonl",
    "validation/contract-lifecycle.json",
    "validation/workflow-action-probe.json",
    "mutation-challenge.jsonl",
    "mutation-challenge-summary.json",
    "mutation-challenge-annotated.jsonl",
    "mutation-challenge-annotated-summary.json",
    "construction-audit-407-192.jsonl",
    "construction-audit-summary.json",
)

# These are recorded as a posthoc dependency addendum.  They are deliberately
# kept out of mutation-freeze.json because the v3.1 run has already completed.
CHECKER_DEPENDENCY_FILES = (
    "docs/paper/biofoundry-preprint/benchmarks/v2/scorer.py",
    "docs/paper/biofoundry-preprint/benchmarks/v2/common.py",
    "docs/paper/biofoundry-preprint/benchmarks/v2/repair.py",
    "docs/paper/biofoundry-preprint/benchmarks/v2/frozen.json",
    "docs/paper/biofoundry-preprint/benchmarks/scorer.py",
    "docs/paper/biofoundry-preprint/benchmarks/common.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def locate_root(explicit: Path | None = None) -> Path:
    candidates = []
    if explicit is not None:
        candidates.append(explicit.expanduser().resolve())
    if os.environ.get("BIOFOUNDRY_VLAB"):
        candidates.append(Path(os.environ["BIOFOUNDRY_VLAB"]).expanduser().resolve())
    candidates.extend([Path.cwd().resolve(), Path(__file__).resolve()])
    for start in candidates:
        places = [start, *start.parents]
        for place in places:
            if (place / RAW_REL / "mutation-freeze.json").exists() and (place / EXPORT_REL / "asset-library.json").exists():
                return place
    raise FileNotFoundError("Could not locate virtual-lab root; pass --root or set BIOFOUNDRY_VLAB")


def copy_entry(source: Path, destination: Path, root: Path, bundle_root: Path, entries: list[dict]):
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    entries.append({
        "source": str(source.relative_to(root)),
        "bundle": str(destination.relative_to(bundle_root)),
        "bytes": source.stat().st_size,
        "sha256": sha256(source),
    })


def raw_rows(bundle: Path):
    path = bundle / "raw" / "mutations" / "mutants.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def rescore(rows: list[dict]) -> dict:
    layers = ("intent", "schedule", "mass_balance", "material_location", "asset_contract")
    categories = {}
    for category in sorted({row["category"] for row in rows}):
        group = [row for row in rows if row["category"] == category]
        layer_stats = {}
        for layer in layers:
            values = [row["layers"].get(layer) for row in group if row["layers"].get(layer) is not None]
            layer_stats[layer] = {
                "detected": sum(bool(value) for value in values),
                "total": len(values),
                "not_applicable": len(group) - len(values),
                "rate": sum(bool(value) for value in values) / len(values) if values else None,
            }
        categories[category] = {"n": len(group), "layers": layer_stats, "union": sum(any(value is True for value in row["layers"].values()) for row in group)}
    union = sum(any(value is True for value in row["layers"].values()) for row in rows)
    oracle_counts = {}
    for row in rows:
        label = row["oracle_label"]
        oracle_counts[label] = oracle_counts.get(label, 0) + 1
    known = [row for row in rows if row["oracle_label"] == "known_violation"]
    equivalent = [row for row in rows if row["oracle_label"].startswith("equivalent")]
    return {
        "schema": "biofoundry.v3.1.portable-rescore/1",
        "total": len(rows),
        "categories": categories,
        "oracle_counts": dict(sorted(oracle_counts.items())),
        "union": {"detected": union, "total": len(rows), "rate": union / len(rows)},
        "known_error_yield": {"detected": sum(any(value is True for value in row["layers"].values()) for row in known), "total": len(known)},
        "equivalent_or_control_detections": sum(any(value is True for value in row["layers"].values()) for row in equivalent),
        "notes": [
            "This is a raw-record re-score; it does not rerun frozen checkers or infer new truth labels.",
            "The portable bundle contains metadata and the simulator source snapshot but not GLB files.",
        ],
    }


def bundle(root: Path, destination: Path):
    paper = root / PAPER_REL
    export = root / EXPORT_REL
    if destination.exists():
        shutil.rmtree(destination)
    (destination / "raw").mkdir(parents=True)
    entries: list[dict] = []
    for rel in RAW_FILES:
        copy_entry(paper / "source-data/v3" / rel, destination / "raw" / rel, root, destination, entries)
    copy_entry(paper / "benchmarks/v3/VALIDATION_PROTOCOL.md", destination / "protocol/VALIDATION_PROTOCOL.md", root, destination, entries)
    copy_entry(paper / "audit/v3/VALIDATION.md", destination / "protocol/VALIDATION_AUDIT.md", root, destination, entries)
    copy_entry(paper / "audit/v3/VALIDATION_CONSTRUCTION_AUDIT.md", destination / "protocol/VALIDATION_CONSTRUCTION_AUDIT.md", root, destination, entries)
    copy_entry(paper / "audit/v3/VALIDATION_CODE_REVIEW.json", destination / "protocol/VALIDATION_CODE_REVIEW.json", root, destination, entries)
    copy_entry(paper / "benchmarks/v3/portable_v31.py", destination / "tools/portable_v31.py", root, destination, entries)
    copy_entry(paper / "benchmarks/v3/construction_audit.py", destination / "tools/construction_audit.py", root, destination, entries)
    copy_entry(export / "asset-library.json", destination / "asset-library.json", root, destination, entries)
    copy_entry(root / "sim/library_protocols.py", destination / "sim/library_protocols.py", root, destination, entries)

    checker_entries: list[dict] = []
    for rel_text in CHECKER_DEPENDENCY_FILES:
        source = root / rel_text
        destination_path = destination / "checker-dependencies" / Path(rel_text).relative_to(PAPER_REL)
        before = len(entries)
        copy_entry(source, destination_path, root, destination, entries)
        checker_entries.append(entries[before])
    source_v2 = root / "docs/paper/biofoundry-preprint/reproducibility/source-v2"
    if source_v2.exists():
        for source in sorted(source_v2.rglob("*.py")):
            if "__pycache__" in source.parts:
                continue
            destination_path = destination / "checker-dependencies/source-v2" / source.relative_to(source_v2)
            before = len(entries)
            copy_entry(source, destination_path, root, destination, entries)
            checker_entries.append(entries[before])

    contracts = sorted((export / "library").glob("*/asset.contract.json"))
    if len(contracts) != 71:
        raise RuntimeError(f"Expected 71 asset contracts, found {len(contracts)}")
    assembly_count = 0
    for contract in contracts:
        asset_id = contract.parent.name
        copy_entry(contract, destination / "library" / asset_id / "asset.contract.json", root, destination, entries)
        assembly = contract.parent / "assembly-reference.json"
        copy_entry(assembly, destination / "library" / asset_id / "assembly-reference.json", root, destination, entries)
        assembly_count += 1

    rows = raw_rows(destination)
    rescore_result = rescore(rows)
    (destination / "portable-rescore.json").write_text(json.dumps(rescore_result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    entries.append({"source": None, "bundle": "portable-rescore.json", "bytes": (destination / "portable-rescore.json").stat().st_size, "sha256": sha256(destination / "portable-rescore.json")})
    freeze = json.loads((destination / "raw/mutation-freeze.json").read_text())
    asset_catalog = json.loads((destination / "asset-library.json").read_text())
    manifest = {
        "schema": "biofoundry.v3.1.portable-source-manifest/1",
        "adaptation": "posthoc_public_metadata_bundle",
        "retroactive_freeze": False,
        "frozen_record": {
            "source_freeze_file_sha256": sha256(destination / "raw/mutation-freeze.json"),
            "source_freeze_inputs": freeze.get("inputs", {}),
        },
        "asset_counts": {"asset_library_entries": len(asset_catalog.get("assets", [])), "asset_contracts": len(contracts), "assembly_references": assembly_count},
        "profile_source": "sim/library_protocols.py snapshot plus asset.contract.json digital_protocol_profile fields",
        "posthoc_asset_hashes": [entry for entry in entries if entry["source"] and (entry["source"] == "exports/biofoundry/asset-library.json" or entry["source"] == "sim/library_protocols.py" or entry["source"].endswith("/asset.contract.json") or entry["source"].endswith("/assembly-reference.json"))],
        "checker_dependency_hashes": checker_entries,
        "posthoc_added_hashes": [entry for entry in entries if entry["source"] and (entry["source"] == "exports/biofoundry/asset-library.json" or entry["source"] == "sim/library_protocols.py" or entry["source"].endswith("/asset.contract.json") or entry["source"].endswith("/assembly-reference.json") or entry in checker_entries)],
        "posthoc_added_hashes_are_not_in_original_freeze": True,
        "entries": entries,
        "notes": [
            "The asset-library catalogue, 71 contracts, 71 assembly-reference JSON files, simulator source and checker dependency snapshots are included for metadata inspection and adapted re-scoring.",
            "The original validation.py also hashes normalized GLB files through Library.binding_fingerprint; those GLBs are intentionally not included in this metadata-only bundle. Run the original script in the full virtual-lab tree, or use portable-rescore.json for the frozen raw-record re-score.",
            "This manifest records source hashes after the v3.1 freeze and does not retroactively add them to mutation-freeze.json. Checker dependencies are a posthoc addendum, not evidence that the original freeze covered them.",
        ],
    }
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    (destination / "manifest.json").write_text(manifest_text)
    posthoc_manifest = paper / "source-data/v3/posthoc-source-manifest.json"
    posthoc_manifest.write_text(manifest_text)
    (destination / "posthoc-source-manifest.json").write_text(manifest_text)
    (destination / "README.md").write_text(
        "# Biofoundry v3.1 portable metadata bundle\n\n"
        "This posthoc public adaptation contains the frozen v3.1 raw records, a raw-record re-score, the construction audit, the 71 delivered asset contracts, their 71 assembly-reference JSON files, `asset-library.json`, a snapshot of `sim/library_protocols.py`, and checker dependency snapshots.\n\n"
        "Run `python3 tools/portable_v31.py --bundle . --verify` from this bundle to verify the manifest. `portable-rescore.json` is recomputed from `raw/mutations/mutants.jsonl`; it does not rerun the frozen checker or add truth labels. The same posthoc hash manifest is also stored at `source-data/v3/posthoc-source-manifest.json` in the source tree.\n\n"
        "The original `benchmarks/v3/validation.py` requires the full source tree and normalized GLB files because `Library.binding_fingerprint` hashes each model. The metadata-only bundle therefore documents that original requirement instead of implying a hardware or geometry rerun.\n"
    )
    return manifest, rescore_result


def verify(destination: Path):
    manifest = json.loads((destination / "manifest.json").read_text())
    failures = []
    for entry in manifest["entries"]:
        path = destination / entry["bundle"]
        if not path.exists() or sha256(path) != entry["sha256"]:
            failures.append(entry["bundle"])
    rows = raw_rows(destination)
    result = rescore(rows)
    saved = json.loads((destination / "portable-rescore.json").read_text())
    if result != saved:
        failures.append("portable-rescore.json")
    catalog = json.loads((destination / "asset-library.json").read_text())
    if len(catalog.get("assets", [])) != 71 or len(list((destination / "library").glob("*/asset.contract.json"))) != 71:
        failures.append("asset metadata counts")
    if failures:
        raise RuntimeError("Portable bundle verification failed: " + ", ".join(failures))
    return {"verified": True, "entries": len(manifest["entries"]), "records": len(rows), "assets": len(catalog["assets"]), "union": result["union"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, help="virtual-lab root; inferred from cwd/script path when omitted")
    parser.add_argument("--out", type=Path, default=None, help="bundle output directory")
    parser.add_argument("--bundle", type=Path, default=None, help="existing bundle to verify")
    parser.add_argument("--verify", action="store_true", help="verify an existing bundle")
    args = parser.parse_args()
    if args.verify:
        target = (args.bundle or args.out or Path.cwd()).expanduser().resolve()
        print(json.dumps(verify(target), ensure_ascii=False))
        return
    root = locate_root(args.root)
    destination = (args.out or root / PAPER_REL / "reproducibility/v3/portable-v3.1").expanduser().resolve()
    manifest, result = bundle(root, destination)
    print(json.dumps({"bundle": str(destination), "entries": len(manifest["entries"]), "records": result["total"], "union": result["union"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
