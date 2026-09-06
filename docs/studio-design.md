# Studio, the design contract

The contract behind `aquascope studio`, the Explorer's Study mode and the
`studio_*` MCP tools. [studio.md](studio.md) is the user's guide;
[solve-design.md](solve-design.md) is the contract of the layer underneath
(plans with gates, playbooks, the method registry), which Studio keeps.

## The one sentence

A crew of roles over one shared workspace does a complete study at a place,
with the data that exists there and the data the user brings, and reports it
the way an engineer would: the user agrees the brief and approves the
methodology, then the crew runs to the bundle.

```
 you ──► Consultant ──► Scout ──► Methodologist ──► you ──► Analysts ──► Critic ──► Author ──► bundle
        (the brief)   (inventory)  (the plan)     (approve)  (run, gates)  (review)  (report)
                                                                 ▲                              │
                                                                 └────────── follow-up ◄────────┘
```

## Why a crew and not a pipeline, and why no framework

The team behind `aquascope solve` is five names on a fixed pipeline: keyword
rules, a YAML tree, gates, templates, and at most three stateless model calls.
It proves that a plan can be shown first and checked at every step. It cannot
talk about the problem, cannot plan outside its seven trees, and produces
Markdown.

Studio keeps every property that made Solve honest (a registered function
behind every step, a gate on every step, a study the runner replays with no
model, the checks on the prose) and adds what Solve lacked: a conversation,
a methodology composed for the data at hand, figures and documents, and a
memory the study lives in.

No agent framework: the engine runs in the Explorer's Pyodide worker
(LangChain and LangGraph closed Pyodide support as won't-fix in June 2026,
langchain-ai/langchain#35881; CrewAI and AutoGen do not build for WASM),
free tiers cannot carry transcripts between roles, and a framework's tool
loop would sit between the numbers and the report. The roles are plain
functions; `examples/langgraph_team.py` and `examples/crewai_studio.py` map
them onto those frameworks for people who host the crew elsewhere.

## The workspace (`aquascope/studio/workspace.py`)

One serialisable object every role reads and writes:

| Field | Written by | What |
| --- | --- | --- |
| `brief` | Consultant | problem, decision, quantities, period, horizon, constraints, deliverables, kind, playbook, intake, assumptions, questions, ready, source |
| `inventory` | Scout | site, datasets (station, upload, reanalysis, catchment, donors, samples), the raw `assess_site` recon (the sufficiency table lives there), catchment, donors, notes |
| `study` | Methodologist | `Study.to_dict()`, version 3 |
| `run` | Analysts | ok, results per step with gates, stopped_at, stop_reason |
| `critique` | Critic | checks, issues, not_established |
| `report` | Author | title, answer, key_numbers, sections (id, title, text, figures, tables), not_established, references, footer |
| `artifacts` | Analysts, Author | figures, tables, documents, workbook, notebook, study, bundle: bytes with a name, a media type, a caption, a step |
| `messages` | everyone | the conversation, with a kind a face can render (text, questions, plan, report) |
| `events` | everyone | the timeline (`role, step, event, detail, at`) |
| `ledger` | Model | calls and tokens per role |
| `tables` | Coordinator | the user's uploads as CSV text, so they round-trip |
| `status` | Coordinator | intake, scouting, planning, review, running, critique, authoring, done, declined |

`to_dict` / `from_dict` (bytes as base64), `to_json` / `from_json`. The
browser holds the dict between worker calls, the CLI writes
`workspace.json`, MCP passes it in and out.

## The catalogue (`aquascope/studio/catalogue.py`)

Every step a plan may name, described once: id, what it is for, its kind
(site, station, frame, weather, recon, table, none), its argument schema
and required arguments, what its payload yields (series, annual_maxima, ffa,
fdc, trend, spi, spei, sgi, donors, signatures, climate, samples, wqi,
demand, reliability, catchment, ...), the registry methods it applies, the
gates that make sense on it, the figures and tables the makers draw from it,
a citation. Built from the Analyst's tool specs, `workbench.TOOLS`,
`assess_site` and the `load_table` step (a user's upload as a payload).

`compact(problem)` is the JSON the Methodologist reads. `callables(extra)`
is the dict the runner executes. `validate_step` and `validate_plan` are the
deterministic checks every model-written step passes: the tool exists, the
arguments are the tool's, required ones are present, references and
`depends_on` point backwards to known ids, every gate is in
`aquascope.gates.CHECKS`, a `method` is a registry id the tool applies and is
not marked not defensible at the site.

## Study version 3

The version-2 shape (steps with id, rationale, arguments, gates, fallback,
depends_on, method) plus, on the plan: `objective`, `decision`,
`methodology` (numbered sentences), `assumptions`, `alternatives` (considered
and why not), `limitations_expected`, `citations`, `author`
(`methodologist` or `playbook`); and on each step: `outputs`
(`[{kind: figure | table, id, caption}]`). `run_study` runs it as a
version-2 study; `aquascope run` replays it with no model.

## The roles

Each role is a module under `aquascope/studio/roles/` exposing one function
over the workspace. Each has a keyless behaviour; each uses the model, when
one is present, as stateless calls with compact JSON in and one JSON object
out (`aquascope.studio.model.Model.call_json`).

| Role | Keyless | With a model | Writes |
| --- | --- | --- | --- |
| Consultant | keyword rules (`team.choose_playbook`), intake hints, the playbook's intake fields as questions | the brief from the text, the site, the attached tables and a catalog-only recon; at most three questions in one round; "just go" proceeds on assumptions | `brief`, a `questions` message |
| Scout | `assess_site`, the ERA5 and GloFAS reach, uploads through `ingest` | the same (deterministic) | `inventory`, a `Dataset` per row |
| Methodologist | the playbook tree (`playbooks.plan`) | a version-3 study composed from the catalogue; `validate_plan`; one repair call with the errors; then the tree; then a decline with the errors | `study`, a `plan` message |
| Analysts | `run_study` with gates and the bounded replan of `team._execute`; figures per step as results land | the Specialist's fallback proposal after a failed gate, as in Solve | `run`, figure and table artifacts, events |
| Critic | `verify.verify` on the draft, the gates, the plan's notes | one independent pass over the draft sections and the compact results: issues with a section, a severity and a fix | `critique` |
| Author | template prose (`team._template_answer` and the sentence makers) | one call per report for the prose of every section, given the compact results, the critique and the caveats; the numbers come from the results | `report`, the documents, the workbook, the notebook, the bundle |
| Coordinator | the state machine, checkpoints, follow-ups | the same; a follow-up is classified by the Consultant as a question (answered from the workspace) or a change (steps appended, run, re-authored) | `status`, `follow_ups` |

Reading between the roles: compact JSON of exactly what the role needs
(`aquascope.studio.model.compact`), never the whole workspace, never a
transcript.

## The Coordinator's API (`aquascope.studio.Studio`)

```python
s = Studio(lat=..., lon=..., provider=..., model=..., api_key=..., base_url=..., client=...,
           data={"upload:flows.csv": df}, on_event=print)
r = s.say("Design flow for a road crossing, 100-year")   # -> the Consultant's reply (brief, questions or the plan)
r = s.say("200 years, and use the local gauge")            # answers; when the brief is ready the Scout and the
                                                            # Methodologist run and the plan comes back
r = s.approve(edits=None)                                   # runs Analysts, Critic, Author; returns the report
r = s.follow_up("redo it with a 500-year return period")   # a change: new steps, run, re-author
paths = s.export("out/")                                    # writes the bundle's files
ws = s.to_dict(); s2 = Studio.from_dict(ws)                 # checkpoint and resume anywhere
```

Every method returns a `Reply` (`kind`: questions, plan, report, answer,
declined; `text`; `payload`) and leaves the workspace consistent, so a face
can stop at any point and resume. The keyless path is the default: a model is
used only when one is asked for.

## The deliverables (`aquascope/studio/deliverables/`)

Pure Python so they run in the Pyodide worker; the plotting and document
libraries are imported inside the functions, never at module import.

| File | Makes | Needs |
| --- | --- | --- |
| `figures.py` | PNG and SVG per figure kind from the payload (series, annual_maxima, frequency_curve, fdc, trend, drought_strip, propagation, donors_map, signatures_band, monthly_climate, reliability_curve, demand_monthly, site_map, ...) with a caption | matplotlib |
| `workbook.py` | the Excel workbook: README, one sheet per dataset and result table, a figure index | openpyxl |
| `report_docx.py` | the Word report with figures and tables embedded | python-docx; skipped with a note when it cannot be imported |
| `report_md.py` | Markdown and HTML through `ReportBuilder` | nothing |
| `notebook.py` | the notebook that re-runs the study and redraws the figures, as plain JSON | nothing |
| `bundle.py` | the zip with everything, study.yaml, workspace.json, README.txt | nothing |

The report's sections, in this order: Summary (the answer, the key numbers
table), Problem and decision, Site and data (the inventory table, the site
map), Methodology (numbered, with the gates and the assumptions), Results
(one subsection per step with its figures and tables), Limitations and what
this study does not establish, Recommendations, References, Appendix
(reproducibility: the study, the commands, the ledger).

## The faces

- **CLI**: `aquascope studio "PROBLEM" --lat --lon [--data FILE ...] [--provider ...] [--out DIR] [--yes] [--resume workspace.json]`.
- **MCP**: `studio_start`, `studio_say`, `studio_approve`, `studio_follow_up`, `studio_export`, the workspace dict in and out.
- **Explorer**: the `studio` worker message (`op`: start, say, approve, follow_up, export) with the workspace dict in and out, `studio_progress` events, artifact events carrying PNG bytes as base64; matplotlib with `loadPackage`, openpyxl and python-docx with micropip, only when a study runs.

## The honesty rules, kept

Every number in the report comes from a tool result and passes the gates
and the checks before it is quoted; what fails is listed under "what this
study does not establish". A method the registry calls not defensible at the
site is refused at plan time. The playbooks' caveats are printed verbatim
when a playbook applies. The study replays with no model. The ledger is in
the report's footer.
