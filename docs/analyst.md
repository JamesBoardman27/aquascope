# The Analyst: `aquascope ask` and `aquascope ingest`

Two commands where a language model does the part hydrologists spend hours on
and aquascope does the part that has to be right.

## `aquascope ask`: a question in, a cited report out

```bash
pip install aquascope             # the openai SDK is optional (pip install "aquascope[llm]")
export GROQ_API_KEY=...            # or OPENAI_API_KEY, HF_TOKEN, MISTRAL_API_KEY, OPENROUTER_API_KEY, or AQUASCOPE_LLM_API_KEY + _BASE_URL + _MODEL
aquascope ask "What is the 100-year flood of the Seine at Paris, and how sure can we be?" -o seine.md
```

The model gets the same tools the [MCP server](mcp.md) exposes (`find_stations`,
`analyze_station`, `flood_frequency`, `get_timeseries`, `anywhere`,
`list_sources`, `describe_methods`) and decides which to call; aquascope runs
them against real data. The Markdown report has three parts:

1. the model's answer (told to quote units, periods, stations and confidence
   intervals, and never to invent numbers);
2. **Data**: every station or point the tools touched, with period, licence and
   attribution, assembled from the tool results;
3. **Methods and citations**: the methods actually applied, with references,
   also assembled from the tool results (never from the model's memory).

A footer records the model, provider, date and the tools called. `--provider`
picks openai / groq / huggingface / ollama (defaults from the environment),
`--model` overrides the default model, `--max-steps` bounds the tool loop.
Works with any OpenAI-compatible endpoint that supports tool calling.

This is deliberately not an autonomous agent: no memory, no planning beyond
the tool loop, no writes. It is the "ask, get the work done, see the work"
surface from the direction review, and its numbers are exactly what
`aquascope analyze`/the Explorer would give you.

The same function runs inside the [Explorer](explorer.md) (the **Ask ✨**
button): the browser worker calls the provider directly with your key through
`aquascope.ai_engine.llm_transport.UrllibChatClient`, a dependency-free
OpenAI-compatible client that is also the fallback when the `openai` package
is not installed, so `pip install aquascope` alone is enough for `aquascope
ask`. Providers: `openai`, `groq`, `huggingface`, `mistral`, `openrouter`,
`ollama`, or `AQUASCOPE_LLM_BASE_URL` for anything else that speaks the
protocol.

## `aquascope ingest`: any export in, a clean series and a QA report out

```bash
aquascope ingest nwis_export.txt --unit cfs
aquascope ingest pegel.csv --variable water_level --date-column Datum --value-column "Pegel [cm]" --unit cm
aquascope ingest agency.xlsx --sheet 2 --llm --describe "monthly discharge in l/s from the regional office"
```

What happens:

- the file is read with the usual agency quirks handled (comment lines,
  `;`/tab delimiters, Excel sheets, JSON);
- the mapping (date column, value column, variable, unit and SI factor,
  station column) is guessed by heuristics, or proposed by an LLM when `--llm`
  is set and validated by the heuristics; anything you pass on the command
  line wins;
- the mapping is applied deterministically: sentinel values (-9999 and friends)
  are dropped *before* unit conversion, duplicates are dropped, timestamps are
  normalised;
- the QA report counts what was dropped, flags negatives and spikes (robust
  sigma), lists gaps over 30 days, computes coverage per year, and warns when
  the record is too holey for statistics;
- the cleaned series gets `aquascope.explore.analyze_series` (flood frequency
  when there are 10+ complete years, FDC, trend);
- outputs: `<stem>.csv` (`date,value` in SI units), `<stem>.qa.json`
  (mapping + QA), `<stem>.qa.md` (the human-readable report).

Nothing in `ingest` needs a key or a network connection unless you ask for
`--llm`.
