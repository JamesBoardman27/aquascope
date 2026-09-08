# HydroGym Phase 2, 2026-09-07: what the Methodologist gets right and wrong

Twenty-five reference plans on seven real sites (`aquascope/gym/plans/`),
the playbook tree and the Studio Methodologist on Claude Sonnet 5 and Claude
Haiku 4.5, two repeats each, played on 2026-09-07 from the saved
reconnaissance (no network but the model call), 300 s per case, no errors
and no timeouts. The rows are in `plans-*.jsonl`, the table in
`leaderboard.md`, the cases with their reconnaissance in `deposit/`.

| agent | model | score (25) | solvable (18) | off-tree (3) | spread of 2 runs | declined (7) | tools | methods | gates | extraneous | forbidden | valid first try | tokens/case | s/case | cost USD |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tree | none | 0.97 | 0.95 | 0.73 | - | 7 / 7 | 94 % | 94 % | 93 % | 0 % | 0 % | - | 0 | 0.0 | 0 |
| methodologist | claude-sonnet-5 | 0.64 | 0.89 | 0.98 | 0.63 to 0.66 | 0 / 7 | 87 % | 90 % | 85 % | 8 % | 0 % | 92 % | 14,073 | 52.8 | 3.58 |
| methodologist | claude-haiku-4-5 | 0.66 | 0.92 | 0.96 | 0.66 to 0.67 | 0 / 7 | 95 % | 87 % | 94 % | 8 % | 6 % | 86 % | 10,580 | 33.7 | 1.18 |

Per case (the score of each repeat):

| case | tree | Sonnet 5 | Haiku 4.5 |
|---|---|---|---|
| `flood_at_site_potomac` | 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| `flood_short_record_fish_creek` | 1.00 | 1.00 / 1.00 | 0.92 / 0.92 |
| `flood_regional_nevada` | 1.00 | 1.00 / 1.00 | 0.57 / 1.00 |
| `flood_inundation_declined_potomac` | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `ungauged_at_gauge_oregon` | 1.00 | 1.00 / 1.00 | 1.00 / 0.98 |
| `ungauged_regional_nevada` | 1.00 | 1.00 / 1.00 | 0.75 / 1.00 |
| `gw_well_tetbury` | 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| `gw_regional_potomac` | 1.00 | 0.28 / 0.25 | 0.95 / 0.24 |
| `gw_cause_declined_tetbury` | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `drought_gauge_tetbury` | 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| `drought_reanalysis_snake_plain` | 0.95 | 1.00 / 1.00 | 0.92 / 1.00 |
| `drought_flash_declined_tetbury` | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `supply_gauged_vegre` | 1.00 | 1.00 / 1.00 | 0.96 / 0.97 |
| `supply_regional_nevada` | 1.00 | 0.83 / 0.83 | 0.58 / 0.64 |
| `supply_storage_declined_vegre` | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `irrigation_with_gauge_snake_plain` | 1.00 | 0.98 / 0.98 | 1.00 / 1.00 |
| `irrigation_demand_only_nevada` | 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| `irrigation_schedule_declined_snake_plain` | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `wq_drinking_potomac` | 1.00 | 0.30 / 0.38 | 1.00 / 1.00 |
| `wq_irrigation_snake_plain` | 1.00 | 1.00 / 0.30 | 1.00 / 1.00 |
| `wq_no_samples_declined_tetbury` | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `wq_health_verdict_declined_potomac` | 1.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| `offtree_atsite_vs_regional_potomac` | 0.65 | 1.00 / 1.00 | 0.88 / 0.99 |
| `offtree_supply_crop_vegre` | 0.77 | 0.97 / 1.00 | 1.00 / 1.00 |
| `offtree_drought_well_river_tetbury` | 0.78 | 1.00 / 0.94 | 1.00 / 0.92 |

## What the tree does

The tree scores 1.00 on the 22 cases a playbook branch covers, by
construction (the references start from the branches), and 0.65, 0.77 and
0.78 on the three off-tree briefs: it cannot add the donor transfer next to
the at-site fit for a comparison, the gauge's own record to a crop-supply
question, or the borehole's trend to a drought question that asks whether
the water table is lower than it used to be. Its 0.95 on the reanalysis
drought case is the low-flow context it makes optional where the brief
asks for it. The tree declines all seven declining cases. That is the bar:
0.97 with no model, and the model's job is the last three points and the
briefs beyond the branches.

## What the Methodologist gets right

**The off-tree briefs.** This is where a model earns its place, and both
do: Sonnet 0.98 and Haiku 0.96 on the three cases against the tree's 0.73.
On the comparison case both add `similar_basins` and
`regionalize_signatures` as steps of their own next to the trend test and
the two-distribution fit (Sonnet 1.00 twice; Haiku 0.88 then 0.99, the
first time without the `method` labels the registry gates on). On the
crop-supply question both put the crop demand first and add the gauge's
flow-duration curve as a step in its own right before the screening. On the
drought question that names the well and the river both add the borehole's
Sen's slope and make the propagation and the low-flow context required
(Sonnet 1.00 then 0.94, Haiku 1.00 then 0.92; the second run of each left
out the trend).

**The on-tree solvable cases.** Sonnet reproduces the reference on 11 of
the 15 and is within 0.02 on one more; Haiku on 8, within 0.08 on five
more. The plans are the tree's with the gates the tree carries, and the
extras are mostly harmless (a GloFAS cross-check, a catchment description).
On `gw_well_tetbury` both take the SGI through `drought_propagation` at the
borehole rather than a fetched series and the table tool, a route the
catalogue offers and the reference accepts as an alternative.

**The validator.** 92 percent of Sonnet's plans and 86 percent of Haiku's
pass the Studio's validator at the first attempt, and every one of the
rest passes after the one repair call; no plan fell back to the tree. The
first-try errors are invented arguments (`variable` on `low_flow_context`,
`water_quality_samples` and `flood_frequency`, `k` on `supply_reliability`,
`max_points`, `log_transform` on `analyze_station`) and, for Haiku, methods
the registry refuses at a point with no record (`at_site_flood_frequency`,
`flow_duration`, `supply_reliability` at the Nevada point).

## What it gets wrong

**1. It never declines.** Zero of seven declining cases, both models, both
repeats. The inundation map got an at-site flood fit (five steps); the
question "is it the abstraction upstream" got the trend, the baseflow and
the SGI (five to seven steps); the flash drought got the monthly chain; the
reservoir got the run-of-river screening; the daily schedule got the
seasonal demand; the safe-to-drink verdict got the samples fetched; and at
Tetbury, where no station within 50 km carries water quality, both models
planned `water_quality_samples` at a station that has none, a plan that
fails at run time. The cause is in the Studio, not the models: with a model
the Methodologist passes the tree's decline to the model as the exemplar
(`{"playbook": ..., "declined": "<the sentence>"}`) but the prompt does not
offer a decline as a reply, and `plan()` declines only when the model's plan
fails validation *and* the tree declines. In Phase 1 the plan-first team
declined every probe before any model call because it runs the tree first;
the Studio's Methodologist with a model does not. Seven of 25 cases score
zero for this one behaviour, 28 points of the overall score, and the fix is
small: return the tree's decline when the tree declines (or let the model
reply `{"decline": "..."}` and have the Coordinator honour it).

**2. Sonnet cannot reach the water-quality index.** 0.30 and 0.38 on the
drinking case, 1.00 then 0.30 on the irrigation case. The catalogue the
Methodologist reads drops the table tools (`who_screen`, `wqi`, `iwqi`,
kind `frame`) when the client attached no table, although the
water_quality playbook's own steps use them on the fetched samples
(`from_step`). Sonnet follows "only tools from the catalogue given" and
plans the samples fetch plus a `get_timeseries` of the flow; Haiku copies
the exemplar's `wqi` step and scores 1.00 four times. The fix is in
`aquascope.studio.catalogue`/the Methodologist's `_catalogue_for`: list the
frame tools the problem's playbook uses (or whose methods serve the
problem) even without an upload.

**3. A discharge trend is not a groundwater signal.** On
`gw_regional_potomac` (no well in the catalog within 50 km) Sonnet scores
0.28 and 0.25 and Haiku 0.95 then 0.24: the plans run Mann-Kendall on the
Potomac's discharge, twice in the same plan, and fetch a level series,
instead of the ERA5 water balance for the cell that the reference and the
tree put first (Haiku's first run kept it). The brief asks about the water
table; the river's trend says nothing about it, and the report would have
to say so.

**4. The regional supply branch is unreachable.** `supply_regional_nevada`:
Sonnet 0.83 twice, Haiku 0.58 and 0.64. The playbook's regional branch
names `supply_reliability` with method `regionalize_signatures` (the
tool's ungauged mode); the catalogue lists only `supply_reliability` for
that tool, so the Methodologist rewrites the method, the registry refuses
it ("no discharge record at this site") and the step is pruned. Sonnet
keeps the catchment, the donors and the transferred signatures (0.83, the
reliability itself missing); Haiku, in one run, invents station steps
(`analyze_station`, `get_timeseries`) at a point with no station. The
Studio cannot plan a branch its own tree produces; `catalogue.py` should
list `regionalize_signatures` on the `supply_reliability` entry.

**5. Haiku invents stations.** 6 percent of its solvable plans use a
forbidden tool: `flood_frequency` and `analyze_station` at the Nevada
point on the flood case (0.57), station tools at the same point on the
supply case. The validator checks the tool's arguments, not whether the
station exists in the inventory; a check that a `source`/`station_id` pair
is in the inventory would catch every one of these. Sonnet used no
forbidden tool in 36 plans.

**6. Extraneous steps and missing labels.** Eight percent of both models'
steps are ones the reference does not name: a `get_timeseries` no later
step uses (nine times across both models), a second Mann-Kendall on the
same record, and, twice for Sonnet, `water_quality_samples` added to an
irrigation demand question because the gauge lists water quality. Haiku
often leaves the `method` off `similar_basins` (the short-record and the
comparison cases), which the registry needs to gate the step and the scorer
counts as a missing method.

**7. Cost and length.** Sonnet spends 14,100 tokens and 53 s per case
(4,300 completion tokens per plan, long rationales and alternatives), 3.58
USD for 50 runs; Haiku 10,600 tokens and 34 s, 1.18 USD. The whole Phase 2
run cost 4.76 USD at the list prices in the price table (2 and 10 USD per
million for Sonnet 5, 1 and 5 for Haiku 4.5); at 3 and 15 for Sonnet it
would be 6.55 USD. The plan-quality difference between the two models is
within the repeat spread on the solvable cases (Haiku 0.92, Sonnet 0.89);
Haiku's forbidden tools and missing labels are the price of the cheaper
model, Sonnet's water-quality miss is the price of following the catalogue
too well.

## What the numbers do not say

The references are one hydrologist's judgement encoded over the registry's
preconditions and the playbooks' branches; a different expert would draw
some lines elsewhere (whether the climate frame is a step, whether the SGI
by either route is the same step). Three revisions were made after the
first pass of the runs, when the plans showed a route the catalogue
legitimately offers: the SGI through `drought_propagation` as an
alternative, `low_flow_frequency` as the primary method on
`low_flow_context` (the catalogue lists it; the Studio rewrites the
playbook's `flow_duration` to it) with the others as alternatives, and the
`anywhere` climate frame optional on the irrigation cases (the crop-demand
tool computes the ET0 itself). The stored plans were re-scored
(`aquascope gym plans rescore`); the models were not run again; before the
revisions the means were Sonnet 0.60 and Haiku 0.62.

The Methodologist is given the playbook and the intake as the case states
them (the Consultant's job in the Studio), so the classification of the
brief is not measured here. Two repeats put the spread of the means at
0.03 (Sonnet) and 0.01 (Haiku); per case it is larger (Haiku's
`gw_regional_potomac` 0.95 then 0.24, Sonnet's `wq_irrigation_snake_plain`
1.00 then 0.30). The playbooks' data-driven decline (fewer than three
donors at an ungauged point) cannot arise at any real site because the
donor pool is the whole archive, so the declining cases are the intake
rules and the water-quality rule. The Heytesbury A36 gauge (8.3 years)
was captured and left out: a 53-year gauge sits 300 m away, which the
reconnaissance does not see because it takes the nearest station's span
per variable, so the expert plan (the at-site fit on the neighbour) is one
the Studio's validator refuses; that is a reconnaissance limitation worth
its own issue. No key for Groq or Hugging Face was in the environment, so
the small-model row is pending; the `file` agent scores a plan produced
anywhere from its JSON, and `--agent methodologist --provider groq` or
`huggingface` runs the role on those endpoints when a key is set.
