# Plan quality after the engine fixes (2026-09-08)

The 2026-09-07 run found that with a model the Studio never declined an ill-posed brief (0 of 7 for both
models), that the table tools were hidden from the Methodologist without an upload, that the supply
screening's ungauged mode was unreachable, and that a model could name a station the site does not have.
All four were fixed in the engine (a playbook's own decline rule is honoured before any model is asked, a model
may reply with a decline, the analytic table tools are listed, the supply entry names its regional method, a
station must be in the inventory) and the two model rows were run again on the same 25 cases, one repeat each.

| agent | score | solvable | off-tree | declined (of 7) | false declines |
| --- | --- | --- | --- | --- | --- |
| tree | 0.97 | 0.95 | 0.73 | 100 % | 0 % |
| Claude Sonnet 5, before | 0.64 | 0.89 | 0.98 | 0 % | 0 % |
| Claude Sonnet 5, after | 0.96 | 0.94 | 0.98 | 100 % | 6 % |
| Claude Haiku 4.5, before | 0.66 | 0.92 | 0.96 | 0 % | 0 % |
| Claude Haiku 4.5, after | 0.93 | 0.90 | 0.89 | 100 % | 6 % |

What remains is judgement rather than plumbing. Sonnet declined one solvable case (`gw_regional_potomac`: no
well within reach, so it refused to say anything about the water table, where the reference and the playbook
take the ERA5 water balance for the cell and label it regional); that is a defensible position an engineer
might also take, and the reference keeps the regional answer because a labelled estimate beats silence for a
screening question. The groundwater kind is therefore the weakest for the model. The device-class row is still
pending a free small-model endpoint.

Costs at list prices: Sonnet 5 about 1.0 USD for the 25 cases (10k tokens a case), Haiku 4.5 less than half of
that. Files: the three JSONL result files, `leaderboard.md` (from `aquascope gym leaderboard`), this note.
