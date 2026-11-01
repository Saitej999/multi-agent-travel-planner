# Multi-Agent Travel Planner 🧳

A local, educational travel planning assistant built to show how Google ADK agents share verified tool results. It has a Streamlit interface, a repeatable Offline Demo, and an AI Agent Mode backed by Ollama. **Sample flight and hotel offers are simulated and non-bookable.** For other destinations, the app retrieves city matches from Open-Meteo and named attractions from OpenStreetMap via Overpass; it does not retrieve live fares, hotel rates, or admission prices.

## What it does

- Accepts an origin, destination, dates, travelers, rooms, budget, interest tags, travel pace, and optional preferences.
- Shows a selected sample flight and hotel when the route is in the built-in catalog, day-by-day activity ideas, a map, and an itemized trip estimate.
- For global cities in AI Agent Mode, requires verified city choices and uses named OpenStreetMap attractions. Morning, afternoon, and evening slots distinguish verified places from general suggestions.
- For global routes, flight and hotel offers are explicitly unavailable. Optional user-entered allowances contribute to a **partial** budget; unknown admission prices remain unknown, so no complete total or within-budget verdict is claimed.
- Makes one budget optimization pass if the first estimate is too high. It uses only options returned by the synthetic search tools and calculates costs in Python.
- Shows the original total, revised total, amount saved, and any remaining shortfall.
- Separates the deterministic demo from real local ADK agent execution. Developer diagnostics are hidden by default and reveal observed tool events, model requests, Python tool timing, agent duration, and partial evidence if a run stops.

## Architecture

```text
TripRequest (Pydantic)
        |
        +---- Demo Mode: plan_trip() -> Python search/budget tools -> result
        |
        +---- AI Agent Mode: Google ADK SequentialAgent (root_agent)
                     |
                     +-- Flight LlmAgent ---- search_flights() ---- flight_search
                     +-- Hotel LlmAgent ----- search_hotels() ----- hotel_search
                     +-- Itinerary LlmAgent - suggest_activities() - itinerary_result
                     |                        free itinerary prepared in Python callback
                     +-- Budget BaseAgent --- estimate_budget()/partial_budget()
                     |                        one deterministic optimization pass
                     +-- Coordinator LlmAgent -------------- final explanation
                              ^
                         ADK session state carries verified results
```

The three specialist LLM agents call Python tools; their callbacks save structured responses in ADK session state. The Budget Agent validates the returned IDs and trip details, computes the first total, and evaluates returned flight, hotel, and activity combinations only if needed. The Coordinator presents those facts. ADK runs the five stages in order, so the Budget Agent receives the specialist results before calculating. The Offline Demo uses the same synthetic catalog and budget tool but **does not run AI agents**. The ADK implementation no longer uses `AgentTool` delegation; its collaboration is the ordered workflow and shared state.

For global trips, the application resolves both cities with [Open-Meteo geocoding](https://open-meteo.com/en/docs/geocoding-api) and fetches named nearby places from [OpenStreetMap through Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API). The same Flight, Hotel, Itinerary, Budget, and Coordinator stages run. Flight and Hotel stages return explicit `unavailable` results; the Budget Agent calculates only known and user-provided amounts. If either public geographic service is unavailable or returns no usable attractions, the global run stops with a clear error. These public services require internet access, while the sample Offline Demo does not.

Specialists skip an extra model summary after their tool response. Each LLM agent uses ADK's [`include_contents='none'`](https://google.github.io/adk-docs/agents/llm-agents/) because its validated input comes from session state; prior agents' tool responses need not be resent as conversation history. The Coordinator receives a compact view of verified facts while the full plan stays in state for the app. The Budget Agent's arithmetic and optimization add no LLM call. The intended complete workflow uses four model requests: one per LLM specialist and one for the Coordinator.

In AI Agent Mode, the Itinerary Agent may prioritize valid interest tags and set a popular-spot filter from the request. Python grounds the destination and dates and constructs activities from the existing catalog. The filter is an illustrative catalog label, **not live crowd information**. The Coordinator explains the selections; Python alone calculates prices and optimizes the budget.
The ADK `tool_call` event shows the model's proposed arguments; callbacks replace trip facts such as dates, traveler count, and itinerary day count before executing Python. For example, November 15–19 is five calendar days and four hotel nights even if the model proposes another `days` value. The tool-timing table records the arguments actually used.

**Stack:** Python 3.11+, Google ADK, Ollama, LiteLLM, Streamlit, Pydantic, Pytest, Open-Meteo, and OpenStreetMap/Overpass. There is no database, booking API, or paid model API.

## Install and run

Run these commands from this repository directory. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
python -m streamlit run app.py
```

Open the local address Streamlit prints (normally `http://localhost:8501`). Choose **Offline Demo** for an immediate, repeatable result. AI Travel Planner is the default and requires Ollama. For Offline Demo alone, `requirements-demo.txt` supplies Streamlit, Pydantic, and the test dependencies without Google ADK or Ollama:

```powershell
python -m pip install -r requirements-demo.txt
python -m streamlit run app.py
```

### AI Agent Mode with Ollama

Install [Ollama](https://ollama.com/download), start its local server, and pull a chat model. For example:

```powershell
ollama pull llama3.2:3b
ollama list
# Run "ollama serve" if the desktop app has not started it.
Copy-Item .env.example travel_planner\.env
```

Edit the ignored `travel_planner/.env` to match a model shown by `ollama list`:

```dotenv
MODEL=ollama_chat/llama3.2:3b
OLLAMA_API_BASE=http://localhost:11434
LITELLM_LOCAL_MODEL_COST_MAP=True
```

The template defaults to `qwen3:8b`; the currently configured local model may differ. Choose **AI Travel Planner**, then generate a plan. Each AI run has a 180-second limit. Turn on **Developer diagnostics** in the sidebar to inspect observed calls and timing. A final answer alone is never treated as proof that every tool ran.

For a command-line ADK check with a configurable limit:

```powershell
python -m scripts.verify_workflow --budget 2000 --timeout 180
python -m scripts.verify_workflow --budget 2000 --interests outdoors --preferences "Active outdoor walks and sightseeing" --timeout 180
```

To inspect events in ADK Web, run `adk web --no-reload --port 8000`, select `travel_planner`, and paste a complete `TripRequest` JSON object. ADK Web does not use the Streamlit form.

## Example

Enter Chicago → New York City, **November 15–19, 2026**, **2 travelers**, **1 room**, a **$2,000** total budget, and interests **food, culture, outdoors**. The current synthetic tools produce:

| | Initial plan | Optimized plan |
|---|---:|---:|
| Round-trip flight | DEMO-F001, $660 | DEMO-F001, $660 |
| Hotel, 4 nights | DEMO-H002, $920 | DEMO-H001, $640 |
| Food / transport / activities | $450 / $100 / $140 | $450 / $100 / $140 |
| **Total** | **$2,270** | **$1,990** |
| Difference from limit | $270 short | $10 remaining |

The plan saves **$280** by changing the hotel. If no valid combination fits, the app shows the cheapest returned combination and its shortfall. Flight and hotel offers are fictional samples, and attraction costs and locations are illustrative.

For a global example, enter **Chicago → Rome**, choose the city matches, and select November 15–19 for two travelers. If geographic services respond, the app can place named OpenStreetMap attractions across five days. It will show four hotel nights and a known food and ground transport subtotal of **$550** at the default daily allowances ($45 × 2 × 5 + $20 × 5). Flight, hotel, and admission costs remain unknown until you supply your own flight and whole-stay hotel allowances; even then, admission remains unknown and the app does not state a complete total.

## Verification and limits

`python -m pytest -q` currently passes **75 tests** covering schemas, tool results, shared-state handoffs, budget arithmetic, replanning, geographic data parsing, runner evidence, and both Streamlit display paths. `python -m scripts.demo_pipeline` runs the deterministic pipeline without Ollama. The AI verification script records actual ADK function calls and responses; on timeout it reports the partial trace instead of claiming success.

### Measured local execution

The installed model was `llama3.2:3b`; `qwen3:8b` was not installed. The slow stage was LLM inference: a diagnostic run measured Flight and Hotel model requests at **37.7** and **42.2 seconds**, while their Python search functions each took less than **0.001 seconds**. Before the context reduction, runs timed out at 100–180 seconds. One earlier partial trace reached Flight and Hotel; a later one reached Budget but waited for the Coordinator. Old stage timing included the next agent's wait, so model-request timings are the more precise comparison.

After reducing repeated context and Coordinator input, two bounded live runs completed:

| Scenario | Total | Flight | Hotel | Itinerary | Budget | Coordinator | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| Food, culture, outdoors | 89.7 s | 17.3 s | 10.3 s | 7.8 s | <0.1 s | 53.5 s | $2,270 → $1,990 |
| Active outdoor preference | 150.3 s | 33.8 s | 30.6 s | 33.0 s | <0.1 s | 52.4 s | $2,130 → $2,000 |

Both traces show `search_flights`, `search_hotels`, `suggest_activities`, initial and revised `estimate_budget` calls and responses, and a final Coordinator response. The model made **four requests** in each run. See the [baseline AI trace](docs/optimized-ai-run.json) and [outdoor AI trace](docs/outdoor-preferences-ai-run.json). The different outdoor itinerary confirms preference handling in a real ADK run, although the small catalog repeats its two outdoor New York activities across five days. Model speed varies substantially even with identical orchestration; `llama3.2:3b` can complete this demo but is not guaranteed to finish inside 180 seconds on every machine.

The new global destination path is covered by mocked geographic-service and Streamlit tests. It has **not** completed a live Ollama run in this environment. A single 45-second check of the configured `ollama_chat/llama3.2:3b` timed out before a Python tool event, and this environment rejected a direct public geocoding request with a socket permission error. Run the global flow on a machine with Ollama and access to the public geographic endpoints before claiming end-to-end verification for that path.
The baseline trace was captured before the final Coordinator wording change; its raw answer contains an incorrect sentence about excluded fees. The structured Python budget in that trace excludes those fees, and the later outdoor answer follows the corrected instruction. Review the structured plan and tool events as the source of truth.

The synthetic offer catalog covers Chicago departures to New York City, San Francisco, and Tokyo. Other city pairs can use the global AI path when the public geographic services are reachable. There is no live inventory, booking, flight or hotel provider API, verified attraction schedule, crowd forecast, or guaranteed travel price. Hotel check-in follows the requested departure date; confirm actual arrival dates when using a real itinerary. Per-agent times are approximate wall-clock stages inferred from ADK events. Google ADK currently warns that `SequentialAgent` is deprecated in favor of `Workflow`; this project retains the requested five-stage architecture.

## Repository guide

```text
app.py                         Streamlit interface and two execution modes
travel_ui.py                   Reusable traveler-facing Streamlit result views
travel_planner/agent.py        Five ADK agents in a SequentialAgent
travel_planner/coordination.py Validated request and shared-state callbacks
travel_planner/budget_agent.py Python budget stage
travel_planner/runner.py       Bounded ADK execution, events, timings
travel_core/tools.py          Synthetic travel and budget tools
travel_core/geo.py            Bounded Open-Meteo and Overpass clients
travel_core/global_planner.py Verified-place itinerary and partial budget
travel_core/replanning.py     One-pass ADK plan optimizer
travel_core/planner.py        Deterministic Demo Mode pipeline
travel_core/schemas.py        Pydantic request and tool schemas
scripts/verify_workflow.py    Command-line live ADK check
tests/                        Unit and interface tests
```
