# Reproducing the v3 computational study

Use Python **3.12.13** and OR-Tools **9.15.6755**, as recorded by the frozen runners. Install `reproducibility/requirements-v2.lock.txt`; the v3 analyses use that same Python environment. No API calls are needed to inspect and re-score saved plans or replay the digital contracts.

## Primary and retrospective evidence

The immutable v2 files retain the initial 60-design scheduling study, language requests and repair set. V3 reuses those designs for certificate, budget and comparator extensions. This is a retrospective extension, not a fresh unseen test set. Each amendment has its own source/configuration record; the corrected comparator is **sgs_v33**, preserving all older implementations and outputs.

- `source-data/v3/scheduling/cp_sat_truth_runs.jsonl` / `truth-final.json`: staged caps of 2, 10 and 60 s. The final classifications at that stage are 53 feasible, six INFEASIBLE and one UNKNOWN, over 60 designs and 63 attempts.
- `cp_sat_unknown_300s_followup*`: the separate 93.6-s infeasibility proof resolves the last UNKNOWN. It does not replace the original 60-s-stage row.
- `budget-effects.csv`: 20 fixed designs, each independently run at every CP-SAT allowance.
- `sgs_v33_runs.jsonl`: 20 designs × two variants × three allowances =120 actual executions. Serial returns12/20 and parallel4/20 at each allowance. One serial2-s execution times out; the others' NO_SGS_PLAN is a heuristic nonreturn, never a proof of infeasibility.
- `ks4000_outage.jsonl`: known180-s outage on18 eligible baseline designs, nine valid repairs/+180s and nine INFEASIBLE. Independent checks confirm every baseline is a valid separate60-s result and returned repairs preserve started rows. The900-s challenge uses those same cases, separately labelled exploratory.

The historical `run.py` remains byte-identical to the evaluated source. Its generic baseline-fallback weakness is documented in `audit/v3/SCHEDULING_OUTAGE_BASELINE_R2.md`; all18 actual baseline records were checked and are unaffected. Do not treat the historical runner as a newly corrected production scheduler. `protocol-sgs-v33.json` protects the current comparator's complete configuration and source hashes.

## Local paper-tree checks

From the paper directory, with `.venv/bin/python` or a matching environment:

```sh
python benchmarks/v2/recheck_saved.py
python reproducibility/verify_legacy_location.py
python benchmarks/v3/portable_v31.py --bundle reproducibility/v3/portable-v3.1 --verify
python reproducibility/v3/replay_validation_v31.py --source-paper . --output-dir /tmp/biorehearse-fresh-validation
```

Choose a new output directory. The replay actually executes unchanged `mutation.py`, `validation.py` and simulator source for26 positive lifecycles,156 directed invalid orders and407 variants. It does not merely recount saved detection flags. The metadata bundle excludes geometry: deterministic temporary placeholder files satisfy the constructor's hash lookup on a path that never parses GLB. The report records this adaptation; it supplies no geometric, collision or rendering evidence.

The407-record set comprises328 plan records on24 base plans,72 separate asset-action probes and seven previously observed intent errors. Of361 construction-confirmed violations, all are flagged;46 controls/equivalent records remain unflagged. The exploratory192 records include162 confirmed errors,120 detections and42 missed moderate quantity changes. `construction_audit.py` checks error premises independently of detector outputs. These are nested finite artifact counts, not407 independent experiments. `portable_v31.py --verify` additionally verifies the metadata-bundle hashes and recounts raw records; it is distinct from fresh checker execution.

## Public checkout

The public v2 runner has an already documented account-budget/path adaptation; its sanitized source must not be overwritten by private v2 files. V3 publication retains original design/protocol files in `provenance/` and records each public-only dependency-hash adaptation. Those adaptations change neither method code, requests, workload membership nor scoring, and are not new prospective freezes. Run the public relocation helper described in the release README after cloning, then execute the same offline checks above. A matching release is verified before its tag is reported in `audit/v3/CODE_RELEASE.json`.

Runners refuse to overwrite primary results. Full algorithm reruns should be performed in a disposable copy, retaining the existing result directory separately first. Inspect the corresponding design/protocol and amendment notes before executing a historical version. Runtime and solver status can vary by machine and load; keep all new failures, wall times and source hashes.

## Language, figures and rights

The two primary models each use96 first test executions plus24 prespecified repeat executions. The retrospective GLM comparison uses96 test requests;12 development requests are separate. All strict scores and failed outputs remain available. API replication requires local credentials and an explicit fresh spending allowance for paid routes; there is no paid fallback in the GLM probe.

Six figure scripts under `figures/v3/source/` generate quantitative panels directly from the recorded results. Native rendering scripts refer to original geometry, layout and state inputs; they do not use image generation. The original71-asset library and video stay in virtual-lab. Per-asset source rights apply, including CC BY-NC and upstream exceptions; the software MIT license does not relicense those materials. Author-review manuscript figures remain local.
