"""Fully offline example that does not require Ollama, ADK, or the internet.

Run from the project root: python -m scripts.demo_pipeline
"""

import json

from travel_core.planner import plan_trip


def main() -> None:
    trip = {
        'origin': 'Chicago', 'destination': 'New York City',
        'departure_date': '2026-11-15', 'return_date': '2026-11-19',
        'travelers': 2, 'rooms': 1, 'budget_limit_usd': 2000,
        'interests': 'culture,food',
    }
    print(json.dumps(plan_trip(trip), indent=2))


if __name__ == '__main__':
    main()
