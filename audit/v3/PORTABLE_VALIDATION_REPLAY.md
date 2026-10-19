# Portable v3.1 validator replay

**Status:** passed on 2026-10-19 (local macOS checkout)

`reproducibility/v3/portable-v3.1/replay_validation_v31.py` performs a fresh
execution of the frozen validator and mutation source files. It does not
re-score the saved booleans in `raw/mutations/mutants.jsonl`. The runner builds
a temporary virtual-lab root, imports the original source files with
`importlib`, and rebinds their source-tree path globals to that root. The
source files are not edited or copied into the output.

The checked command was:

```sh
python3 docs/paper/biofoundry-preprint/reproducibility/v3/replay_validation_v31.py \
  --bundle docs/paper/biofoundry-preprint/reproducibility/v3/portable-v3.1 \
  --source-paper docs/paper/biofoundry-preprint \
  --output-dir /tmp/biofoundry-v31-replay-test-20261019b
```

The fresh run produced 26 positive contract traces, 156 contract-derived
negative traces (six for each of 26 access bindings), and all 407 frozen
mutations. The scientific fields of the fresh outputs matched the portable
records exactly after stable sorting by `asset_id` or `mutation_id`. The
mutation summary also matched exactly. The output was written outside the
bundle at `/private/tmp/biofoundry-v31-replay-test-20261019b`; the frozen
`source-data/v3` tree and portable raw records were not overwritten.

## Frozen inputs and source hashes

The original `mutation.py::assert_frozen()` completed successfully before the
replay. The freeze record SHA-256 was
`772e9b82ace7a8596e3d0e4974d9130e65d4240c4eb6858fe0bab0eaef5c8d9d`, and its
declared mutation count was 407. The replay observed these source hashes:

| Input | SHA-256 |
|---|---|
| `benchmarks/v3/mutation.py` | `3a09db53b4375e7be2a72c5ae27d1c435a3e1e641509739dd9cfbc01731a990e` |
| `benchmarks/v3/validation.py` | `80a246d79cdc36902ad5c774ebf2fb7a636a7b976ca8953f9094b5c1d4871ec7` |
| portable `sim/library_protocols.py` | `12ae3a20966672fe7e93a8a9f19e2fe1c0b86e5f75021ce50678e1aeffe62e5d` |

The staged metadata inventory contained 71 asset-library entries, 71 asset
contracts and 71 assembly-reference JSON files. No normalized GLB was present
in the portable bundle.

## GLB path adapter

`sim.library_protocols.Binding.__init__` computes a `model_glb_sha256` by
hashing the declared path. It does not parse or load geometry in the contract
lifecycle or mutation execution path. The runner therefore creates 71
deterministic placeholder files only inside the temporary virtual root so the
unchanged constructor can complete. It records this as an adapter difference;
the placeholder fingerprints are not compared with the frozen scientific
records and no geometry or collision conclusion is made by this replay.

The simulator snapshot, contracts and assembly references are the actual
portable files. The original module's `__file__` is left untouched so source
hashes remain meaningful; there is no `modulefilelogicalpath` global in the
frozen source. The rebased globals are `ROOT`, `VLAB`, `PAPER`, `EXPORT`, `V2`,
`PLAN_DIR`, `CATALOG`, `LANGUAGE_DIAGNOSTICS`, `PROTOCOL`, `OUT` and `FREEZE`.

The generated directory contains `validation/contract-lifecycle.json`,
`validation/workflow-action-probe.json`, `mutations/mutants.jsonl`,
`mutation-summary.json`, `fig6-validation-matrix.csv` and
`replay-report.json`. `replay-report.json` records the temporary path adapter,
input hashes, counts and field-by-field comparison status.
