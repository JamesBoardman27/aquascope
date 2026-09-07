# Studio: a complete study at a place

`aquascope studio` puts a crew of roles over one shared workspace and runs a
hydrological study the way an engineer would: the brief is agreed with you,
the methodology is shown and approved before anything runs, every step
passes a gate, the report says what it does not establish, and the study
file re-runs with no model. [studio-design.md](studio-design.md) is the
contract; this page is the user's guide.

```
 you ──► Consultant ──► Scout ──► Methodologist ──► you ──► Analysts ──► Critic ──► Author ──► bundle
        (the brief)   (inventory)  (the plan)     (approve)  (run, gates)  (review)  (report)
```

## The flow

1. **Brief.** You say the problem in plain language. The Consultant writes
   the brief: the decision, the quantities wanted, the playbook it maps to,
   the intake fields it can read off the text. At most three questions come
   back when something the analysis cannot proceed without is missing; say
   `just go` to proceed on the defaults.
2. **Inventory.** The Scout lists what exists: the gauges within reach with
   their record spans, the catchment, the donor pool, the ERA5 cell (any
   point on land), and every table you attached, run through the ingest
   mapping and QA.
3. **Plan.** The Methodologist writes a version-3 study: objective,
   methodology in numbered sentences, steps with arguments, a registry
   method, gates and fallbacks, expected figures and tables. Keyless it is
   the playbook tree's plan; with a model it is composed from the catalogue
   and validated (the tool exists, the arguments are its own, the gates are
   known, a method the registry calls not defensible here is refused).
4. **Review.** The plan is a numbered checklist. Approve it, edit a step
   (`s3.return_period=200`) or change the brief ("make it a 200-year return
   period") and get a new plan.
5. **Run.** The Analysts run the steps in order with their gates; a failed
   gate runs the fallback once, or the plan is replanned once (the playbook's
   branch, or a Specialist's proposal validated against the catalogue).
   Figures and tables are made per step as results land.
6. **Report.** The Author writes the report from the results; the Critic
   checks it (every number must be in a result; a return level carries its
   interval; the record is named) and lists what is not established. With a
   model the Critic's `fix` issues earn one rewrite.
7. **Bundle.** Markdown, `study.yaml`, `report.json`, `workspace.json` and,
   when the deliverables package is installed, the figures, the Excel
   workbook, the Word report, the notebook and one zip.
8. **Follow-up.** A question is answered from the workspace; a change (another
   return period, another statistic) is planned, run and re-authored, reusing
   every step whose arguments and gates did not change.

## The tiers

| Tier | What runs | What you get |
| --- | --- | --- |
| Keyless (default) | keyword rules, the playbook tree, gates, template prose, the deterministic checks | a complete study with zero model calls |
| With a model | the same, plus one stateless call per role: the brief, a composed methodology, the Specialist's fallback, the Critic's issues, the Author's prose | the same bundle, with prose and a plan beyond the seven trees |

A model is used only when asked for (`--provider`, `--model`, `--api-key`,
`--base-url`, or a ready client). The ledger of calls and tokens per role is
in the report's footer.

## CLI

```bash
aquascope studio "Design flow for a road crossing, 100-year return period" --lat 51.415 --lon -0.308
```

Interactive in a terminal: the questions, `Run this plan? [y/N/e]` (`e` to
type overrides), the timeline as it happens, then a follow-up loop until
`done`. Non-interactive:

```bash
aquascope studio "Is this area in drought now?" --lat 24.15 --lon 120.68 --yes --out out/taichung
aquascope studio "..." --lat ... --lon ... --data flows.csv --intake return_period=200 --provider anthropic
aquascope studio --resume out/taichung/workspace.json --yes
```

`--yes` answers the defaults, approves and exports. `--data FILE` attaches a
table (CSV, Excel, JSON) as `upload:<name>`; a plan may load it with
`load_table` and analyse it with the workbench tools. `--resume` continues
a saved workspace from wherever it stopped.

## Python

```python
from aquascope.studio import Studio

s = Studio(lat=51.415, lon=-0.308, data={"flows.csv": df}, on_event=print)
r = s.say("Design flow for a road crossing, 100-year return period")   # -> questions or the plan
if r.kind == "questions":
    r = s.say("just go")
r = s.approve()                          # -> the report
r = s.follow_up("how sure can we be?")   # -> an answer from the workspace
r = s.follow_up("redo it with a 50-year return period")   # -> a new report
paths = s.export("out/")
ws = s.to_dict(); s2 = Studio.from_dict(ws)    # checkpoint and resume anywhere
```

Every method returns a `Reply` with `kind` (`questions`, `plan`, `report`,
`answer`, `declined`), `text` and `payload`. The roles are plain functions
under `aquascope.studio.roles` (`consult`, `scout`, `plan`, `run`,
`critique`, `author_report`), each over the workspace, for anyone who wants
to drive them from another orchestrator; `examples/langgraph_team.py
--studio` and `examples/crewai_studio.py` show two.

## MCP

`studio_start(problem, lat, lon, intake=None, ...)`, `studio_say(workspace,
text)`, `studio_approve(workspace, edits=None)`, `studio_follow_up(workspace,
text)`, `studio_export(workspace, out_dir)`. The tools are stateless: each
returns the reply, a summary and the workspace dict to pass to the next.

## In the Explorer

**Study** is the second mode of the Explorer's drawer, next to Ask. Open it
with **Study this place** on a gauge or on a point (a bare point works: the
Scout finds what is in reach), or with the Study button at the top right.
Everything runs in the page: the crew is `aquascope.studio` in the Pyodide
worker, the same Coordinator the CLI and the MCP tools drive.

The drawer is a conversation and a board. The conversation is the workspace's
messages: what you said, what the Consultant asked, what the crew wrote. The
board above the input shows one thing at a time:

1. **Intake**: the place, the model line, and what to bring. Drop a CSV or an
   XLSX, or attach the table already open in My data. Type the problem and
   send. When the Consultant asks something, the options are chips (one click
   answers) and **Just go** proceeds on the defaults.
2. **Review**: the plan as a card: the objective, the numbered steps with
   their arguments in words, the gates as chips, the rationale on expand.
   **Approve** runs it; **Edit** opens the arguments inline and sends them as
   the Methodologist's edits, revalidated in the worker (a refused edit says
   why and keeps the plan); **Decline** keeps the input open for a change of
   brief, or start again.
3. **Running**: the timeline as it happens, one line per event, and the
   figures as they are drawn. **Stop** abandons the run.
4. **Done**: the answer, the key numbers, the figures, what the study does
   not establish when the Critic listed anything, **Download bundle** (the
   zip) and links for the Word, Excel, Markdown, notebook and `study.yaml`
   files. The input stays open: a question is answered from the workspace, a
   change ("redo it with a 200-year return period") is planned, run and
   re-authored, and the board refreshes. **New study** clears the board for
   another study at the same place.

The tiers are Ask's. Keyless by default, which is a complete study: the
playbook tree plans, the gates check, templates write. When Ask holds a key,
one line offers it for the prose and the composed methodology. When Chrome's
built-in model is already on the device, or Ask has loaded a small model in
this tab, it reads the first sentence into a brief (the decision, the
quantities, a return period or drought timescales when stated) before the
Consultant sees it; nothing is downloaded for that, and a wrong reading costs
one question, never a wrong number.

The bytes stay in the worker. The page holds the workspace without the
artifact data; a figure travels as a PNG when it is drawn, a document only
when you ask for it, the bundle when you download it. matplotlib is loaded
before the first run and the document libraries before the first bundle,
once per visit, and never on a visit that runs no study. Nothing is uploaded
anywhere: the tables you attach are read in your tab and travel inside the
workspace as CSV text.

## The honesty rules

- Every number in the report comes from a tool result and passes the gates
  and the checks before it is quoted; what fails is listed under "what this
  study does not establish".
- A method the registry calls not defensible at the site is refused at plan
  time, whoever wrote the plan.
- The playbook's caveats are printed verbatim when a playbook applies.
- The study replays with no model: `aquascope run study.yaml`.
- The ledger (calls and tokens per role) is in the report's footer, and the
  plan says who wrote it (`playbook` or `methodologist`).
