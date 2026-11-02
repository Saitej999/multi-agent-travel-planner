"""Stable public request and response contracts for the local web application."""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .geo import Attraction, ResolvedLocation
from .schemas import TripRequest


PriceKind = Literal['known', 'estimated', 'unknown']
DataSource = Literal['simulated', 'user_estimate', 'assumption', 'verified', 'unknown']


class Price(BaseModel):
    amount_usd: float | None = Field(default=None, ge=0)
    kind: PriceKind
    source: DataSource

    @model_validator(mode='after')
    def check_amount(self):
        if (self.kind == 'unknown') != (self.amount_usd is None):
            raise ValueError('Unknown prices must have no amount; known or estimated prices require an amount')
        if self.kind == 'known' and self.source != 'verified':
            raise ValueError('A known price must come from a verified source')
        return self


class CostAllowances(BaseModel):
    flights_usd: float | None = Field(default=None, ge=0)
    hotel_usd: float | None = Field(default=None, ge=0)


class PlanTripRequest(BaseModel):
    origin: ResolvedLocation
    destination: ResolvedLocation
    departure_date: date
    return_date: date
    travelers: int = Field(ge=1, le=8)
    rooms: int = Field(ge=1, le=8)
    total_budget_usd: float = Field(gt=0, le=1_000_000)
    interests: list[str] = Field(default_factory=list, max_length=12)
    travel_pace: Literal['Relaxed', 'Balanced', 'Adventurous'] = 'Balanced'
    additional_preferences: str = Field(default='', max_length=300)
    optional_cost_allowances: CostAllowances = Field(default_factory=CostAllowances)

    @model_validator(mode='after')
    def check_trip(self):
        nights = (self.return_date - self.departure_date).days
        if not 1 <= nights <= 13:
            raise ValueError('Return must be 1–13 nights after departure')
        if self.origin.id == self.destination.id:
            raise ValueError('Origin and destination must be different cities')
        return self

    def to_trip_request(self) -> TripRequest:
        """Translate the web contract once, retaining existing Pydantic validation."""
        origin = _catalog_city(self.origin) or self.origin.label
        destination = _catalog_city(self.destination) or self.destination.label
        sample = origin == 'Chicago' and destination in {
            'New York City', 'San Francisco', 'Tokyo'}
        return TripRequest(
            origin=origin, destination=destination,
            origin_location=self.origin, destination_location=self.destination,
            global_mode=not sample,
            departure_date=self.departure_date, return_date=self.return_date,
            travelers=self.travelers, rooms=self.rooms,
            budget_limit_usd=self.total_budget_usd,
            interests=','.join(self.interests),
            preferences=self.additional_preferences, travel_pace=self.travel_pace,
            flight_allowance_usd=self.optional_cost_allowances.flights_usd,
            hotel_allowance_usd=self.optional_cost_allowances.hotel_usd,
        )


def _catalog_city(location: ResolvedLocation) -> str | None:
    country = location.country_code.upper() or location.country.upper()
    region = location.region.casefold()
    name = location.name.casefold()
    if name == 'chicago' and 'illinois' in region and country in {'US', 'UNITED STATES'}:
        return 'Chicago'
    if name in {'new york', 'new york city'} and 'new york' in region and country in {'US', 'UNITED STATES'}:
        return 'New York City'
    if name == 'san francisco' and 'california' in region and country in {'US', 'UNITED STATES'}:
        return 'San Francisco'
    if name == 'tokyo' and country in {'JP', 'JAPAN'}:
        return 'Tokyo'
    return None


class TripSummary(BaseModel):
    origin: ResolvedLocation
    destination: ResolvedLocation
    departure_date: date
    return_date: date
    days: int
    nights: int
    travelers: int
    rooms: int
    total_budget_usd: float
    travel_pace: str
    interests: list[str]


class FlightOption(BaseModel):
    id: str
    airline: str
    origin: str
    destination: str
    stops: int
    group_round_trip: Price
    bookable: bool = False


class HotelOption(BaseModel):
    id: str
    name: str
    city: str
    nights: int
    whole_stay: Price
    bookable: bool = False


class ActivitySlot(BaseModel):
    period: Literal['morning', 'afternoon', 'evening']
    title: str
    category: str
    description: str = ''
    duration_minutes: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str
    verified_place: bool
    attraction_id: str | None = None
    source_url: str | None = None


class DailyPlan(BaseModel):
    day: int
    date: date
    slots: list[ActivitySlot]


class CostItem(BaseModel):
    category: Literal['flights', 'hotel', 'food', 'ground_transport', 'activities']
    label: str
    price: Price


class BudgetBreakdown(BaseModel):
    items: list[CostItem]
    initial_total: Price
    optimized_total: Price
    known_subtotal: Price
    savings: Price
    remaining: Price
    budget_limit_usd: float
    comparison_status: Literal['complete', 'partial']
    within_budget: bool | None
    nights: int

    @model_validator(mode='after')
    def check_comparison(self):
        if self.comparison_status == 'partial' and self.within_budget is not None:
            raise ValueError('Partial budgets cannot claim a within-budget result')
        return self


class OptimizationSummary(BaseModel):
    triggered: bool
    explanation: str
    outcome: str


class Diagnostics(BaseModel):
    model: str
    execution_mode: str
    trace: list[dict] = Field(default_factory=list)
    agent_summary: list[dict] = Field(default_factory=list)
    timings: dict[str, float] = Field(default_factory=dict)
    model_metrics: list[dict] = Field(default_factory=list)
    tool_metrics: list[dict] = Field(default_factory=list)
    geographic_discovery: list[dict] = Field(default_factory=list)


class AttractionDataStatus(BaseModel):
    status: Literal['complete', 'partial', 'insufficient_data', 'not_applicable']
    verified_count: int = Field(ge=0)
    sources: list[str]
    quality_issues: list[str] = Field(default_factory=list)


class TripPlanResponse(BaseModel):
    trip_summary: TripSummary
    flight_options: list[FlightOption]
    hotel_options: list[HotelOption]
    selected_flight: FlightOption | None
    selected_hotel: HotelOption | None
    flight_allowance: Price
    hotel_allowance: Price
    daily_itinerary: list[DailyPlan]
    attractions: list[Attraction]
    attraction_data: AttractionDataStatus
    budget_breakdown: BudgetBreakdown
    optimization_summary: OptimizationSummary
    warnings: list[str]
    data_sources: list[str]
    diagnostics: Diagnostics

    @model_validator(mode='after')
    def check_dates(self):
        summary = self.trip_summary
        if len(self.daily_itinerary) != summary.days:
            raise ValueError('Itinerary day count must match trip dates')
        if self.budget_breakdown.nights != summary.nights:
            raise ValueError('Hotel night count must match trip dates')
        return self


def _price(amount: float | None, source: DataSource) -> Price:
    return Price(amount_usd=amount, kind='unknown' if amount is None else 'estimated',
                 source='unknown' if amount is None else source)


def plan_response(request: PlanTripRequest, result: dict) -> TripPlanResponse:
    """Project verified ADK state into a stable UI response, without LLM arithmetic."""
    facts = result['structured_plan']
    budget = facts['budget']
    original = (facts.get('original_plan') or {}).get('budget') or budget
    days = (request.return_date - request.departure_date).days + 1
    nights = days - 1
    global_mode = facts['request'].get('global_mode', False)

    flights = [FlightOption(
        id=item['id'], airline=item['airline'], origin=item['origin'],
        destination=item['destination'], stops=item['stops'],
        group_round_trip=_price(item['total_round_trip_usd'], 'simulated'))
        for item in result.get('available_flights') or []]
    hotels = [HotelOption(
        id=item['id'], name=item['name'], city=item['city'], nights=nights,
        whole_stay=_price(item['total_room_cost_usd'], 'simulated'))
        for item in result.get('available_hotels') or []]
    selected_flight = next((item for item in flights if item.id == (facts.get('flight') or {}).get('id')), None)
    selected_hotel = next((item for item in hotels if item.id == (facts.get('hotel') or {}).get('id')), None)
    if not global_mode and (selected_flight is None or selected_hotel is None):
        raise ValueError('Selected simulated offers are missing from returned options')

    itinerary = []
    for day in facts['itinerary']:
        if 'slots' in day:
            expected_date = request.departure_date + timedelta(days=day['day'] - 1)
            if day.get('date') != expected_date.isoformat():
                raise ValueError('Itinerary date does not match trip dates')
            slots = [ActivitySlot.model_validate(slot) for slot in day['slots']]
        else:
            activity = day['activity']
            slots = [ActivitySlot(
                period='morning', title=activity['name'], category=activity['interest'],
                description='Illustrative demo activity', duration_minutes=90,
                latitude=activity['latitude'], longitude=activity['longitude'],
                source='SYNTHETIC_DEMO', verified_place=False),
                ActivitySlot(period='afternoon', title='Flexible time', category='general',
                             source='GENERAL_SUGGESTION', verified_place=False),
                ActivitySlot(period='evening', title='Dinner or rest', category='general',
                             source='GENERAL_SUGGESTION', verified_place=False)]
        itinerary.append(DailyPlan(
            day=day['day'],
            date=request.departure_date + timedelta(days=day['day'] - 1),
            slots=slots))

    breakdown = budget['breakdown']
    mapped = [
        ('flights', 'Round-trip flights', 'flights_usd' if global_mode else 'round_trip_flights_usd'),
        ('hotel', 'Hotel stay', 'hotel_usd' if global_mode else 'hotel_room_total_usd'),
        ('food', 'Food', 'food_usd'),
        ('ground_transport', 'Ground transport', 'ground_transport_usd'),
        ('activities', 'Activities and admission', 'admission_usd' if global_mode else 'activities_usd'),
    ]
    items = [CostItem(
        category=category, label=label,
        price=_price(breakdown.get(key), (
            'user_estimate' if global_mode and category in {'flights', 'hotel'} else
            'simulated' if category in {'flights', 'hotel', 'activities'} else 'assumption')))
        for category, label, key in mapped]
    final_total = budget.get('estimated_total_usd')
    initial_total = original.get('estimated_total_usd')
    savings = (round(initial_total - final_total, 2)
               if initial_total is not None and final_total is not None else None)
    known_subtotal = budget.get('known_subtotal_usd', final_total)
    warnings = (['Flight and hotel offers and prices are simulated, not live or bookable.']
                if not global_mode else
                ['No verified flight or hotel offers are available for this route.',
                 'This is a partial estimate; admission and any missing allowances are unknown.',
                 *(result.get('attraction_discovery') or {}).get('warnings', []),
                 *(['The itinerary has unscheduled periods because verified places are limited.']
                   if facts.get('attraction_status') == 'partial' else [])])
    attraction_sources = (result.get('attraction_discovery') or {}).get('sources') or []
    return TripPlanResponse(
        trip_summary=TripSummary(
            origin=request.origin, destination=request.destination,
            departure_date=request.departure_date, return_date=request.return_date,
            days=days, nights=nights, travelers=request.travelers, rooms=request.rooms,
            total_budget_usd=request.total_budget_usd, travel_pace=request.travel_pace,
            interests=request.interests),
        flight_options=flights, hotel_options=hotels,
        selected_flight=selected_flight, selected_hotel=selected_hotel,
        flight_allowance=_price(request.optional_cost_allowances.flights_usd, 'user_estimate'),
        hotel_allowance=_price(request.optional_cost_allowances.hotel_usd, 'user_estimate'),
        daily_itinerary=itinerary,
        attractions=[Attraction.model_validate(item) for item in result.get('attractions') or []],
        attraction_data=AttractionDataStatus(
            status=({'ok': 'complete'}.get(facts.get('attraction_status'),
                    facts.get('attraction_status', 'partial')) if global_mode else 'not_applicable'),
            verified_count=len(result.get('attractions') or []),
            sources=attraction_sources if global_mode else [],
            quality_issues=facts.get('quality_issues') or []),
        budget_breakdown=BudgetBreakdown(
            items=items, initial_total=_price(initial_total, 'simulated'),
            optimized_total=_price(final_total, 'simulated' if not global_mode else 'unknown'),
            known_subtotal=_price(known_subtotal, 'simulated' if not global_mode else 'assumption'),
            savings=_price(savings, 'simulated'), remaining=_price(budget.get('remaining_usd'), 'simulated'),
            budget_limit_usd=request.total_budget_usd,
            comparison_status='partial' if global_mode else 'complete',
            within_budget=budget.get('within_budget'), nights=nights),
        optimization_summary=OptimizationSummary(
            triggered=facts['replanning'].get('triggered', False),
            explanation=facts['replanning'].get('explanation', ''),
            outcome=facts['replanning'].get('outcome', 'unknown')),
        warnings=warnings,
        data_sources=['SYNTHETIC_DEMO'] if not global_mode else [
            'OPEN_METEO_GEOCODING', *attraction_sources],
        diagnostics=Diagnostics(
            model=result['model'], execution_mode=result['execution_mode'],
            trace=result.get('trace') or [], agent_summary=result.get('agent_summary') or [],
            timings=result.get('timings') or {}, model_metrics=result.get('model_metrics') or [],
            tool_metrics=result.get('tool_metrics') or [],
            geographic_discovery=(result.get('attraction_discovery') or {}).get('diagnostics') or []),
    )
