# Wayfinder: Multi-Agent Travel Planner

An educational travel-planning application with a React interface, a small FastAPI backend, and a five-stage Google ADK workflow. Gemini interprets travel interests and explains the plan; Python retrieves the available data, validates trip facts, and calculates every budget figure. The project runs locally, but **AI Agent Mode calls the Gemini API**. No Ollama, database, Docker, paid model, or booking service is required.

**Flight and hotel offers for the built-in sample routes are simulated and non-bookable.** Global routes can show optional Duffel developer test flight offers and source-backed OpenStreetMap hotel locations. Duffel sandbox prices are simulated and excluded from the budget; hotel prices and availability remain unknown unless the traveler supplies estimates. A partial estimate is never presented as a complete budget.

## Screenshots

![Completed Mumbai itinerary and map on desktop](docs/screenshots/mvp-mumbai-desktop.png)

The same completed result at [tablet](docs/screenshots/mvp-mumbai-tablet.png) and [mobile](docs/screenshots/mvp-mumbai-mobile.png) widths. These screenshots show a past live Gemini itinerary with traveler-entered cost estimates; they do not show verified flight fares or hotel prices.

## Features

- Search worldwide cities through Open-Meteo and choose a specific city, region, and country.
- Plan a 2–14 day trip with dates, optional destination-local arrival and departure times, travelers, rooms, budget, interests, pace, and preferences.
- See flights, hotels, a day-by-day itinerary, budget charts, and clickable map markers for verified places. Itinerary place names focus the map; the execution trace is optional.
- Add group flight, whole-stay or per-room-night hotel, and admission estimates after planning. Python updates the budget without another Gemini call.
- Explore named OpenStreetMap hotel properties on the map when the public provider responds. Hotel ratings, room prices, and availability are not claimed.
- Optionally search Duffel developer test flights with a backend-only test token. These offers are simulated and non-bookable in this application.
- Compare the initial and revised sample budgets using the existing Python optimizer.
- Follow real ADK progress through an in-memory FastAPI job. Technical details stay behind the Developer diagnostics panel.
- Use the preserved Streamlit **Offline Demo** without a key. Its output is a deterministic demonstration, not AI agent execution.

## Architecture

```mermaid
flowchart LR
    UI[React + TypeScript] --> API[FastAPI /api]
    API --> JOB[In-memory trip job]
    JOB --> ADK[Google ADK SequentialAgent]
    ADK --> F[Flight Search<br/>Python ADK agent]
    F --> H[Hotel Search<br/>Python ADK agent]
    H --> I[Itinerary Planning<br/>Gemini LlmAgent]
    I --> B[Budget Optimization<br/>Python ADK agent]
    B --> C[Travel Coordination<br/>Gemini LlmAgent]
    F --> DATA[Simulated catalog or Duffel test offers]
    H --> HOTEL[Simulated catalog or OSM hotel locations]
    I --> OSM[Verified places via Overpass or Wikipedia fallback]
    C --> OUT[Pydantic TripPlanResponse]
    OUT --> API
```

The five agents run in order and exchange **validated ADK session state**. Flight and Hotel stages execute their existing Python search tools every time and emit observed ADK tool events. The Itinerary Agent makes one Gemini request to select interest tags or verified attraction IDs, then calls `suggest_activities()`. Python grounds its tool arguments in the original request. The Budget Agent checks the returned data, calls `estimate_budget()` for sample routes or `partial_budget()` for global routes, and makes at most one optimization pass. The Coordinator makes one Gemini request to explain the structured facts. Its prose is separate from the typed response used by React; it never supplies prices to the budget calculator.

This workflow uses **two model requests** on a successful sample trip: Itinerary and Coordinator. The other stages are real ADK agents with deterministic Python behavior. It uses sequential orchestration and shared state, not `AgentTool` delegation. This is intentional: mandatory searches cannot be skipped by a model. The offline demo is a separate Python pipeline.

| Stage | Google ADK role | Responsibility |
|---|---|---|
| Flight | Deterministic Python agent | Runs the synthetic catalog or optional Duffel test search and records tool events. |
| Hotel | Deterministic Python agent | Runs the synthetic catalog or named OpenStreetMap property discovery. |
| Itinerary | Gemini `LlmAgent` | Interprets interests and selects grounded activity IDs; Python builds and validates the schedule. |
| Budget | Deterministic Python agent | Calculates costs, partial totals, and one possible sample-route optimization. |
| Coordinator | Gemini `LlmAgent` | Explains the validated plan and limitations without supplying financial arithmetic. |

## AI engineering concepts

The project demonstrates ADK sequential orchestration, typed shared state, observable Python tool calls, bounded LLM reasoning, Pydantic validation, grounded retrieval, deterministic financial calculations, failure reporting, and a generated OpenAPI-to-TypeScript contract. The event trace records calls that actually ran; a final answer mentioning an agent alone is not treated as proof of delegation.

## Technology

| Layer | Tools |
|---|---|
| Web | React 18, TypeScript, Vite, Tailwind CSS 4, shadcn/ui components, Lucide React, Recharts, MapLibre GL JS |
| API | FastAPI, Pydantic, in-memory asyncio jobs |
| Agents | Google ADK, Gemini API, existing Python search, itinerary, budget, and replanning tools |
| Geographic data | Open-Meteo Geocoding, OpenStreetMap via Overpass, Wikipedia geosearch, OpenFreeMap tiles |
| Optional flight sandbox | Duffel developer test mode; backend token only, no orders or payments |
| Tests | Pytest, Vitest, React Testing Library |

The map uses [OpenFreeMap's public style](https://openfreemap.org/) through MapLibre and keeps the built-in attribution control. Markers are shown only for coordinates returned by the geographic provider; synthetic demo activities have no map markers.

For global trips, Python ranks source-backed places by stated interests, category variety, and nearby daily grouping. It schedules only unique verified places, leaves unsupported periods empty, and treats the first and final days as provisional when travel times are unknown. It does not invent opening hours, admission prices, or live availability.

## External integrations

| Source | Used for | Limit |
|---|---|---|
| Gemini API | Itinerary selection and coordinator explanation | An API key and free-tier quota are required. |
| Open-Meteo Geocoding | City search and disambiguation | Public service may be unavailable. |
| OpenStreetMap Overpass | Named attractions and hotel locations | Public instances may time out; properties have no verified room inventory or price. |
| Wikipedia Geosearch | Source-backed attraction fallback | An article does not establish current access or opening hours. |
| Duffel Developer test mode | Optional simulated flight offers | Requires a backend test token; test fares are not live prices. |
| OpenFreeMap | Destination map tiles | Public tiles may fail; source links remain available. |

## Install and run

Use Python **3.11+** and Node.js **22.12+**. Commands below run from this repository directory in Windows PowerShell. Keep `travel_planner/.env` private; `.gitignore` excludes it.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example travel_planner\.env
```

Edit `travel_planner/.env` and set your own `GOOGLE_API_KEY`. The template sets `GOOGLE_GENAI_USE_VERTEXAI=FALSE` and `GEMINI_MODEL=gemini-3.1-flash-lite`. This model completed the live workflow with the configured key and has a [documented free tier and function calling](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite). You can set `GEMINI_MODEL` to another free-tier-compatible Gemini model available to your project. Gemini availability and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) vary by project. Do not enable billing for this learning project.

For optional sandbox flight search, create a token in **Duffel Developer test mode** and put `DUFFEL_TEST_TOKEN=duffel_test_...` in the same ignored `travel_planner/.env` file. The backend rejects tokens without the test prefix and never sends the token to React. [Duffel test mode](https://duffel.com/docs/api/overview/test-mode/duffel-airways) uses airline sandboxes with limited, sometimes unrealistic schedules and prices. This project only creates offer requests; it never creates orders or payments. Without the token, international flight search reports `missing_credentials` and the existing synthetic demo still works.

Start the backend in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to FastAPI. The API documentation is at `http://127.0.0.1:8000/docs` and `GET /api/health` shows the selected model and whether a key is configured, without revealing the key. Use **one backend process**: trip jobs live only in memory and disappear when it restarts.

The preserved Streamlit fallback is optional. From the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Choose **Offline Demo** to use only deterministic Python tools. For that mode alone, `requirements-demo.txt` can be installed in a separate virtual environment without Google ADK or a Gemini key. Streamlit's AI mode uses the same ADK/Gemini workflow as FastAPI.

## Example trip and result

Choose **Chicago, Illinois, United States → New York, New York, United States**, December 15–19, 2026, two travelers, one room, a $2,000 budget, and culture/food interests. The sample route yields five calendar days and four hotel nights:

| Estimate | Original | Optimized |
|---|---:|---:|
| Simulated round-trip flights | $660 | $660 |
| Simulated hotel stay | $920 | $640 |
| Food | $450 | $450 |
| Ground transport | $100 | $100 |
| Illustrative activities | $140 | $140 |
| **Total** | **$2,270** | **$1,990** |

The Python optimizer saves **$280** by selecting a cheaper returned sample hotel. The final estimate is $10 below the requested budget before taxes and fees. Flight and hotel names, offers, and prices are fictional; nothing can be booked from this app. The five daily activity suggestions are illustrative. See the [completed Gemini/ADK trace](docs/gemini-lite-live-check.json) for the exact calls and resulting plan.

For a global route such as Chicago → Rome, the city picker resolves a specific Rome, Italy record. Overpass or the Wikipedia geosearch fallback supplies named attractions and coordinates when available. OpenStreetMap can also return named hotel properties and coordinates, without room prices or availability. A configured Duffel test token can return simulated round-trip flight offers. Traveler-entered estimates can add to the known subtotal. Until flights, hotel, and admission all have estimates, the overall budget remains **partial**, without a within-budget verdict. Once they do, the UI shows an **estimate-based** comparison, never a verified quote.

## API and testing

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Backend status and model configuration |
| `GET /api/locations/search?q=Rome` | Up to five disambiguated city matches |
| `POST /api/trips/plan` | Validate input and start an ADK job |
| `GET /api/trips/{id}/status` | Queued/running/completed/failed and observed progress |
| `GET /api/trips/{id}/result` | Typed plan, pending status, or structured failure |
| `POST /api/trips/{id}/budget` | Recalculate a completed global trip using traveler estimates in Python; no agent rerun |

The frontend's TypeScript contract is generated from the FastAPI OpenAPI schema (`frontend/src/types/generated.ts`). After changing backend schemas, regenerate `frontend/src/types/openapi.json` from `backend.main.app.openapi()` and run `npm run types:generate` in `frontend`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run check
npm run test
npm run build
```

To inspect a bounded **live** sample run without the UI:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_workflow --budget 2000 --interests culture,food --timeout 75 --output docs\my-live-check.json
```

Automated tests use fake Gemini responses and mock external geography; they do not consume API quota. The HTTP-to-ADK integration test submits a trip job, runs all five ADK stages, checks observed tool events, and validates the structured API result. React tests exercise form submission, status polling, results, and hidden diagnostics.

## Verification and limitations

- A bounded live run with `gemini-3.1-flash-lite` completed in **34.19 seconds**. The trace records `search_flights`, `search_hotels`, `suggest_activities`, two `estimate_budget` calls, and the final Coordinator response. Its model metrics record one Itinerary and one Coordinator request. The optimized $1,990 total and $280 savings came from Python.
- A second live check went through Vite's `/api` proxy: Open-Meteo resolved Chicago and New York, FastAPI returned a completed job, and the typed result contained the same five-day/four-night budget regression and all observed ADK stages. See the [HTTP journey summary](docs/gemini-http-check.json).
- A live Chicago → Mumbai browser submission used the React form, Vite proxy, FastAPI, and Gemini/ADK. The observed trace includes all five stages and the four Python tools. Wikipedia geosearch supplied 24 candidates and the result scheduled eight unique places across five days. The rendered browser showed eight map markers. A real `/budget` request recalculated the result without agent calls; the completed result was then replayed in the browser to verify map focus, estimate updates, and desktop/tablet/mobile layouts without another Gemini call. See the screenshots above.
- The requested `gemini-2.5-flash` returned **404 unavailable to new users** for this key. `gemini-3.8-flash` returned a temporary **503 high demand**. The configurable default is the free-tier-compatible model that completed the live run. See [Gemini model availability and pricing](https://ai.google.dev/gemini-api/docs/pricing).
- Live Open-Meteo lookup resolved Rome, Italy. Both tested public Overpass instances timed out in this environment. The Wikipedia fallback did return source-backed Rome candidates, but **a complete live Rome ADK run is not verified**.
- Public geographic services can be slow or unavailable. The hotel adapter makes one bounded request to each of two public Overpass instances and returns an explicit unavailable state if both fail. Search results, OSM tags, attraction descriptions, and coordinates are not guarantees of admission, opening hours, accessibility, or current conditions. Arrival and departure days keep only one optional named visit because travel times are unknown.
- Duffel developer test offers are sandbox fixtures, not live airline fares or inventory. A missing test token, unmatched airport, unsupported route, authentication error, timeout, or non-USD response yields an unavailable state. OpenStreetMap hotel names and locations do not confirm that a property currently operates or has rooms available.
- Sample fares, lodging, activity costs, and food/transport allowances are teaching examples. Taxes and fees are excluded. No booking, live inventory, or guaranteed budget is provided.
- Jobs are local memory only; restarting the backend loses them. Google ADK currently warns that `SequentialAgent` is deprecated. The project keeps the existing five-stage architecture for clarity.
- The frontend production dependency audit is clear. One moderate `minimatch` advisory remains across three packages in the development-only `openapi-typescript` chain; it does not ship in the browser bundle. Regenerate types only from this project's trusted local OpenAPI schema.

## Repository guide

```text
frontend/                       React form, results, map, charts, tests, generated API types
backend/main.py                 FastAPI routes and in-memory jobs
travel_planner/agent.py         Five ADK stages
travel_planner/retrieval_agents.py Mandatory Python flight/hotel ADK stages
travel_planner/budget_agent.py   Python budget and optimization ADK stage
travel_planner/coordination.py   Validated shared-state handoffs and model callbacks
travel_planner/runner.py         Event trace, progress, timeout, and execution checks
travel_core/api_schemas.py       Typed HTTP request/response contract
travel_core/geo.py               Open-Meteo and Overpass clients
travel_core/global_planner.py    Verified-place itinerary and partial budget
travel_core/tools.py             Existing travel and budget tools
app.py                           Preserved Streamlit fallback
scripts/verify_workflow.py       Bounded live ADK verification
tests/                          Python unit and integration tests
```

## License

MIT. See [LICENSE](LICENSE). This educational application does not process bookings or payments.
