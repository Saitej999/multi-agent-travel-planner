"""Input validation schemas. Pydantic ensures tool arguments are coherent."""

from datetime import date, time

from pydantic import BaseModel, Field, model_validator

from .geo import ResolvedLocation


class TravelDates(BaseModel):
    departure_date: date
    return_date: date

    @model_validator(mode="after")
    def validate_range(self):
        if self.return_date <= self.departure_date:
            raise ValueError("return_date must be after departure_date")
        if (self.return_date - self.departure_date).days > 30:
            raise ValueError("demo supports trips up to 30 nights")
        return self


class FlightQuery(TravelDates):
    origin: str = Field(min_length=2)
    destination: str = Field(min_length=2)
    travelers: int = Field(ge=1, le=8)


class HotelQuery(BaseModel):
    destination: str = Field(min_length=2)
    check_in: date
    check_out: date
    rooms: int = Field(ge=1, le=8)

    @model_validator(mode="after")
    def validate_range(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be after check_in")
        if (self.check_out - self.check_in).days > 30:
            raise ValueError("demo supports stays up to 30 nights")
        return self


class ActivityQuery(BaseModel):
    destination: str = Field(min_length=2)
    days: int = Field(ge=1, le=14)
    interests: str = ""


class BudgetQuery(BaseModel):
    flight_option_id: str
    hotel_option_id: str
    nights: int = Field(ge=1, le=30)
    travelers: int = Field(ge=1, le=8)
    rooms: int = Field(ge=1, le=8)
    food_per_person_per_day_usd: float = Field(default=45.0, ge=0, le=1000)
    transport_per_day_usd: float = Field(default=20.0, ge=0, le=1000)
    activities_per_person_usd: float = Field(default=0.0, ge=0, le=5000)
    budget_limit_usd: float = Field(default=0.0, ge=0, le=1_000_000)


class TripRequest(FlightQuery):
    """One complete demo trip. The Streamlit example supports up to 14 calendar days."""

    rooms: int = Field(default=1, ge=1, le=8)
    budget_limit_usd: float = Field(ge=1, le=1_000_000)
    interests: str = 'culture,food'
    preferences: str = Field(default='', max_length=300)
    travel_pace: str = 'Balanced'
    arrival_time: time | None = None
    departure_time: time | None = None
    global_mode: bool = False
    origin_location: ResolvedLocation | None = None
    destination_location: ResolvedLocation | None = None
    flight_allowance_usd: float | None = Field(default=None, ge=0, le=1_000_000)
    hotel_allowance_usd: float | None = Field(default=None, ge=0, le=1_000_000)
    food_per_person_per_day_usd: float = Field(default=45.0, ge=0, le=1000)
    transport_per_day_usd: float = Field(default=20.0, ge=0, le=1000)

    @model_validator(mode='after')
    def validate_duration(self):
        if (self.return_date - self.departure_date).days > 13:
            raise ValueError('Interactive demo supports up to 13 nights (14 calendar days)')
        if self.travel_pace not in {'Relaxed', 'Balanced', 'Adventurous'}:
            raise ValueError('travel_pace must be Relaxed, Balanced, or Adventurous')
        return self
