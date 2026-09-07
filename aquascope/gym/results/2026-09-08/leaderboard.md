## HydroGym plan-quality leaderboard

25 cases, 75 runs, 3 agent-model pairs. Score is the mean over every case of the plan-quality score (weights tools 0.3, methods 0.25, gates 0.2, clean 0.15, parsimony 0.1; a declining case scores 1 for a decline and 0 for a plan; an error scores 0); solvable is the mean over the cases the reference does not decline, off-tree over the cases no single playbook branch covers; spread is the range of the per-run means when a model was played more than once; declined is the share of declining cases the agent refused; false declines are solvable cases it refused; tools, methods and gates are the mean coverage of the reference's required tools, methods and gates; extraneous is the mean share of a plan's steps the reference does not name; forbidden is the share of plans that use a tool or method not defensible at the site; valid first try is the share of model plans the validator accepted at once; tree fallback is the share of plans that are the tree's because the model's did not pass.

| agent | model | cases (solvable + decline) | score | solvable | off-tree | spread | declined | false declines | tools | methods | gates | extraneous | forbidden | valid first try | tree fallback | tokens/case | s/case | cost USD | errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| methodologist | claude-haiku-4-5 | 25 (18 + 7) | 0.93 | 0.90 | 0.89 | - | 100 % | 6 % | 100 % | 91 % | 98 % | 6 % | 11 % | 92 % | 0 % | 8,339 | 21.7 | 0.420 | 0 |
| methodologist | claude-sonnet-5 | 25 (18 + 7) | 0.96 | 0.94 | 0.98 | - | 100 % | 6 % | 100 % | 98 % | 100 % | 1 % | 0 % | 96 % | 0 % | 10,151 | 24.4 | 1.017 | 0 |
| tree | none | 25 (18 + 7) | 0.97 | 0.95 | 0.73 | - | 100 % | 0 % | 94 % | 94 % | 93 % | 0 % | 0 % | 100 % | 0 % | 0 | 0.0 | 0.000 | 0 |

Mean score by playbook:

| agent | model | drought_status | flood_risk | groundwater_decline | irrigation_feasibility | supply_reliability | ungauged_flow | water_quality |
|---|---|---|---|---|---|---|---|---|
| methodologist | claude-haiku-4-5 | 1.00 | 0.97 | 0.67 | 0.95 | 0.98 | 0.78 | 1.00 |
| methodologist | claude-sonnet-5 | 0.98 | 1.00 | 0.67 | 1.00 | 0.99 | 1.00 | 1.00 |
| tree | none | 0.93 | 0.93 | 1.00 | 0.94 | 1.00 | 1.00 | 1.00 |

Cost is estimated from the tokens the provider reported and a small table of list prices (aquascope.gym.bench.PRICES_USD_PER_MTOK, mid-2026); prices change, cache and batch discounts are not modelled, and a model not in the table gets no estimate.
