"""Run the ordered ADK workflow and expose its actual tool events."""

import asyncio
from time import perf_counter
from uuid import uuid4

from travel_core.config import model_name
from travel_core.schemas import TripRequest
from travel_planner.coordination import DEMO_DISCLAIMER

REQUIRED_SPECIALISTS = {'flight_agent', 'hotel_agent', 'itinerary_agent', 'budget_agent'}
REQUIRED_PYTHON_TOOLS = {'search_flights', 'search_hotels', 'suggest_activities', 'estimate_budget'}
AGENT_ORDER = ('flight_agent', 'hotel_agent', 'itinerary_agent', 'budget_agent', 'travel_coordinator')


class WorkflowRunError(RuntimeError):
    """A failed local run with the ADK events observed before it stopped."""

    def __init__(self, message: str, trace: list[dict], timings: dict,
                 model_metrics: list | None = None, tool_metrics: list | None = None,
                 total_seconds: float | None = None):
        super().__init__(message)
        self.trace = trace
        self.timings = timings
        self.model_metrics = model_metrics or []
        self.tool_metrics = tool_metrics or []
        self.total_seconds = total_seconds


def agent_execution_summary(trace: list[dict], timings: dict) -> list[dict]:
    """Report observed tool activity; prose alone never counts as execution."""
    summary = []
    for name in AGENT_ORDER:
        calls = [item['tool'] for item in trace if item['agent'] == name and item['event'] == 'tool_call']
        responses = [item['tool'] for item in trace if item['agent'] == name and item['event'] == 'tool_result']
        final_seen = any(item['agent'] == name and item['event'] == 'final_response' for item in trace)
        summary.append({'agent': name, 'tool_calls': ', '.join(calls) or '—',
                        'tool_results': ', '.join(responses) or '—',
                        'elapsed_seconds': timings.get(name),
                        'observed': bool(calls or responses or final_seen),
                        'status': ('final response observed' if final_seen else
                                   'tool result observed' if responses else
                                   'tool call observed' if calls else 'no event observed')})
    return summary


def missing_specialist_calls(trace: list[dict]) -> set[str]:
    """Identify specialist AgentTool calls absent from a complete-trip run."""
    called = {item['tool'] for item in trace
              if item['event'] == 'tool_call' and item['agent'] == 'travel_coordinator'}
    return REQUIRED_SPECIALISTS - called


def make_prompt(request: TripRequest) -> str:
    return request.model_dump_json()


def missing_workflow_tools(trace: list[dict]) -> set[str]:
    """Check calls, not mentions in the final prose."""
    called = {item['tool'] for item in trace if item['event'] == 'tool_call'}
    return REQUIRED_PYTHON_TOOLS - called


async def run_adk_trip(request: TripRequest, timeout_seconds: float = 180,
                       on_progress=None) -> dict:
    """Run the actual sequential agents with a validated request in session state."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from travel_planner.agent import root_agent

    candidates = []
    discovery_status = 'not_applicable'
    discovery_sources = []
    discovery_warnings = []
    discovery_diagnostics = []
    if request.global_mode:
        from travel_core.geo import find_attractions

        if not request.destination_location or not request.origin_location:
            raise WorkflowRunError('Choose verified origin and destination cities first.', [], {})
        days = (request.return_date - request.departure_date).days + 1
        desired_places = 2 + max(0, days - 2) * (3 if request.travel_pace == 'Adventurous' else 2)
        discovery = await asyncio.to_thread(find_attractions, request.destination_location,
                                            desired_places)
        candidates = [item.model_dump() for item in discovery.attractions]
        discovery_status = discovery.status
        discovery_sources = discovery.sources
        discovery_warnings = discovery.warnings
        discovery_diagnostics = discovery.diagnostics or []
        if on_progress:
            on_progress({'agent': 'itinerary_agent', 'event': 'attractions_found' if candidates else 'attractions_unavailable',
                         'count': len(candidates)})

    app_name = 'travel_planner'
    user_id = 'streamlit_demo_user'
    session_id = uuid4().hex
    sessions = InMemorySessionService()
    await sessions.create_session(app_name=app_name, user_id=user_id, session_id=session_id,
                                  state={'trip_request': request.model_dump(mode='json'),
                                         'attraction_candidates': candidates,
                                         'attraction_discovery': {'status': discovery_status,
                                                                  'sources': discovery_sources,
                                                                  'warnings': discovery_warnings,
                                                                  'diagnostics': discovery_diagnostics}})
    runner = Runner(agent=root_agent, app_name=app_name, session_service=sessions)
    content = types.Content(role='user', parts=[types.Part(text=make_prompt(request))])
    trace = []
    timings = {}
    answer = ''
    started = perf_counter()
    stage = AGENT_ORDER[0]
    stage_started = started
    last_event_at = started
    async def partial_metrics():
        try:
            partial = await sessions.get_session(app_name=app_name, user_id=user_id,
                                                 session_id=session_id)
            return (partial.state.get('model_metrics') or [], partial.state.get('tool_metrics') or [])
        except Exception:
            return ([], [])

    try:
        async with asyncio.timeout(timeout_seconds):
            async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
                now = perf_counter()
                if event.author in AGENT_ORDER and event.author != stage:
                    timings[stage] = round(last_event_at - stage_started, 2)
                    stage = event.author
                    stage_started = last_event_at
                last_event_at = now
                for call in event.get_function_calls():
                    deterministic = event.author in {'flight_agent', 'hotel_agent', 'budget_agent'}
                    trace.append({'agent': event.author, 'event': 'tool_call', 'tool': call.name,
                                  'details': str(call.args)[:600],
                                  'argument_source': ('deterministic Python stage' if deterministic
                                                      else 'Gemini proposal; callback grounds trip facts')})
                for result in event.get_function_responses():
                    trace.append({'agent': event.author, 'event': 'tool_result', 'tool': result.name,
                                  'details': str(result.response)[:600]})
                    if on_progress:
                        on_progress({'agent': event.author, 'event': 'tool_result',
                                     'tool': result.name})
                if event.author == 'travel_coordinator' and event.is_final_response() and event.content:
                    answer = '\n'.join(part.text for part in (event.content.parts or []) if part.text)
                    trace.append({'agent': event.author, 'event': 'final_response',
                                  'tool': '—', 'details': answer[:600]})
                    if on_progress:
                        on_progress({'agent': event.author, 'event': 'final_response'})
                delta = getattr(getattr(event, 'actions', None), 'state_delta', None) or {}
                budget_finished = (event.author == 'budget_agent' and
                                   ('revised_plan' in delta or
                                    (request.global_mode and 'plan_facts' in delta) or
                                    delta.get('budget_result', {}).get('within_budget') is True))
                if event.author == stage and (event.is_final_response() or budget_finished):
                    timings[stage] = round(now - stage_started, 2)
                    index = AGENT_ORDER.index(stage)
                    if index + 1 < len(AGENT_ORDER):
                        stage = AGENT_ORDER[index + 1]
                        stage_started = now
    except TimeoutError as exc:
        timings[stage] = round(perf_counter() - stage_started, 2)
        model_metrics, tool_metrics = await partial_metrics()
        raise WorkflowRunError(f'Local AI run exceeded {timeout_seconds:g} seconds.', trace, timings,
                               model_metrics, tool_metrics, round(perf_counter() - started, 2)) from exc
    except Exception as exc:
        timings[stage] = round(perf_counter() - stage_started, 2)
        model_metrics, tool_metrics = await partial_metrics()
        raise WorkflowRunError(f'Local AI run stopped: {type(exc).__name__}: {exc}', trace, timings,
                               model_metrics, tool_metrics, round(perf_counter() - started, 2)) from exc
    timings.setdefault(stage, round(last_event_at - stage_started, 2))

    session = await sessions.get_session(app_name=app_name, user_id=user_id, session_id=session_id)
    state = session.state
    if state.get('workflow_error'):
        raise WorkflowRunError(f"Travel workflow stopped: {state['workflow_error']}", trace, timings)
    required = ({'search_flights', 'search_hotels', 'suggest_activities', 'partial_budget'}
                if request.global_mode else REQUIRED_PYTHON_TOOLS)
    missing = required - {item['tool'] for item in trace if item['event'] == 'tool_call'}
    if missing:
        raise WorkflowRunError('The sequential workflow did not execute Python tools: '
                               + ', '.join(sorted(missing)), trace, timings)
    expected_budget_status = 'partial' if request.global_mode else 'ok'
    if state.get('budget_result', {}).get('status') != expected_budget_status:
        raise WorkflowRunError('The Budget Agent did not produce a valid Python calculation.', trace, timings)
    answer = answer or state.get('final_plan_text', '')
    if not answer or not state.get('plan_facts'):
        raise WorkflowRunError('The Travel Coordinator produced no final plan.', trace, timings)
    if not request.global_mode and DEMO_DISCLAIMER not in answer:
        raise WorkflowRunError('The final plan omitted the simulated, non-bookable data label.', trace, timings)
    if not request.global_mode:
        for selected in (state['selected_flight'], state['selected_hotel']):
            if selected['id'] not in answer:
                raise WorkflowRunError(f"The final plan omitted selected option {selected['id']}.", trace, timings)
    summary = agent_execution_summary(trace, timings)
    for row in summary:
        if row['agent'] == 'flight_agent':
            row['selected_result'] = (state['selected_flight']['id'] if state.get('selected_flight')
                                      else 'No live offer')
        elif row['agent'] == 'hotel_agent':
            row['selected_result'] = (state['selected_hotel']['id'] if state.get('selected_hotel')
                                      else 'No live offer')
        elif row['agent'] == 'itinerary_agent':
            row['selected_result'] = f"{len((state.get('itinerary_result') or {}).get('itinerary', []))} activity days"
        elif row['agent'] == 'budget_agent':
            total = state['budget_result'].get('estimated_total_usd')
            row['selected_result'] = (f'${total:,.2f} final total' if total is not None
                                      else 'Partial estimate calculated')
        else:
            row['selected_result'] = 'final plan'
    return {'answer': answer, 'trace': trace, 'structured_plan': state['plan_facts'],
            'available_flights': (state.get('flight_search') or {}).get('options', []),
            'available_hotels': (state.get('hotel_search') or {}).get('options', []),
            'attractions': candidates,
            'attraction_discovery': {'status': discovery_status,
                                     'sources': discovery_sources,
                                     'warnings': discovery_warnings,
                                     'diagnostics': discovery_diagnostics},
            'timings': timings, 'agent_summary': summary,
            'model_metrics': state.get('model_metrics') or [],
            'tool_metrics': state.get('tool_metrics') or [],
            'total_seconds': round(perf_counter() - started, 2),
            'model': model_name(), 'execution_mode': 'GOOGLE_ADK_SEQUENTIAL_AGENTS'}
