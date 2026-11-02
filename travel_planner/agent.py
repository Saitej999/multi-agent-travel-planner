"""Ordered ADK travel workflow with verified session-state handoffs."""

from google.adk.agents import LlmAgent, SequentialAgent
from google.genai import types

from travel_core.config import build_model
from travel_core.tools import suggest_activities
from travel_planner.budget_agent import BudgetAgent
from travel_planner.coordination import (
    record_coordinator_response, record_model_error,
    record_model_response, record_model_start, report_tool_error,
    save_specialist_tool_result, skip_on_error, specialist_tool_args,
)
from travel_planner.retrieval_agents import FlightSearchAgent, HotelSearchAgent

MODEL = build_model()
SPECIALIST_CONFIG = types.GenerateContentConfig(temperature=0, max_output_tokens=512)

flight_agent = FlightSearchAgent(name='flight_agent',
    description='Runs the Python flight search deterministically and records its ADK events.')

hotel_agent = HotelSearchAgent(name='hotel_agent',
    description='Runs the Python hotel search deterministically and records its ADK events.')

itinerary_agent = LlmAgent(
    name='itinerary_agent', model=MODEL,
    description='Uses Gemini to select interests or verified places for the Python itinerary tool.',
    instruction=(
        'For {trip_request}, call suggest_activities once. For global_mode, select verified '
        'attraction IDs in preferred visit order from {attraction_choices}; choose for interests '
        'and pace. Prefer a varied set of notable places and group nearby places by day. '
        'If there are no verified IDs, call the tool once with an empty selection. '
        'Never invent IDs. For demo trips, choose interest tags from culture, food, '
        'outdoors, entertainment; set avoid_popular_spots only if requested.'
    ),
    tools=[suggest_activities], include_contents='none',
    generate_content_config=SPECIALIST_CONFIG,
    before_agent_callback=skip_on_error,
    before_tool_callback=specialist_tool_args,
    after_tool_callback=save_specialist_tool_result,
    on_tool_error_callback=report_tool_error,
    before_model_callback=record_model_start,
    after_model_callback=record_model_response,
    on_model_error_callback=record_model_error,
)

budget_agent = BudgetAgent(
    name='budget_agent',
    description='Calculates the budget in Python from verified flight, hotel, and itinerary state.',
)

travel_coordinator = LlmAgent(
    name='travel_coordinator', model=MODEL,
    description='Uses Gemini to explain the verified travel plan.',
    instruction=(
        'Using only {coordinator_facts}, write a concise travel plan. '
        'For global mode, describe verified places by day, note user price allowances and missing '
        'flight, hotel, or admission prices, and never claim the full trip fits the budget. '
        'If attraction_status is partial or insufficient_data, say that venue coverage is '
        'incomplete and leave unscheduled periods open. '
        'For demo mode, report verified synthetic flight and hotel IDs and Python totals. '
        'List verified activities on their exact numbered day. '
        'Do not replace activity days with flight, arrival, or hotel events; arrival time is unknown. '
        'State trip dates and travelers; for demo trips state selected flight and hotel IDs and totals, '
        'savings or shortfall, and one sentence about how the activities match preferences. '
        'The budget excludes taxes and fees; do not say they are included. '
        'Flight and hotel offers are simulated and not bookable. '
        'Do not invent schedules, prices, or attractions.'
    ),
    output_key='final_plan_text',
    include_contents='none',
    generate_content_config=types.GenerateContentConfig(temperature=0, max_output_tokens=420),
    before_agent_callback=skip_on_error,
    before_model_callback=record_model_start,
    after_model_callback=record_coordinator_response,
    on_model_error_callback=record_model_error,
)

root_agent = SequentialAgent(
    name='travel_planner_workflow',
    description='Runs flight, hotel, itinerary, budget, and final summary in order.',
    sub_agents=[flight_agent, hotel_agent, itinerary_agent, budget_agent, travel_coordinator],
)
