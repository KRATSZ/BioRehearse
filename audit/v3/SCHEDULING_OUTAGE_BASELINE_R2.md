# R2 outage baseline audit

The retained prespecified KS4000 outage file
`source-data/v3/scheduling/ks4000_outage.jsonl` contains 18 records.  An
independent field audit confirms that all 18 records state
`baseline_budget_s=60` and `baseline_independent_valid=true`; no truth-pass or
shorter-budget plan is used in those rows.  The file has 9 valid repairs and 9
explicit `INFEASIBLE` repairs.

The JSONL SHA256 is
`99c2f50fc3c1d645aaf2c1f413654d12c46d18ee77e37434585166c2c72654d7`.

The v3.2 driver uses a separate held-out baseline path and does not alter this
retained outage file.  The earlier v3 parallel comparator remains in the old
JSONL as a superseded implementation result; v3.2 rows are separate.
