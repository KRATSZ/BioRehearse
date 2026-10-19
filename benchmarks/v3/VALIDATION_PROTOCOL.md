# v3.1 layered-validation and mutation protocol

This protocol was frozen before the v3.1 run. The prior 400-record development
run is preserved under `source-data/v3/development-amendment/v3.0/` and is not
overwritten by this revision. The v3.1 suite is an offline, post-compilation
mutation study; it does not replace the v2 held-out benchmark and it does not
turn a digital asset trace into a hardware test.

## Inputs and scope

- Seed: `20261020` (Python `random.Random`, no global state).
- Base plans: all 24 `source-data/v2/repair/plans/repair-*.json` plans. Each
  must pass the independent v2 arithmetic scorer, mass check and material
  location check before being used as a substrate.
- Contract source: delivered `exports/biofoundry/library/*/asset.contract.json`
  plus the exact access-joint profile selected by
  `sim/library_protocols.py`. Twenty-six assets had this access lifecycle in
  the input catalog. The fifth layer is therefore a contract-backed access
  lifecycle check, not a generic image or mesh heuristic.
- Layers reported for every record: intent consistency, schedule arithmetic,
  component mass balance, material location/custody, and asset-contract access
  lifecycle. Compiled-plan mutations have intent marked `NA`; the
  asset-contract layer is marked `NA` for portfolio plans. The intent layer is
  evaluated only on seven recorded deadline mismatches from the frozen language
  study. Asset records are separate `Workflow.act` action probes over a
  selected asset, not the GFP/BCA/PicoGreen portfolio.

## Prespecified distribution

The v3.1 run contains 407 records: 40 unchanged controls, 72 records for each
of five plan/asset mutation families, and seven recorded deadline mismatches.
A deterministic local seed is recorded per generated record.

| family | construction | independent oracle label |
|---|---|---|
| `control` | deep copy with no field changed | `equivalent_control` |
| `delete_transfer` | remove one complete start/finish transfer pair; classify a same-station transfer as equivalent because it leaves the carrier location unchanged | `known_violation` or `equivalent_mutation` from the predeclared trace oracle |
| `incompatible_device` | replace a compiled operation resource with `bench`, leaving the original intent unchanged | `known_violation` |
| `shift_time` | move an operation to one second before its first predecessor ends | `known_violation` |
| `change_volume` | set one recorded transfer volume negative or above the recorded source amount | `known_violation` |
| `access_order` | execute a contract-derived lifecycle command before the required open/close/load state through `Workflow.act` | `known_violation` |
| `intent_deadline` | seven real deadline mismatches recorded in `language-diagnostics.json` | `known_violation` |

The construction rule supplies the oracle label. A checker can miss a known
violation; such misses remain in the JSONL and are listed in the summary.
Equivalent controls and same-station deletions are not counted as errors. The
suite is a mutation-yield study and no detection rate is interpreted as the
prevalence or sensitivity of errors produced by a language model. The v3.1
report separates 354/354 generated known plan/asset violations from 7/7
recorded deadline mismatches, 0/46 equivalent/control false positives, and
361/407 overall layer triggers. The equivalent denominator is determined by
the frozen random draw: 40 unchanged controls plus six same-station transfer
deletions. It is reported from the generated records, not rounded to a planned
target.

## Reproduction

From the repository root:

```bash
python3 docs/paper/biofoundry-preprint/benchmarks/v3/mutation.py --freeze
python3 docs/paper/biofoundry-preprint/benchmarks/v3/mutation.py
python3 docs/paper/biofoundry-preprint/benchmarks/v3/validation.py
python3 docs/paper/biofoundry-preprint/benchmarks/v3/mutation_challenge.py
```

The first command is run once before evaluation. The second command checks the
freeze and fails closed if any source hash, protocol count or seed changes.
The freeze includes the v3 scripts, the imported simulator source, every
asset-contract hash, and the seven raw diagnostic files. Outputs are
`source-data/v3/mutations/mutants.jsonl`,
`source-data/v3/mutation-summary.json`, `source-data/v3/fig6-validation-matrix.csv`,
`source-data/v3/validation/contract-lifecycle.json` and
`source-data/v3/validation/workflow-action-probe.json`.

## Exploratory challenge after the freeze

After the v3.1 freeze, a separate challenge was added without changing the
frozen script, seed or headline outputs. It uses seed `20261021` and 192
records: 48 moderate volume factors (0.5, 0.8, 1.2 or 1.5), 48 resource
substitutions sampled from real selectable catalog resources, 48 positive or
negative predecessor offsets (−600, −60, −1, +1, +60 or +600 s), 24 transfer
deletions and 24 asset-action access probes. Its outputs are
`source-data/v3/mutation-challenge.jsonl` and
`source-data/v3/mutation-challenge-summary.json`; it is an exploratory
mutation-yield record and is excluded from the v3.1 headline score.

## Limits

The access positions and joint traces are digital demonstrations. They do not
establish vendor API compatibility, calibrated loading clearance, robot IK,
collision freedom, analytical measurements, or biological validity. The
catalog records zero hardware adapters; that scope is retained in the data and
Methods even when the zero is omitted from a principal figure.
