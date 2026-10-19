# Biofoundry v3.1 portable metadata bundle

This posthoc public adaptation contains the frozen v3.1 raw records, a raw-record re-score, the construction audit, the 71 delivered asset contracts, their 71 assembly-reference JSON files, `asset-library.json`, a snapshot of `sim/library_protocols.py`, and checker dependency snapshots.

Run `python3 tools/portable_v31.py --bundle . --verify` from this bundle to verify the manifest. `portable-rescore.json` is recomputed from `raw/mutations/mutants.jsonl`; it does not rerun the frozen checker or add truth labels. The same posthoc hash manifest is also stored at `source-data/v3/posthoc-source-manifest.json` in the source tree.

The original `benchmarks/v3/validation.py` requires the full source tree and normalized GLB files because `Library.binding_fingerprint` hashes each model. The metadata-only bundle therefore documents that original requirement instead of implying a hardware or geometry rerun.
