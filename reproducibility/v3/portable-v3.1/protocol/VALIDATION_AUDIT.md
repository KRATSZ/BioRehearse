# v3 layered validation audit

The v3.1 protocol was frozen before the independent run. The v3.0
development-amendment record remains under
`source-data/v3/development-amendment/v3.0/`; it is not used as the v3.1
result. The v3.1 freeze is
`source-data/v3/mutation-freeze.json` (SHA-256
`772e9b82ace7a8596e3d0e4974d9130e65d4240c4eb6858fe0bab0eaef5c8d9d`).

## Contract-backed fifth layer

The delivered asset contracts expose access joints through the exact profile
selected by `sim/library_protocols.py`. Twenty-six of the 71 contract files
declare a tested access lifecycle. Each completed the digital trace
`open → load → close → start → finish → open → unload → close`. The same 26
assets were exercised with six predeclared access-order mutations. All 156
negative cases were rejected atomically with the contract-expected code,
including `ACCESS_CLOSED`, `WRONG_LOCATION`, `ACCESS_OPEN`, `BUSY` and
`NOT_LOADED`.

The atomicity statement above applies to these 156 fresh-state
`validation.py::_reject` cases. The `state_unchanged` field in the random
mutation JSONL compares with the initial state before any valid prefix actions
and is therefore not an atomicity measurement for the final rejected action.

The separate `workflow-action-probe.json` record uses the selected KS4000
asset through `Workflow.act`, with initial state from
`sim.library_protocols.demo_samples()`. A closed-door load was rejected as
`ACCESS_CLOSED` without changing state, followed by the positive lifecycle
trace. This is an asset-action probe. It does not mean that the compiled
GFP/BCA/PicoGreen portfolio plans passed the fifth layer: those plan rows are
marked `asset_contract = NA` in the mutation records.

These are digital contract checks. They do not validate vendor commands,
calibrated clearances, collision freedom, hardware adapters or biological
measurements.

## Frozen v3.1 mutation yield

The suite contains 407 records: 40 unchanged controls, 72 records in each of
five plan/asset mutation families, and seven recorded deadline mismatches. All
24 v2 repair plans passed the independent v2 schedule, component-balance and
material-location checks before mutation. Detection is a mutation yield, not a
naturally occurring error rate.

| family | n | intent | schedule | mass balance | material location | asset contract | union |
|---|---:|---:|---:|---:|---:|---:|---:|
| control | 40 | NA | 0/40 | 0/40 | 0/40 | NA | 0/40 |
| delete transfer | 72 | NA | 0/72 | 0/72 | 66/72 | NA | 66/72 |
| incompatible device | 72 | NA | 72/72 | 0/72 | 0/72 | NA | 72/72 |
| shift time | 72 | NA | 72/72 | 0/72 | 0/72 | NA | 72/72 |
| change volume | 72 | NA | 0/72 | 72/72 | 0/72 | NA | 72/72 |
| access order | 72 | NA | NA | NA | NA | 72/72 | 72/72 |
| intent deadline | 7 | 7/7 | NA | NA | NA | NA | 7/7 |

The plan/asset rows contain 354 independently labelled known violations and
all 354 were detected. A separate construction audit
(`source-data/v3/construction-audit-407-192.jsonl`, summarized in
`source-data/v3/construction-audit-summary.json`) mechanically checked the
premises of those labels against the original source plans. It found 66/66
cross-station transfer deletions with a first later use at the declared
destination, 72/72 device substitutions outside the task candidates, and
72/72 time shifts whose recorded new start was strictly before the actual
predecessor end. The seven recorded deadline mismatches were detected by the
intent layer. The remaining 46 records (40 controls and six same-station
transfer deletions) were equivalent by the predeclared oracle; none was
flagged. The resulting union is 361/407 (88.70%). The same-station deletion
rule is supported by the independent source/destination trace oracle: the
removed transfer starts and ends at the same station, so it does not change
the carrier location. All 407 records, including misses if any, remain in
`mutants.jsonl`; the construction audit is a derived denominator review and
does not rewrite that raw file.

The seven intent cases are not synthetic mutations. They are the six
`deepseek-flash` and one `deepseek-v4-pro` deadline mismatches recorded in
`source-data/v2/language-diagnostics.json`; their raw response paths and SHA
256 hashes are included in the v3 freeze. Compiled-plan mutations keep
`intent = NA` because changing a post-compilation resource or schedule is not
an intent test.

## Exploratory challenge

After the v3.1 freeze, an independent 192-record challenge was run with seed
`20261021`. It samples moderate volume factors (0.5, 0.8, 1.2 and 1.5), real
selectable resource substitutions (including candidate-compatible choices),
positive and negative predecessor offsets, transfer deletions and asset-action
access faults. The challenge is recorded in
`source-data/v3/mutation-challenge.jsonl` and
`source-data/v3/mutation-challenge-summary.json`. The mass checker triggered on
6/48 protocol-quantity changes and missed 42/48 method-level quantity
mismatches that conserved total volume; these misses are retained as evidence
that conservation and protocol compliance are different checks. The challenge
labels and misses are exploratory and are excluded from the frozen v3.1
headline score.

The exact challenge layer counts are:

| family | n | schedule | mass balance | material location | asset contract | union |
|---|---:|---:|---:|---:|---:|---:|
| volume factor | 48 | 0/48 | 6/48 | 0/48 | NA | 6/48 |
| device resource | 48 | 48/48 | 0/48 | 0/48 | NA | 48/48 |
| shift offset | 48 | 46/48 | 0/48 | 0/48 | NA | 46/48 |
| delete transfer | 24 | 0/24 | 0/24 | 21/24 | NA | 21/24 |
| access order | 24 | NA | NA | NA | 24/24 | 24/24 |
| total | 192 | 94/192 applicable | 6/192 applicable | 21/192 applicable | 24/192 applicable | 145/192 |

The raw challenge keeps the original construction labels. The derived files
`mutation-challenge-annotated.jsonl` and
`mutation-challenge-annotated-summary.json` rename the 26 nonnegative time
offset flags to `nonnegative_precedence_offset_other_constraints_unlabelled`
and the one candidate-compatible resource flag to
`candidate_compatible_resource_other_constraints_unlabelled`. Neither label is
treated as an equivalence-validity oracle or as a false-positive denominator.

The construction audit independently checked the full 192-record challenge.
The corrected known-error denominator is 162/192: 48 protocol-quantity
changes, 47 non-candidate resource replacements, 22 strictly negative
precedence shifts, 21 transfer deletions with a destination use, and 24
contract access probes. The corresponding measured union is 120/162; the
other 30 records in the 192-row challenge are the one candidate-compatible
resource change, 26 nonnegative or otherwise unlabelled time offsets, and
three same-station transfer deletions. Separately, within the 48
protocol-quantity changes, the mass layer detected 6 and missed 42,
preserving the method-level quantity blind spot. A time shift is called known
only when the recorded start is strictly before the source-plan predecessor
end; a transfer deletion is called known only when a later use at its declared
destination is present. These denominators come from the derived
construction-audit file, not from the measured checker outputs.

## Reproduction and artifacts

From the repository root:

```bash
python3 docs/paper/biofoundry-preprint/benchmarks/v3/mutation.py --freeze
python3 docs/paper/biofoundry-preprint/benchmarks/v3/mutation.py
python3 docs/paper/biofoundry-preprint/benchmarks/v3/validation.py
python3 docs/paper/biofoundry-preprint/benchmarks/v3/mutation_challenge.py
python3 docs/paper/biofoundry-preprint/benchmarks/v3/construction_audit.py
```

The v3.1 freeze includes the mutation and validation scripts, the simulator
source used by the action trace, all 71 asset-contract hashes, all 26 access
contract hashes, the 24 base-plan hashes and the seven raw diagnostic hashes.
The compact matrix for Fig. 6 is
`source-data/v3/fig6-validation-matrix.csv`; contract traces are in
`source-data/v3/validation/contract-lifecycle.json`; the selected workflow
probe is in `source-data/v3/validation/workflow-action-probe.json`. The
post-freeze source hash addendum is
`source-data/v3/posthoc-source-manifest.json`; it covers the asset-library
catalogue, all 71 contracts, all 71 assembly references and the simulator
source snapshot, plus the checker-dependency snapshots, without modifying the
v3.1 freeze retroactively.

The construction-audit helper has its own source and run hashes in
`source-data/v3/construction-audit-summary.json`. Its source-plan hashes are
posthoc audit provenance; they do not amend `mutation-freeze.json`.

The v2 freeze and v2 outputs are unchanged. The catalog still records zero
hardware adapters; this scope is retained in the data and Methods even when
the zero is omitted from a principal figure.
