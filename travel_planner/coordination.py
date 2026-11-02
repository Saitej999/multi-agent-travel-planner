"""Session-state handoffs for the ordered ADK travel workflow."""

import json
import re
from time import perf_counter

from pydantic import ValidationError

from travel_core.schemas import TripRequest
from travel_core.tools import suggest_activities

_PREREQUISITES = ('flight_agent', 'hotel_agent', 'itinerary_agent')


def guard_budget_call(tool, args, tool_context):
    """Defer budget work until prior specialist results and concrete IDs exist."""
    if tool.name != 'budget_agent':
        return None
    missing = [name for name in _PREREQUISITES
               if not tool_context.state.get(f'travel_planner.completed.{name}')]
    request = str(args.get('request', ''))
    has_ids = re.search(r'\bDEMO-F\d+\b', request) and re.search(r'\bDEMO-H\d+\b', request)
    if missing or not has_ids:
        return {'status': 'missing_inputs',
                'message': 'Wait for flight, hotel, and itinerary results, then retry budget_agent '
                           'with returned DEMO-F and DEMO-H IDs, nights, traveler and room counts, '
                           'and per-person activity cost.',
                'missing_specialists': missing}
    return None


def record_specialist_result(tool, args, tool_context, tool_response):
    """Track completed specialist calls in this ADK session."""
    failed = (isinstance(tool_response, dict)
              and tool_response.get('status') in {'tool_error', 'invalid_request', 'no_results',
                                                  'unsupported_route', 'unsupported_destination'})
    if tool.name in _PREREQUISITES and tool_response is not None and not failed:
        tool_context.state[f'travel_planner.completed.{tool.name}'] = True
    return None


def report_tool_error(tool, args, tool_context, error):
    """Give the calling agent a clear failure result instead of a fabricated offer."""
    _record_tool_timing(tool.name, tool_context, 'error', args)
    return {'status': 'tool_error', 'tool': tool.name,
            'message': f'{tool.name} could not complete. Explain the failure and do not invent results.',
            'error_type': type(error).__name__}


def _message(text: str):
    from google.genai import types

    return types.Content(role='model', parts=[types.Part(text=text)])


def _record_tool_timing(name, tool_context, status, args=None):
    started = (tool_context.state.get('_tool_started_at') or {}).get(name)
    if started is None:
        return
    metrics = list(tool_context.state.get('tool_metrics') or [])
    used = dict(args or {})
    if used.get('candidate_data_json'):
        used['candidate_data_json'] = '[verified attraction candidates from session state]'
    metrics.append({'tool': name, 'status': status,
                    'duration_seconds': round(perf_counter() - started, 4),
                    'used_arguments': used})
    tool_context.state['tool_metrics'] = metrics


def record_model_start(callback_context, llm_request):
    """Count real ADK model requests and their prompt size without logging content."""
    name = callback_context.agent_name
    starts = dict(callback_context.state.get('_model_started_at') or {})
    starts[name] = perf_counter()
    callback_context.state['_model_started_at'] = starts
    content_chars = sum(len(part.text or '') for content in llm_request.contents
                        for part in content.parts or [])
    try:
        request_chars = len(llm_request.model_dump_json(exclude_none=True))
    except AttributeError:
        request_chars = content_chars
    requests = list(callback_context.state.get('model_metrics') or [])
    requests.append({'agent': name, 'request_number': 1 + sum(x['agent'] == name for x in requests),
                     'prompt_contents': len(llm_request.contents), 'content_text_chars': content_chars,
                     'request_json_chars': request_chars,
                     'duration_seconds': None, 'status': 'started'})
    callback_context.state['model_metrics'] = requests
    return None


def record_model_response(callback_context, llm_response):
    name = callback_context.agent_name
    starts = callback_context.state.get('_model_started_at') or {}
    requests = list(callback_context.state.get('model_metrics') or [])
    for item in reversed(requests):
        if item['agent'] == name and item['status'] == 'started':
            item['duration_seconds'] = round(perf_counter() - starts[name], 2) if name in starts else None
            item['status'] = 'completed'
            break
    callback_context.state['model_metrics'] = requests
    return None


def record_model_error(callback_context, llm_request, error):
    record_model_response(callback_context, None)
    requests = list(callback_context.state.get('model_metrics') or [])
    for item in reversed(requests):
        if item['agent'] == callback_context.agent_name:
            item['status'] = type(error).__name__
            break
    callback_context.state['model_metrics'] = requests
    return None


def record_coordinator_response(callback_context, llm_response):
    record_model_response(callback_context, llm_response)
    return ensure_demo_disclaimer(callback_context, llm_response)


def prepare_request(callback_context):
    """Accept validated runner state or a JSON TripRequest pasted into ADK Web."""
    raw = callback_context.state.get('trip_request')
    if callback_context.user_content:
        text = ''.join(part.text or '' for part in (callback_context.user_content.parts or []))
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = None
    for key in ('workflow_error', 'flight_search', 'selected_flight', 'hotel_search',
                'selected_hotel', 'hotel_nights', 'itinerary_result', 'free_itinerary_result',
                'itinerary_interests_used',
                'activities_per_person_usd', 'initial_budget_result', 'budget_result',
                'original_plan', 'revised_plan', 'replanning', 'plan_facts',
                'coordinator_facts',
                'final_plan_text', 'flight_agent_response', 'hotel_agent_response',
                'itinerary_agent_response', 'model_metrics', 'tool_metrics',
                '_model_started_at', '_tool_started_at'):
        callback_context.state[key] = None
    try:
        request = TripRequest.model_validate(raw)
    except ValidationError as exc:
        error = 'Provide a complete TripRequest JSON object: ' + '; '.join(
            item['msg'] for item in exc.errors())
        callback_context.state['workflow_error'] = error
        return _message(error)
    callback_context.state['trip_request'] = request.model_dump(mode='json')
    callback_context.state['budget_limit_usd'] = request.budget_limit_usd
    callback_context.state['food_per_person_per_day_usd'] = request.food_per_person_per_day_usd
    callback_context.state['transport_per_day_usd'] = request.transport_per_day_usd
    choices = callback_context.state.get('attraction_candidates') or []
    callback_context.state['attraction_choices'] = [
        {'id': item['id'], 'name': item['name'], 'category': item['category']}
        for item in choices[:24]
    ]
    return None


def skip_on_error(callback_context):
    """Skip downstream model calls when a prior stage failed."""
    error = callback_context.state.get('workflow_error')
    return _message(error) if error else None


def specialist_tool_args(tool, args, tool_context):
    """Ground tool arguments in the validated request, not model guesses."""
    request = TripRequest.model_validate(tool_context.state['trip_request'])
    if tool.name == 'search_flights':
        args.clear()
        args.update(origin=request.origin, destination=request.destination,
                    departure_date=request.departure_date.isoformat(),
                    return_date=request.return_date.isoformat(), travelers=request.travelers)
        if request.global_mode:
            args.update(global_mode=True, flight_allowance_usd=request.flight_allowance_usd)
    elif tool.name == 'search_hotels':
        args.clear()
        args.update(destination=request.destination,
                    check_in=request.departure_date.isoformat(),
                    check_out=request.return_date.isoformat(), rooms=request.rooms)
        if request.global_mode:
            args.update(global_mode=True, hotel_allowance_usd=request.hotel_allowance_usd)
    elif tool.name == 'suggest_activities':
        if request.global_mode:
            candidates = tool_context.state.get('attraction_candidates') or []
            valid_ids = {item['id'] for item in candidates}
            selected = [item.strip() for item in str(args.get('selected_attraction_ids', '')).split(',')
                        if item.strip() in valid_ids]
            args.clear()
            args.update(destination=request.destination,
                        days=(request.return_date - request.departure_date).days + 1,
                        interests=request.interests, free_only=False,
                        candidate_data_json=json.dumps(candidates, separators=(',', ':')),
                        selected_attraction_ids=','.join(selected), pace=request.travel_pace,
                        start_date=request.departure_date.isoformat())
            starts = dict(tool_context.state.get('_tool_started_at') or {})
            starts[tool.name] = perf_counter()
            tool_context.state['_tool_started_at'] = starts
            return None
        valid_tags = {'culture', 'food', 'outdoors', 'entertainment'}
        requested_tags = [tag.strip().lower() for tag in request.interests.split(',')
                          if tag.strip().lower() in valid_tags]
        model_tags = [tag.strip().lower() for tag in str(args.get('interests', '')).split(',')
                      if tag.strip().lower() in valid_tags]
        chosen = [tag for tag in model_tags if not requested_tags or tag in requested_tags]
        avoid_popular = args.get('avoid_popular_spots') is True or str(
            args.get('avoid_popular_spots', '')).lower() == 'true'
        args.clear()
        args.update(destination=request.destination,
                    days=(request.return_date - request.departure_date).days + 1,
                    interests=','.join(chosen or requested_tags), free_only=False,
                    avoid_popular_spots=avoid_popular)
    starts = dict(tool_context.state.get('_tool_started_at') or {})
    starts[tool.name] = perf_counter()
    tool_context.state['_tool_started_at'] = starts
    return None


def save_specialist_tool_result(tool, args, tool_context, tool_response):
    """Persist only successful, serializable Python tool responses."""
    if tool.name not in {'search_flights', 'search_hotels', 'suggest_activities'}:
        return None
    tool_context.actions.skip_summarization = True
    result = tool_response if isinstance(tool_response, dict) else {}
    _record_tool_timing(tool.name, tool_context, result.get('status', 'invalid_response'), args)
    request = TripRequest.model_validate(tool_context.state['trip_request'])
    if request.global_mode and tool.name in {'search_flights', 'search_hotels'}:
        if result.get('status') != 'unavailable':
            tool_context.state['workflow_error'] = f"{tool.name}: {result.get('message', 'provider failed')}"
        elif tool.name == 'search_flights':
            tool_context.state['flight_search'] = result
            tool_context.state['selected_flight'] = None
        else:
            tool_context.state['hotel_search'] = result
            tool_context.state['selected_hotel'] = None
            tool_context.state['hotel_nights'] = result['nights']
        return None
    if result.get('status') != 'ok' and not (
        request.global_mode and tool.name == 'suggest_activities'
        and result.get('status') in {'partial', 'insufficient_data'}
    ):
        tool_context.state['workflow_error'] = (
            f"{tool.name}: {result.get('message') or result.get('note') or result.get('errors') or 'no result'}")
        return None
    try:
        json.dumps(result)
        if tool.name == 'search_flights':
            options = result['options']
            selected = min(options, key=lambda item: (item['stops'], item['round_trip_usd_per_person']))
            tool_context.state['flight_search'] = result
            tool_context.state['selected_flight'] = selected
        elif tool.name == 'search_hotels':
            options = result['options']
            selected = next((item for item in options if item['category'] == 'midrange'), options[0])
            tool_context.state['hotel_search'] = result
            tool_context.state['selected_hotel'] = selected
            tool_context.state['hotel_nights'] = result['nights']
        else:
            tool_context.state['itinerary_result'] = result
            tool_context.state['itinerary_interests_used'] = args.get('interests', '')
            tool_context.state['activities_per_person_usd'] = result['estimated_activities_usd_per_person']
            if request.global_mode:
                return None
            request = TripRequest.model_validate(tool_context.state['trip_request'])
            free_result = suggest_activities(
                request.destination,
                days=(request.return_date - request.departure_date).days + 1,
                interests=args.get('interests', request.interests),
                free_only=True,
                avoid_popular_spots=args.get('avoid_popular_spots', False),
            )
            if free_result['status'] == 'ok':
                tool_context.state['free_itinerary_result'] = free_result
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        tool_context.state['workflow_error'] = f'{tool.name} returned incomplete data: {type(exc).__name__}'
    return None


DEMO_DISCLAIMER = 'DEMO DATA: Flight and hotel offers and prices are simulated, not live or bookable.'


def ensure_demo_disclaimer(callback_context, llm_response):
    """Keep essential verified lodging and simulation labels in the final plan."""
    from google.genai import types

    content = llm_response.content
    if not content or not content.parts:
        return None
    parts = list(content.parts)
    text = '\n'.join(part.text or '' for part in parts)
    if not text.strip():
        return None
    additions = []
    facts = getattr(callback_context, 'state', {}).get('plan_facts', {})
    if (facts.get('request') or {}).get('global_mode'):
        note = ('No live flight or hotel offers were checked. User travel allowances are estimates; '
                'admission prices are unknown, so the complete trip budget cannot be confirmed.')
        if note not in text:
            additions.append(note)
        if facts.get('attraction_status') == 'partial':
            partial_note = ('Some itinerary slots are general suggestions because verified attractions '
                            'were unavailable; no venue or price is confirmed for those slots.')
            if partial_note not in text:
                additions.append(partial_note)
        if not additions:
            return None
        parts.append(types.Part(text='\n\n' + '\n'.join(additions)))
        return llm_response.model_copy(update={'content': types.Content(role='model', parts=parts)})
    nights = facts.get('budget', {}).get('nights')
    if nights is not None and f'{nights} night' not in text.lower():
        additions.append(f'Lodging stay: {nights} nights.')
    replanning = facts.get('replanning') or {}
    if replanning.get('triggered'):
        original, revised = facts['original_plan'], facts['revised_plan']
        comparison = (
            f"Python budget comparison: original {original['flight']['id']} / "
            f"{original['hotel']['id']} ${original['budget']['estimated_total_usd']:,.2f}; "
            f"revised {revised['flight']['id']} / {revised['hotel']['id']} "
            f"${revised['budget']['estimated_total_usd']:,.2f}; "
            f"activities per person ${original['itinerary']['estimated_activities_usd_per_person']:,.2f} "
            f"to ${revised['itinerary']['estimated_activities_usd_per_person']:,.2f}; "
            f"saved ${replanning['amount_saved_usd']:,.2f}; "
            f"{'within budget' if revised['budget']['within_budget'] else 'over budget'}. "
            f"{replanning['explanation']}")
        if comparison not in text:
            additions.append(comparison)
    if DEMO_DISCLAIMER not in text:
        additions.append(DEMO_DISCLAIMER)
    if not additions:
        return None
    parts.append(types.Part(text='\n\n' + '\n'.join(additions)))
    return llm_response.model_copy(update={'content': types.Content(role='model', parts=parts)})
