# BioRehearse computational reproduction

Use Python 3.12 with `requirements-v2.lock.txt`. Original assets remain in virtual-lab. Scheduling, statistical analysis, independent score checks and language re-scoring do not need meshes, a GPU or paid inference.

From the package root:

```sh
python benchmarks/v2/analyse.py
python benchmarks/v2/recheck_saved.py
```

The study froze 60 workload designs, 96 language requests, 24 repair workloads, source and scoring code before evaluation. Primary schedules contain 1,080 complete outcomes; raw model records contain 120 runs per model including prespecified repeats. Do not rerun into these evidence directories. To generate a new schedule run, copy the package into a separate experiment directory and move its heldout results to a clearly named retained-results directory; the runner refuses overwrites.

`benchmarks/v2/frozen.json` preserves the local protocol. `reproducibility/source-v2/` is the exact Python source snapshot. The standalone GitHub release adds the live TypeScript dependency chain, original manifests and explicit local-path adaptation, without changing methods, tasks or scores. The original source map fingerprints distinguish the evaluated source from portability configuration.

Figure scripts are in `figures/v2/source/`; editable SVG/PDF exports are in `figures/v2/`. All quantitative marks read raw records or their deterministic summaries. The native Blender rendering scripts use the source geometry referenced by asset manifests. Re-rendering those panels requires `BIOFOUNDRY_VLAB` pointing to the original asset workspace (or passing `--root` to Blender); it does not download or duplicate the asset library. Static paper figures are not browser UI captures. Figure QA uses unchanged nature-figure helpers in `reproducibility/figure-qa/`.

`source-data/v2/browser-summary.json` is a secondary Python/JavaScript state-field comparison; `browser-states.jsonl.gz` retains the states. This verifies shared field values, not physical geometry or human inspection accuracy.

All development failures, original v1 negative results and final failures remain available. Account snapshots, worker sessions and assurance prompts are local-only; the public package excludes these and all credentials. The manuscript and exported paper figures remain local pending authors' upload decision.
