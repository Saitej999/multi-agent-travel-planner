"""A focused travel planning UI over the existing demo and five-agent workflow."""

import asyncio
from datetime import date, timedelta
from inspect import signature

import streamlit as st
from pydantic import ValidationError

from travel_core.geo import GeographicDataError, search_cities
from travel_core.planner import plan_trip
from travel_core.schemas import TripRequest
from travel_ui import (render_budget, render_diagnostics, render_hero, render_itinerary,
                       render_map, render_overview, render_recommendations)


st.set_page_config(page_title='Multi-Agent Travel Planner', page_icon='🧳', layout='wide')


@st.cache_data(ttl=3600, show_spinner=False)
def city_candidates(name: str) -> list[dict]:
    return [city.model_dump() for city in search_cities(name)]


def display_plan(result: dict, kind: str) -> dict:
    if kind == 'offline':
        return result
    facts = result['structured_plan']
    global_mode = facts['request'].get('global_mode', False)
    return {
        'status': 'ok', 'request': facts['request'], 'flight': facts['flight'],
        'hotel': facts['hotel'], 'itinerary': {'itinerary': facts['itinerary']},
        'initial_budget': (facts['original_plan'] or {}).get('budget'),
        'budget': facts['budget'], 'replanning': facts['replanning'],
        'flights': {'options': result.get('available_flights') or []},
        'hotels': {'options': result.get('available_hotels') or []},
        'global_mode': global_mode,
    }


with st.sidebar:
    st.markdown('### Your planning space')
    mode = st.radio('Planning mode', ['AI Travel Planner', 'Offline Demo'],
                    help='AI uses the local five-agent ADK workflow. Demo is deterministic Python.')
    diagnostics = st.toggle('Developer diagnostics', value=False)
    st.caption('Local learning project · No bookings or live travel prices')

if st.session_state.get('_last_mode') != mode:
    st.session_state.pop('execution', None)
    st.session_state['_last_mode'] = mode

render_hero()
st.info('Flight and hotel sample prices are **simulated and non-bookable**. Global routes have no live offers; any entered allowances are your estimates.')

if mode == 'Offline Demo':
    origin = st.selectbox('Flying from', ['Chicago'])
    destination = st.selectbox('Travel destination',
                               ['New York City', 'San Francisco', 'Tokyo'])
    origin_location = destination_location = None
    global_mode = False
else:
    place_cols = st.columns(2)
    origin = place_cols[0].text_input('Flying from', value='Chicago', key='origin_text',
                                      placeholder='City or city, country')
    destination = place_cols[1].text_input('Travel destination', value='New York City',
                                           key='destination_text',
                                           placeholder='City or city, country')
    sample_route = (origin.strip().casefold() == 'chicago' and
                    destination.strip().casefold() in
                    {'new york city', 'san francisco', 'tokyo'})
    global_mode = not sample_route
    origin_location = destination_location = None
    if global_mode:
        st.caption('For global planning, verify both cities. Attractions come from OpenStreetMap; fares and hotel rates are unavailable.')
        if st.button('Find matching cities'):
            try:
                st.session_state['city_matches'] = {
                    'origin_query': origin.strip(), 'destination_query': destination.strip(),
                    'origin': city_candidates(origin.strip()),
                    'destination': city_candidates(destination.strip()),
                }
            except GeographicDataError as exc:
                st.session_state.pop('city_matches', None)
                st.error(f'Could not verify cities: {exc}')
        matches = st.session_state.get('city_matches') or {}
        if (matches.get('origin_query') == origin.strip() and
                matches.get('destination_query') == destination.strip()):
            from travel_core.geo import ResolvedLocation
            for key, label in [('origin', 'Choose origin city'),
                               ('destination', 'Choose destination city')]:
                choices = [ResolvedLocation.model_validate(item) for item in matches[key]]
                if choices:
                    chosen = st.selectbox(label, choices, format_func=lambda item: item.label,
                                          key=f'{key}_choice')
                    if key == 'origin':
                        origin_location = chosen
                    else:
                        destination_location = chosen
                else:
                    st.warning(f'No matching {key} city found. Try a more specific name.')

st.subheader('Shape your trip')
with st.form('trip_form'):
    left, middle, right = st.columns(3)
    with left:
        departure = st.date_input('Departure', value=date.today() + timedelta(days=45))
        return_date = st.date_input('Return', value=date.today() + timedelta(days=49))
        travelers = st.number_input('Travelers', min_value=1, max_value=8, value=2)
    with middle:
        rooms = st.number_input('Rooms', min_value=1, max_value=8, value=1)
        budget = st.number_input('Total budget (USD)', min_value=1, value=2000, step=100)
        pace = st.selectbox('Travel pace', ['Balanced', 'Relaxed', 'Adventurous'])
    with right:
        interests = st.multiselect('Interests',
                                   ['culture', 'food', 'outdoors', 'entertainment'],
                                   default=['culture', 'food'])
        preferences = st.text_input('Other preferences', placeholder='Art, gardens, easy walks')
    flight_allowance = hotel_allowance = None
    if mode == 'AI Travel Planner' and global_mode:
        with st.expander('Optional costs you already know'):
            cost_cols = st.columns(2)
            flight_allowance = cost_cols[0].number_input(
                'Group round-trip flight allowance (USD)', min_value=0.0, value=0.0,
                help='Your own estimate for all travelers. Zero means unknown.')
            hotel_allowance = cost_cols[1].number_input(
                'Whole-stay hotel allowance (USD)', min_value=0.0, value=0.0,
                help='Your own estimate for all rooms and nights. Zero means unknown.')
    submit = st.form_submit_button('Create my travel plan', use_container_width=True)

if submit:
    if mode == 'AI Travel Planner' and global_mode and not (origin_location and destination_location):
        st.error('Choose verified origin and destination cities before creating a global plan.')
    else:
        try:
            request = TripRequest(
                origin=origin_location.label if origin_location else origin,
                destination=destination_location.label if destination_location else destination,
                origin_location=origin_location, destination_location=destination_location,
                global_mode=global_mode,
                departure_date=departure, return_date=return_date,
                travelers=int(travelers), rooms=int(rooms), budget_limit_usd=float(budget),
                interests=','.join(interests), preferences=preferences, travel_pace=pace,
                flight_allowance_usd=flight_allowance or None,
                hotel_allowance_usd=hotel_allowance or None,
            )
        except ValidationError as exc:
            st.error('; '.join(error['msg'] for error in exc.errors()))
        else:
            if mode == 'Offline Demo':
                st.session_state['execution'] = ('offline', plan_trip(request))
            else:
                status = st.status('Planning with local AI agents…', expanded=True)
                with status:
                    progress = st.empty()
                    progress_errors = []

                    def on_progress(event):
                        try:
                            names = {'flight_agent': 'Checking flights',
                                     'hotel_agent': 'Checking stays',
                                     'itinerary_agent': 'Planning your days',
                                     'budget_agent': 'Calculating your budget',
                                     'travel_coordinator': 'Assembling your plan'}
                            progress.write(names.get(event['agent'], 'Planning your trip'))
                        except Exception as exc:
                            progress_errors.append(f'{type(exc).__name__}: {exc}')

                    try:
                        from travel_planner.runner import run_adk_trip
                        runner_args = {'timeout_seconds': 180}
                        if 'on_progress' in signature(run_adk_trip).parameters:
                            runner_args['on_progress'] = on_progress
                        result = asyncio.run(run_adk_trip(request, **runner_args))
                    except Exception as exc:
                        if isinstance(exc, TimeoutError) or 'exceeded 180 seconds' in str(exc):
                            user_message = 'The local AI planner took too long. Try again or use Offline Demo.'
                        elif isinstance(exc, TypeError):
                            user_message = 'The AI planner could not start. Restart Streamlit and try again.'
                        else:
                            user_message = 'The AI workflow stopped before producing a complete plan. Try again or use Offline Demo.'
                        st.session_state['execution'] = ('error', {
                            'message': f'{type(exc).__name__}: {exc}',
                            'user_message': user_message,
                            'trace': getattr(exc, 'trace', []),
                            'timings': getattr(exc, 'timings', {}),
                            'model_metrics': getattr(exc, 'model_metrics', []),
                            'tool_metrics': getattr(exc, 'tool_metrics', []),
                            'total_seconds': getattr(exc, 'total_seconds', None),
                            'progress_errors': progress_errors,
                        })
                        status.update(label='Planning stopped', state='error')
                    else:
                        result['progress_errors'] = progress_errors
                        st.session_state['execution'] = ('adk', result)
                        status.update(label='Your plan is ready', state='complete',
                                      expanded=False)

if 'execution' not in st.session_state:
    st.caption('Enter your trip details to begin.')
    st.stop()

kind, result = st.session_state['execution']
if kind == 'error':
    st.error(result['user_message'])
    if diagnostics:
        render_diagnostics(result)
    st.stop()

plan = display_plan(result, kind)
if plan['status'] != 'ok':
    st.error(plan.get('message', 'No travel plan could be created.'))
    if diagnostics:
        st.json(plan)
    st.stop()

st.caption('AI Agent Mode: observed ADK workflow with local Ollama.' if kind == 'adk'
           else 'Offline Demo: deterministic Python demonstration; no LLM agents ran.')
render_overview(plan['request'], plan['budget'])
render_budget(plan)
render_recommendations(plan)
render_itinerary(plan)
render_map(plan)
if diagnostics:
    render_diagnostics(result if kind == 'adk' else {'message': 'Offline Python pipeline', 'trace': plan.get('trace', [])})
