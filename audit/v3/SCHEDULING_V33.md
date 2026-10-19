# v3.3 SGS timeout-signal correction

R3 identified one medium issue in v3.2: candidate enumeration returned
`None` both for an infeasible placement set and for a budget expiration.  The
v3.3 copy adds a `CandidateBudgetExceeded` signal.  The signal propagates out
of serial and parallel placement enumeration, discards any partial candidate
set, and returns `SGS_BUDGET_EXHAUSTED / SOLVER_UNRESOLVED` before reporting
`NO_SGS_PLAN`.

The v3.3 packet is independent of v3 and v3.2.  It does not modify their
source files or data.  Full source and configuration hashes are in
`benchmarks/v3/protocol-sgs-v33.json`; the implementation and driver are
`sgs_v33.py` and `sgs_v33_driver.py`.  The configuration digest is
`f32593282c665fe9696ffe221e3c1508f0e2d58c2c037ecb1e83f3e14fc40b1f`.

The mocked-clock counterexample from R3 was run in both modes.  It returned
`SGS_BUDGET_EXHAUSTED / SOLVER_UNRESOLVED` in both cases.  The same isolated
placement check used for v3.2 still selected the placement available at the
earliest parallel event.

The driver completed 120 unique held-out runs: 20 cases × serial/parallel ×
2/10/60 s.  Development selection contributed 48 execution rows and 8 summary
rows (56 JSONL rows total); it selected `input_order` independently for both
modes.

| mode | budget | valid / 20 | status |
| --- | ---: | ---: | --- |
| serial | 2 s | 12 | 12 `SERIAL_SGS`, 7 `NO_SGS_PLAN`, 1 `SGS_BUDGET_EXHAUSTED` |
| serial | 10 s | 12 | 12 `SERIAL_SGS`, 8 `NO_SGS_PLAN` |
| serial | 60 s | 12 | 12 `SERIAL_SGS`, 8 `NO_SGS_PLAN` |
| parallel | 2 s | 4 | 4 `PARALLEL_SGS`, 16 `NO_SGS_PLAN` |
| parallel | 10 s | 4 | 4 `PARALLEL_SGS`, 16 `NO_SGS_PLAN` |
| parallel | 60 s | 4 | 4 `PARALLEL_SGS`, 16 `NO_SGS_PLAN` |

The one explicit 2-s SGS timeout is `heldout-051` in serial mode.  Valid-plan
counts are unchanged from v3.2; the difference is the truthful status signal.
The raw files are `sgs_v33_runs.jsonl`,
`sgs_v33_development_selection.jsonl` and `sgs_v33_summary.json`.

Source hashes: `sgs_v33.py`
`c4c49d79464f8f1a10f4dc85ab39aa3cee550939cccfc19cb944dc7f23ed15ed`;
`sgs_v33_driver.py`
`93600b85d9d85f4af47dfbcdeafad54086c9cd573aa23174db1620eb94278c9b`.
