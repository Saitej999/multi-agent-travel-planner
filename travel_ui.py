"""Small reusable Streamlit views for verified travel results."""

from math import isfinite

import pandas as pd
import streamlit as st


def money(value) -> str:
    """Format a known USD amount; never turn an unknown cost into zero."""
    if value is None:
        return 'Not available'
    amount = float(value)
    if not isfinite(amount):
        raise ValueError('Currency amount must be finite')
    return f'${amount:,.2f}'


def render_hero() -> None:
    st.markdown('''
    <style>
      .travel-hero {background: linear-gradient(115deg,#103f54,#116b73 58%,#198a81);
        color:#fff; border-radius:22px; padding:2.1rem 2.4rem; margin:0 0 1.5rem 0;}
      .travel-hero h1 {color:#fff; margin:0; font-size:2.15rem; letter-spacing:-.03em;}
      .travel-hero p {color:#e4f5f2; margin:.55rem 0 0; font-size:1.02rem;}
      .section-kicker {color:#147a79; font-weight:700; text-transform:uppercase;
        letter-spacing:.11em; font-size:.77rem; margin-bottom:.3rem;}
    </style>
    <div class="travel-hero"><div class="section-kicker" style="color:#a7ece2">PLAN WITH CONFIDENCE</div>
    <h1>Find your next great trip</h1>
    <p>Thoughtful days, clear costs, and places grounded in real location data.</p></div>
    ''', unsafe_allow_html=True)


def render_overview(request: dict, budget: dict) -> None:
    st.subheader('Your trip at a glance')
    nights = (pd.Timestamp(request['return_date']) - pd.Timestamp(request['departure_date'])).days
    cols = st.columns(4)
    cols[0].metric('Destination', request['destination'])
    cols[1].metric('Travel dates', f"{request['departure_date']} → {request['return_date']}")
    cols[2].metric('Duration', f'{nights + 1} days · {nights} nights')
    cols[3].metric('Travelers', str(request['travelers']))
    st.caption(f"From {request['origin']} · {request['rooms']} room(s) · {request.get('travel_pace', 'Balanced')} pace")


def render_budget(plan: dict) -> None:
    st.subheader('Budget overview')
    budget = plan['budget']
    original = plan.get('initial_budget') or budget
    complete = budget.get('estimated_total_usd') is not None
    cols = st.columns(4)
    cols[0].metric('Estimated total' if complete else 'Known subtotal',
                   money(budget.get('estimated_total_usd') if complete else budget.get('known_subtotal_usd')))
    cols[1].metric('Your budget', money(plan['request']['budget_limit_usd']))
    saved = (original.get('estimated_total_usd') - budget['estimated_total_usd']
             if complete and original.get('estimated_total_usd') is not None else None)
    cols[2].metric('Estimated savings', money(saved))
    cols[3].metric('Remaining budget', money(budget.get('remaining_usd')))
    if complete:
        if budget['within_budget']:
            st.success('Your trip was optimized to fit your budget.' if saved and saved > 0
                       else 'Your estimated plan is within budget.')
        else:
            st.warning(f"This sample plan is {money(-budget['remaining_usd'])} over budget.")
    else:
        st.info('This is a partial USD estimate. Missing travel or admission prices prevent a full budget verdict.')
        st.caption('Missing: ' + ', '.join(name.replace('_usd', '').replace('_', ' ')
                                            for name in budget.get('missing_costs', [])))
    breakdown = [{'Category': key.replace('_usd', '').replace('_', ' ').title(),
                  'USD': value} for key, value in budget['breakdown'].items() if value is not None]
    if breakdown:
        st.bar_chart(pd.DataFrame(breakdown).set_index('Category'), height=230)
    if complete and original.get('estimated_total_usd') != budget['estimated_total_usd']:
        st.caption(f"Original {money(original['estimated_total_usd'])}  →  Optimized {money(budget['estimated_total_usd'])}  ·  Saved {money(saved)}")
    st.caption('USD planning figures; taxes, fees, baggage, and admission may be excluded.')


def render_recommendations(plan: dict) -> None:
    st.subheader('Getting there & staying over')
    flight_col, hotel_col = st.columns(2)
    flight = plan.get('flight')
    hotel = plan.get('hotel')
    request = plan['request']
    with flight_col, st.container(border=True):
        st.markdown('#### ✈️ Flight')
        if flight:
            st.write(f"{flight['airline']} · {flight['origin']} → {flight['destination']}")
            st.write(f"Option {flight['id']} · {flight['stops']} stop(s) · {money(flight['total_round_trip_usd'])} for the group")
            st.caption('Simulated fare · No live availability · Not bookable')
        else:
            st.write('No verified flight offer is available for this route.')
            allowance = request.get('flight_allowance_usd')
            st.write(f'Your flight allowance: {money(allowance)}' if allowance is not None
                     else 'Add a flight allowance when you have an estimate.')
            st.caption('User estimate, not an airline quote')
    with hotel_col, st.container(border=True):
        st.markdown('#### 🏨 Stay')
        if hotel:
            st.write(f"{hotel['name']} · {hotel['city']}")
            st.write(f"Option {hotel['id']} · {plan['budget']['nights']} nights · {money(hotel['total_room_cost_usd'])}")
            st.caption('Simulated rate · No live availability · Not bookable')
        else:
            st.write('No verified hotel offer is available for this city.')
            allowance = request.get('hotel_allowance_usd')
            st.write(f'Your stay allowance: {money(allowance)}' if allowance is not None
                     else 'Add a stay allowance when you have an estimate.')
            st.caption('User estimate, not a hotel quote')
    if plan.get('flights', {}).get('options') or plan.get('hotels', {}).get('options'):
        with st.expander('Compare simulated travel options'):
            for option in plan.get('flights', {}).get('options', []):
                st.write(f"✈️ {option['id']} · {option['airline']} · {money(option['total_round_trip_usd'])} round trip")
            for option in plan.get('hotels', {}).get('options', []):
                st.write(f"🏨 {option['id']} · {option['name']} · {money(option['total_room_cost_usd'])} for the stay")


def render_itinerary(plan: dict) -> None:
    st.subheader('Your days, thoughtfully planned')
    days = plan['itinerary']['itinerary']
    icons = {'museum': '🏛️', 'historic': '🏰', 'park': '🌿', 'viewpoint': '📸',
             'gallery': '🎨', 'food': '🍽️', 'outdoors': '🌿', 'culture': '🏛️'}
    for day in days:
        with st.expander(f"Day {day['day']}", expanded=day['day'] == 1):
            if 'slots' in day:
                slots = day['slots']
            else:
                activity = day['activity']
                slots = [{'period': 'morning', 'title': activity['name'],
                          'category': activity['interest'], 'verified_place': False,
                          'source': 'SYNTHETIC_DEMO', 'duration_minutes': None,
                          'description': 'Illustrative demo activity.'},
                         {'period': 'afternoon', 'title': 'Flexible time',
                          'category': 'general_suggestion', 'verified_place': False,
                          'source': 'GENERAL_SUGGESTION', 'duration_minutes': None,
                          'description': 'Choose a stop locally.'},
                         {'period': 'evening', 'title': 'Flexible dinner or rest',
                          'category': 'general_suggestion', 'verified_place': False,
                          'source': 'GENERAL_SUGGESTION', 'duration_minutes': None,
                          'description': 'No venue or price is verified.'}]
            for slot in slots:
                icon = icons.get(slot['category'], '📍')
                st.write(f"{icon} **{slot['period'].title()}** · {slot['title']}")
                label = ('Verified OSM place' if slot.get('verified_place') else
                         'Illustrative demo activity' if slot['source'] == 'SYNTHETIC_DEMO'
                         else 'General suggestion')
                duration = (f" · about {slot['duration_minutes']} min" if slot.get('duration_minutes') else '')
                st.caption(label + duration + (f" · {slot['description']}" if slot.get('description') else ''))
    st.caption('Periods and durations are planning suggestions, not opening-hour or transit guarantees.')


def render_map(plan: dict) -> None:
    st.subheader('Explore the area')
    points = []
    for day in plan['itinerary']['itinerary']:
        if 'slots' in day:
            for slot in day['slots']:
                if slot.get('verified_place') and slot.get('latitude') is not None:
                    points.append({'lat': slot['latitude'], 'lon': slot['longitude']})
        elif day['activity'].get('latitude') is not None:
            points.append({'lat': day['activity']['latitude'], 'lon': day['activity']['longitude']})
    location = plan['request'].get('destination_location')
    if location:
        points.insert(0, {'lat': location['latitude'], 'lon': location['longitude']})
    if points:
        st.map(pd.DataFrame(points), latitude='lat', longitude='lon', height=340)
        st.caption('Verified OSM coordinates for global places; demo coordinates are approximate static references.')
    else:
        st.info('A map is unavailable because no reliable coordinates were returned.')


def render_diagnostics(result: dict) -> None:
    with st.expander('Advanced → Developer Diagnostics', expanded=False):
        if result.get('message'):
            st.code(result['message'])
        if result.get('progress_errors'):
            st.write({'progress_display_errors': result['progress_errors']})
        if result.get('agent_summary'):
            st.dataframe(pd.DataFrame(result['agent_summary']), hide_index=True)
        if result.get('trace'):
            st.dataframe(pd.DataFrame(result['trace']), hide_index=True)
        if result.get('model_metrics'):
            st.dataframe(pd.DataFrame(result['model_metrics']), hide_index=True)
        if result.get('tool_metrics'):
            st.dataframe(pd.DataFrame(result['tool_metrics']), hide_index=True)
        if result.get('timings'):
            st.write(result['timings'])
