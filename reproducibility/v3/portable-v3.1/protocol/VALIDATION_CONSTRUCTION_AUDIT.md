# Construction audit for v3 mutation denominators

This addendum is a posthoc review of the immutable v3.1 records and the
192-record exploratory challenge. It reads each JSONL record and its original
source plan, then checks the construction premise independently of the
measured schedule, mass-balance, material-location and asset-contract
checkers. The helper is
`benchmarks/v3/construction_audit.py`; the row-level output is
`source-data/v3/construction-audit-407-192.jsonl` and the run manifest is
`source-data/v3/construction-audit-summary.json`.

The audit retained every v3.1 known label. The 354 plan/asset known records
are supported by 66/66 transfer deletions with a first later use at the
declared destination, 72/72 resource replacements whose new resource is
outside the operation candidate list, 72/72 shifts whose recorded new start
is before the actual predecessor end, 72/72 unphysical transfer volumes and
72/72 declared access-contract precondition probes. The seven externally
recorded deadline mismatches have distinct expected and actual deadlines.
The corrected v3.1 denominator is therefore 361 known violations (354
plan/asset plus seven intent cases), with 361/361 union detections and 46
equivalent or control records retained separately.

For transfer deletion, a cross-station source and destination is insufficient
by itself. The audit locates the original start/finish pair, records the moved
containers, finds the first later event that uses one of them, and requires
that event's required station to equal the declared destination and differ
from the source. Same-station deletions remain equivalent constructions.

For device replacement, the audit reads the original operation's
`candidates` list and requires the new resource to be absent from it. For a
time shift, it uses the recorded mutated start and the original predecessor
row and requires a strict arithmetic inequality; a nonnegative or clamped
offset is not a known precedence violation. These checks also cover the
exploratory records.

The corrected exploratory known-error denominator is 162/192: 48
protocol-quantity changes, 47 non-candidate resource replacements, 22 strict
precedence violations, 21 destination-use transfer deletions and 24 access
probes. The measured union is 120/162. The one candidate-compatible resource,
26 nonnegative or otherwise unlabelled time offsets and three same-station
deletions remain unlabelled/equivalent annotations; they are not counted as
false-positive controls. The volume family remains 48 protocol changes with
6/48 mass detections and 42/48 misses. The raw challenge labels and all
negative results are preserved in their original files.

Run from any checkout with a relocatable root:

```bash
python3 docs/paper/biofoundry-preprint/benchmarks/v3/construction_audit.py \
  --root /path/to/virtual-lab
```

The summary records SHA-256 hashes for this helper, both raw JSONL inputs, the
v3.1 freeze and code-review record, plus every source plan used by the audit.
Those plan hashes are posthoc provenance and do not amend the v3.1 freeze.
