"""Deterministic, completely fictional catalog for agent orchestration demos.

No airline or hotel availability or bookability is implied. Replace with
licensed provider adapters before making real-world travel recommendations.
"""

AIRPORT_ALIASES = {
    "chicago": "ORD", "ord": "ORD", "o'hare": "ORD", "ohare": "ORD",
    "new york": "JFK", "new york city": "JFK", "nyc": "JFK", "jfk": "JFK",
    "san francisco": "SFO", "sf": "SFO", "sfo": "SFO",
    "tokyo": "HND", "hnd": "HND", "haneda": "HND",
}

CITY_BY_AIRPORT = {"ORD": "Chicago", "JFK": "New York City", "SFO": "San Francisco", "HND": "Tokyo"}

# Prices are synthetic sample amounts in USD for entire ROUND TRIP per person.
FLIGHTS = [
    {"id": "DEMO-F001", "origin": "ORD", "destination": "JFK", "airline": "Demo Air A", "stops": 0, "round_trip_usd_per_person": 330.0},
    {"id": "DEMO-F002", "origin": "ORD", "destination": "JFK", "airline": "Demo Air B", "stops": 1, "round_trip_usd_per_person": 265.0},
    {"id": "DEMO-F003", "origin": "ORD", "destination": "SFO", "airline": "Demo Air A", "stops": 0, "round_trip_usd_per_person": 420.0},
    {"id": "DEMO-F004", "origin": "ORD", "destination": "SFO", "airline": "Demo Air C", "stops": 1, "round_trip_usd_per_person": 340.0},
    {"id": "DEMO-F005", "origin": "ORD", "destination": "HND", "airline": "Demo Air C", "stops": 1, "round_trip_usd_per_person": 1080.0},
    {"id": "DEMO-F006", "origin": "ORD", "destination": "HND", "airline": "Demo Air A", "stops": 0, "round_trip_usd_per_person": 1420.0},
]

# Synthetic nightly rate per room; hotel names do not represent actual listings.
HOTELS = [
    {"id": "DEMO-H001", "city": "New York City", "name": "Demo Midtown Stay", "nightly_usd_per_room": 160.0, "category": "budget"},
    {"id": "DEMO-H002", "city": "New York City", "name": "Demo Parkside Suites", "nightly_usd_per_room": 230.0, "category": "midrange"},
    {"id": "DEMO-H003", "city": "San Francisco", "name": "Demo Bayview Inn", "nightly_usd_per_room": 180.0, "category": "budget"},
    {"id": "DEMO-H004", "city": "San Francisco", "name": "Demo Union Square Rooms", "nightly_usd_per_room": 270.0, "category": "midrange"},
    {"id": "DEMO-H005", "city": "Tokyo", "name": "Demo Shinjuku Hotel", "nightly_usd_per_room": 115.0, "category": "budget"},
    {"id": "DEMO-H006", "city": "Tokyo", "name": "Demo Ginza Residence", "nightly_usd_per_room": 210.0, "category": "midrange"},
]

# Activity ideas, not operating schedules, tickets, or guarantees.
ACTIVITIES = {
    "New York City": [
        {"name": "Central Park walk", "interest": "outdoors", "estimated_usd_per_person": 0.0},
        {"name": "Museum visit", "interest": "culture", "estimated_usd_per_person": 30.0},
        {"name": "Neighborhood food tour", "interest": "food", "estimated_usd_per_person": 40.0},
        {"name": "Brooklyn waterfront", "interest": "outdoors", "estimated_usd_per_person": 0.0},
        {"name": "Broadway show", "interest": "entertainment", "estimated_usd_per_person": 95.0, "popular_spot": True},
        {"name": "Historic neighborhood stroll", "interest": "culture", "estimated_usd_per_person": 0.0},
    ],
    "San Francisco": [
        {"name": "Golden Gate Bridge viewpoints", "interest": "outdoors", "estimated_usd_per_person": 0.0, "popular_spot": True},
        {"name": "Exploratorium visit", "interest": "culture", "estimated_usd_per_person": 40.0},
        {"name": "Ferry Building food tasting", "interest": "food", "estimated_usd_per_person": 35.0},
        {"name": "Lands End trail", "interest": "outdoors", "estimated_usd_per_person": 0.0},
        {"name": "Chinatown walking tour", "interest": "culture", "estimated_usd_per_person": 20.0},
        {"name": "Live music outing", "interest": "entertainment", "estimated_usd_per_person": 35.0},
    ],
    "Tokyo": [
        {"name": "Meiji Shrine grounds", "interest": "culture", "estimated_usd_per_person": 0.0},
        {"name": "Shibuya neighborhood walk", "interest": "outdoors", "estimated_usd_per_person": 0.0, "popular_spot": True},
        {"name": "Food market tasting", "interest": "food", "estimated_usd_per_person": 35.0},
        {"name": "Museum visit", "interest": "culture", "estimated_usd_per_person": 18.0},
        {"name": "Ueno Park", "interest": "outdoors", "estimated_usd_per_person": 0.0},
        {"name": "Game arcade", "interest": "entertainment", "estimated_usd_per_person": 25.0},
    ],
}


# Approximate, manually curated landmark coordinates for the demo map.
# Names and location points represent real public places, but activity prices
# above remain entirely synthetic. No opening hours or ticket rates are checked.
ACTIVITY_PLACES = {
    "New York City": [
        ("Central Park walk", 40.7829, -73.9654),
        ("Museum of Modern Art visit", 40.7614, -73.9776),
        ("Chelsea Market food exploration", 40.7424, -74.0061),
        ("Brooklyn Bridge Park waterfront", 40.7003, -73.9967),
        ("Times Square theater district", 40.7580, -73.9855),
        ("Lower East Side historic neighborhood", 40.7150, -73.9890),
    ],
    "San Francisco": [
        ("Golden Gate Bridge viewpoints", 37.8199, -122.4783),
        ("Exploratorium visit", 37.8017, -122.3973),
        ("Ferry Building food exploration", 37.7955, -122.3937),
        ("Lands End trail", 37.7810, -122.5033),
        ("Chinatown walking tour", 37.7941, -122.4078),
        ("Union Square evening outing", 37.7879, -122.4074),
    ],
    "Tokyo": [
        ("Meiji Shrine grounds", 35.6764, 139.6993),
        ("Shibuya Crossing neighborhood walk", 35.6595, 139.7005),
        ("Tsukiji Outer Market food exploration", 35.6655, 139.7707),
        ("Tokyo National Museum visit", 35.7189, 139.7765),
        ("Ueno Park walk", 35.7148, 139.7730),
        ("Akihabara arcade district", 35.6983, 139.7730),
    ],
}
for _city, _places in ACTIVITY_PLACES.items():
    for _activity, (_name, _lat, _lon) in zip(ACTIVITIES[_city], _places):
        _activity.update(name=_name, latitude=_lat, longitude=_lon)
