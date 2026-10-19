# BioRehearse

Executable digital rehearsal for registered biofoundry plans: typed intent → method graph → shared-resource schedule → liquid and material-location state → 3D replay.

This repository contains code and computational evidence. It does not publish a manuscript, connect hardware or execute biological experiments. The three registered method families are cell-free GFP, BCA and PicoGreen. The language interface retains LabscriptAI’s one-model, one-loop tool harness; deterministic compilation, CP-SAT and visualization have separate roles.

## Reproduce without API calls

Python 3.12 was used. From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r reproducibility/requirements-v2.lock.txt
.venv/bin/python benchmarks/v2/analyse.py
.venv/bin/python benchmarks/v2/recheck_saved.py
.venv/bin/python reproducibility/verify_legacy_location.py
.venv/bin/python reproducibility/demo_v2.py --out outputs/new-demo.json
```

The retained evidence includes 60 workload designs ×3 planners ×2 objectives ×3 executions (1,080 outcomes), 96 language requests with 120 executions per model, 24 new repair/replanning cases and120 controlled defect/control probes. All final failures and earlier development failures are retained. The legacy liquid-use check reproduces the original16 missing-water location failures using the old implementation; the corrected v2 model is evaluated separately. Runtime/output fields may vary on new machines.

## Source and scope

- `reproducibility/source-v2/`: frozen Python implementation and independent material-state scoring inputs.
- `benchmarks/v2/`: fixed designs, runners, scoring and analysis. All primary outcomes are under `source-data/v2/`.
- `harness/`: evaluated TypeScript authoring import chain and Python CLI. The original per-file source map is in `provenance/`; the only portability configuration change is the relative asset-metadata directory.
- `figures/v2/source/`: Python figure and native Blender rendering sources. Geometry itself remains in the original virtual-lab resource, referenced with source hashes and licenses. Set `BIOFOUNDRY_VLAB` or Blender’s `--root` to that resource. Scheduling/ledger analyses need no geometry. Exported manuscript figures are not included in this code publication.
- `legacy/`: retained original source and plans needed to reproduce the defect, separate from v2 results.

To relocate live-source verification after cloning, run `python reproducibility/relocate_v2.py`. It verifies code hashes and remaps only absolute paths. The public language runner requires --max-spend-cny and a fresh account baseline, and refuses to overwrite evidence. The private study opening balance was removed from this public-only administrative gate; prompts, tasks and scoring are unchanged. Paid replication needs a new output directory and credentials supplied locally. No credentials or account snapshots are included.

The asset resource contains71 assets, of which64 have joint contracts. Facility binding covers54 of73 instances using43 asset identifiers; it does not establish surveyed coordinates or installed options. These computational results establish neither hardware closed-loop operation, collision certification nor biological validation. See `reproducibility/README-v2.md` and `THIRD_PARTY.md`.
