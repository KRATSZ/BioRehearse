# BioRehearse v4 reproduction

The manuscript's v4 extension uses the original v2 source snapshot and test designs. Keep the original requirements lock and all v2/v3 input files. No image library is needed for numerical reproduction. Python3.12 and OR-Tools9.15.6755 are the recorded environment.

From the paper/release root:

```
python reproducibility/verify_v4.py --paper .
python benchmarks/v4/aggregate_economics.py --self-test
python benchmarks/v4/aggregate_economics.py --paper . --output /tmp/new-biorehearse-economics
python benchmarks/v4/capacity_sensitivity.py --paper . --output /tmp/new-biorehearse-capacity --budget 2
python benchmarks/v4/derive_reporting.py --paper .
```

Both aggregation and solver runners require a new output directory and refuse overwriting existing outcomes. `derive_reporting.py` recreates only the three named derived summary tables from saved raw outcomes. Copy the source-data tree first if retaining byte-identical derivatives matters. The independent replay checks all180 saved outcomes and every returned schedule, mass and station location without re-solving. It does not certify physical geometry.

The capacity runner saves a protocol before solving. New 2-s runs may yield different incumbents or timeouts with machine load; numerical summaries of saved outcomes can be reproduced independently. Existing v2/v3 certificates, raw failures and amended heuristic histories remain available. A final seven-case infeasibility classification combines the staged raw search and separate long-budget proof. The recorded shaker outage lasts240s and shifts nine valid completions by180s; baseline allowance60s and actual replanning allowance5s are distinct.

EPI is modeled sqrt((elapsed_h/N)*(nominal_CNY/N)). Here N excludes added controls and technical replication. Mixed-assay N values do not imply equivalent biological output. Bootstrap units are workload designs, not repeated solver executions or wells. All original nonreturns remain in the outcomes table; economic effects condition on corresponding jointly valid workload means. Rates, recipes and capacities are model assumptions; no invoice, realized avoided loss or procurement payback is inferred.

Editable figures are in figures/v4/source; exported PDF/SVG/PNG and source tables accompany the local manuscript. Source renders and library geometry remain referenced under figures/v3 and the original virtual-lab project. The v4 water view is a fresh native render with a wider camera. The 28-s Supplementary Video1 is an event-keyframe composition in videos/biorehearse-v4, not an interpolated physical trajectory. Its local HyperFrames source and input hashes are retained. Raw asset licensing applies separately to render derivatives; the public software repository does not redistribute meshes, manuscript figures or video.

The default `python reproducibility/verify_v4.py` also resolves the paper/release root from its own actual path. It compares raw makespan/cost to the independently scored saved plan and recomputes both throughput fields from the compiled graph and completion interval; EPI uses its separately defined input-sample denominator. A targeted regression rejects raw metric corruption and common-mode throughput corruption. Saved 180-outcome replay reproduces52/60,60/60 and53/60 valid plans for original/shaker/reader scenarios.
