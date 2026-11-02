"""Run the supported synthetic trip and print real ADK events and final state.

Run from the repository root: python -m scripts.verify_workflow
Requires a free-tier Gemini API key in travel_planner/.env.
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

from travel_core.config import model_name
from travel_core.schemas import TripRequest
from travel_planner.runner import WorkflowRunError, run_adk_trip


async def main() -> None:
    parser = argparse.ArgumentParser(description='Run the ADK Gemini travel demo')
    parser.add_argument('--budget', type=float, default=4000)
    parser.add_argument('--interests', default='food,culture,outdoors')
    parser.add_argument('--preferences', default='', help='Optional traveler style or crowd preferences')
    parser.add_argument('--timeout', type=float, default=75, help='Maximum ADK run time in seconds')
    parser.add_argument('--departure-date', default='2026-12-15')
    parser.add_argument('--return-date', default='2026-12-19')
    parser.add_argument('--output', type=Path, help='Write the trace and result as JSON')
    args = parser.parse_args()
    request = TripRequest(
        origin='Chicago', destination='New York City',
        departure_date=args.departure_date, return_date=args.return_date,
        travelers=2, rooms=1, budget_limit_usd=args.budget,
        interests=args.interests, preferences=args.preferences,
    )
    try:
        result = await run_adk_trip(request, timeout_seconds=args.timeout)
    except WorkflowRunError as exc:
        result = {'status': 'failed', 'model': model_name(), 'message': str(exc),
                  'trace': exc.trace, 'timings': exc.timings,
                  'model_metrics': exc.model_metrics, 'tool_metrics': exc.tool_metrics,
                  'total_seconds': exc.total_seconds}
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
        sys.exit(1)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'success', 'model': result['model'],
                          'trace_file': str(args.output),
                          'tool_calls': [(item['agent'], item['tool']) for item in result['trace']
                                         if item['event'] == 'tool_call'],
                          'total_seconds': result['total_seconds']}, indent=2))
    else:
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
