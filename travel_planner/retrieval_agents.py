"""Deterministic ADK stages for mandatory flight and hotel retrieval."""

from types import SimpleNamespace
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from travel_core.tools import search_flights, search_hotels
from travel_planner.coordination import (
    prepare_request, save_specialist_tool_result, specialist_tool_args,
)


async def _run_search(ctx: InvocationContext, agent_name: str, tool_name: str,
                      tool_function) -> AsyncGenerator[Event, None]:
    state = ctx.session.state
    before = dict(state)
    callback_context = SimpleNamespace(
        state=state, user_content=ctx.user_content,
        actions=SimpleNamespace(skip_summarization=False),
    )
    if tool_name == 'search_flights':
        error_content = prepare_request(callback_context)
        if error_content is not None:
            yield Event(invocation_id=ctx.invocation_id, author=agent_name,
                        content=error_content,
                        actions=EventActions(state_delta={
                            key: value for key, value in state.items()
                            if before.get(key) != value}))
            return
    elif state.get('workflow_error'):
        return

    tool = SimpleNamespace(name=tool_name)
    args = {}
    try:
        specialist_tool_args(tool, args, callback_context)
    except Exception as exc:
        state['workflow_error'] = f'{tool_name} could not prepare the validated request: {type(exc).__name__}'
        yield Event(invocation_id=ctx.invocation_id, author=agent_name,
                    content=types.Content(role='model', parts=[
                        types.Part(text=state['workflow_error'])]),
                    actions=EventActions(state_delta={
                        key: value for key, value in state.items()
                        if before.get(key) != value}))
        return

    yield Event(invocation_id=ctx.invocation_id, author=agent_name,
                content=types.Content(role='model', parts=[
                    types.Part.from_function_call(name=tool_name, args=args)]),
                actions=EventActions(state_delta={
                    key: value for key, value in state.items()
                    if before.get(key) != value}))
    before_result = dict(state)
    try:
        result = tool_function(**args)
    except Exception as exc:
        result = {'status': 'tool_error', 'message': f'{tool_name} failed',
                  'error_type': type(exc).__name__}
    save_specialist_tool_result(tool, args, callback_context, result)
    metrics = list(state.get('tool_metrics') or [])
    if metrics:
        metrics[-1] = {**metrics[-1], 'source': 'deterministic_adk_agent'}
        state['tool_metrics'] = metrics
    yield Event(invocation_id=ctx.invocation_id, author=agent_name,
                content=types.Content(role='user', parts=[
                    types.Part.from_function_response(name=tool_name, response=result)]),
                actions=EventActions(state_delta={
                    key: value for key, value in state.items()
                    if before_result.get(key) != value}))


class FlightSearchAgent(BaseAgent):
    """Always execute the existing Python flight tool exactly once."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        async for event in _run_search(ctx, self.name, 'search_flights', search_flights):
            yield event


class HotelSearchAgent(BaseAgent):
    """Always execute the existing Python hotel tool after flight retrieval."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        async for event in _run_search(ctx, self.name, 'search_hotels', search_hotels):
            yield event
