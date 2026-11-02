import { useEffect, useState, type FormEvent } from "react"
import { ArrowRight, MapPin, Search, Users } from "lucide-react"
import { searchLocations } from "@/lib/api"
import type { PlanTripRequest, ResolvedLocation } from "@/types/api"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

const INTERESTS = ["Culture", "Food", "History", "Art", "Outdoors", "Architecture"]

function dateAfter(days: number) {
  const date = new Date()
  date.setDate(date.getDate() + days)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function CityPicker({ label, value, onChange }: {
  label: string
  value: ResolvedLocation | null
  onChange: (value: ResolvedLocation | null) => void
}) {
  const [query, setQuery] = useState("")
  const [options, setOptions] = useState<ResolvedLocation[]>([])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (value || query.trim().length < 2) {
      setOptions([])
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setPending(true)
      setError("")
      try {
        const found = await searchLocations(query.trim(), controller.signal)
        setOptions(found)
        if (!found.length) setError("No matching city found. Try adding a region or country.")
      } catch (caught) {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught.message : "City search is unavailable.")
        }
      } finally {
        if (!controller.signal.aborted) setPending(false)
      }
    }, 320)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [query, value])

  return (
    <div className="relative">
      <label className="form-label" htmlFor={label}>{label}</label>
      <div className="relative">
        <MapPin size={18} className="field-icon" />
        <input
          id={label}
          className="field field-with-icon"
          placeholder="Search city, region or country"
          autoComplete="off"
          value={query}
          onChange={(event) => { setQuery(event.target.value); onChange(null) }}
          aria-expanded={options.length > 0}
          aria-controls={label + "-results"}
        />
      </div>
      {value && <p className="mt-1.5 text-xs font-medium text-teal-700">Selected: {value.name}, {value.region}, {value.country}</p>}
      {pending && <p className="mt-1.5 text-xs text-slate-500">Finding cities…</p>}
      {error && <p className="mt-1.5 text-xs text-rose-700" role="status">{error}</p>}
      {!!options.length && (
        <div id={label + "-results"} className="absolute z-30 mt-1 max-h-64 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl" role="listbox">
          {options.map((city) => (
            <button key={city.id} type="button" role="option" aria-selected={false}
              className="block w-full rounded-lg px-3 py-2.5 text-left text-sm hover:bg-teal-50"
              onClick={() => {
                onChange(city)
                setQuery([city.name, city.region, city.country].filter(Boolean).join(", "))
                setOptions([])
              }}>
              <span className="block font-semibold text-slate-900">{city.name}</span>
              <span className="text-xs text-slate-500">{[city.region, city.country].filter(Boolean).join(", ")}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function TripForm({ onSubmit, busy }: {
  onSubmit: (request: PlanTripRequest) => Promise<void>
  busy: boolean
}) {
  const [origin, setOrigin] = useState<ResolvedLocation | null>(null)
  const [destination, setDestination] = useState<ResolvedLocation | null>(null)
  const [departure, setDeparture] = useState(dateAfter(35))
  const [returnDate, setReturnDate] = useState(dateAfter(39))
  const [arrivalTime, setArrivalTime] = useState("")
  const [departureTime, setDepartureTime] = useState("")
  const [travelers, setTravelers] = useState(2)
  const [rooms, setRooms] = useState(1)
  const [budget, setBudget] = useState(2000)
  const [pace, setPace] = useState<PlanTripRequest["travel_pace"]>("Balanced")
  const [interests, setInterests] = useState<string[]>(["Culture", "Food"])
  const [preferences, setPreferences] = useState("")
  const [flightAllowance, setFlightAllowance] = useState("")
  const [hotelAllowance, setHotelAllowance] = useState("")
  const [formError, setFormError] = useState("")

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!origin || !destination) {
      setFormError("Choose both cities from the search suggestions.")
      return
    }
    if (origin.id === destination.id || departure >= returnDate) {
      setFormError("Choose different cities and a return date after departure.")
      return
    }
    const nights = Math.round((Date.parse(returnDate) - Date.parse(departure)) / 86_400_000)
    if (nights > 13) {
      setFormError("Trips can be up to 13 hotel nights.")
      return
    }
    setFormError("")
    void onSubmit({
      origin, destination, departure_date: departure, return_date: returnDate,
      travelers, rooms, total_budget_usd: budget,
      interests: interests.map((interest) => interest.toLowerCase()),
      travel_pace: pace, additional_preferences: preferences,
      arrival_time: arrivalTime || null, departure_time: departureTime || null,
      optional_cost_allowances: {
        flights_usd: flightAllowance ? Number(flightAllowance) : null,
        hotel_usd: hotelAllowance ? Number(hotelAllowance) : null,
      },
    })
  }

  return (
    <Card className="relative z-10 mx-auto w-full max-w-6xl overflow-visible p-5 sm:p-7 lg:p-9">
      <div className="mb-6 flex items-center gap-2 text-sm font-bold text-teal-700">
        <Search size={17} /> Design your trip
      </div>
      <form onSubmit={submit} className="space-y-6">
        <div className="grid gap-5 md:grid-cols-2">
          <CityPicker label="Flying from" value={origin} onChange={setOrigin} />
          <CityPicker label="Going to" value={destination} onChange={setDestination} />
        </div>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="form-label" htmlFor="departure">Departure</label>
            <div className="relative">
              <input id="departure" type="date" className="field" value={departure} min={dateAfter(0)} onChange={(e) => setDeparture(e.target.value)} required />
            </div>
          </div>
          <div>
            <label className="form-label" htmlFor="return">Return</label>
            <div className="relative">
              <input id="return" type="date" className="field" value={returnDate} min={departure} onChange={(e) => setReturnDate(e.target.value)} required />
            </div>
          </div>
          <div>
            <label className="form-label" htmlFor="travelers">Travelers</label>
            <div className="relative"><Users size={17} className="field-icon" />
              <input id="travelers" type="number" className="field field-with-icon" min={1} max={8} value={travelers} onChange={(e) => setTravelers(Number(e.target.value))} required />
            </div>
          </div>
          <div>
            <label className="form-label" htmlFor="rooms">Rooms</label>
            <input id="rooms" type="number" className="field" min={1} max={8} value={rooms} onChange={(e) => setRooms(Number(e.target.value))} required />
          </div>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <div><label className="form-label" htmlFor="arrival-time">Arrival time in destination (optional)</label>
            <input id="arrival-time" type="time" className="field" value={arrivalTime} onChange={(event) => setArrivalTime(event.target.value)} />
          </div>
          <div><label className="form-label" htmlFor="departure-time">Departure time from destination (optional)</label>
            <input id="departure-time" type="time" className="field" value={departureTime} onChange={(event) => setDepartureTime(event.target.value)} />
          </div>
          <p className="text-xs text-slate-500 sm:col-span-2">Use local destination times. Leave blank if your travel schedule is unknown; first and final day plans will be provisional.</p>
        </div>
        <div className="grid gap-5 md:grid-cols-[1fr_1fr]">
          <div>
            <label className="form-label" htmlFor="budget">Total trip budget · USD</label>
            <div className="relative"><span className="field-icon text-lg font-bold">$</span>
              <input id="budget" type="number" className="field field-with-icon" min={1} max={1000000} step={1} value={budget} onChange={(e) => setBudget(Number(e.target.value))} required />
            </div>
          </div>
          <div>
            <label className="form-label" htmlFor="pace">Your travel pace</label>
            <select id="pace" className="field" value={pace} onChange={(e) => setPace(e.target.value as PlanTripRequest["travel_pace"])}>
              <option>Relaxed</option><option>Balanced</option><option>Adventurous</option>
            </select>
          </div>
        </div>
        <div>
          <span className="form-label">What are you interested in?</span>
          <div className="flex flex-wrap gap-2">
            {INTERESTS.map((interest) => (
              <button key={interest} type="button"
                aria-pressed={interests.includes(interest)}
                className={`interest-chip ${interests.includes(interest) ? "interest-chip-active" : ""}`}
                onClick={() => setInterests((current) => current.includes(interest) ? current.filter((value) => value !== interest) : [...current, interest])}>
                {interest}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="form-label" htmlFor="preferences">Anything else we should know?</label>
          <textarea id="preferences" className="field min-h-24 resize-y py-3" maxLength={300}
            placeholder="Art museums, easy walks, local food…" value={preferences}
            onChange={(e) => setPreferences(e.target.value)} />
        </div>
        <details className="rounded-xl bg-slate-50 px-4 py-3 text-sm">
          <summary className="cursor-pointer font-semibold text-slate-700">Have your own flight or hotel estimates? Add them here</summary>
          <p className="mt-2 text-xs text-slate-500">For routes without sample offers, these are your allowances, not provider prices.</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div><label className="form-label" htmlFor="flights-allowance">Group flight allowance · USD</label>
              <input id="flights-allowance" type="number" className="field" min={0} value={flightAllowance} onChange={(e) => setFlightAllowance(e.target.value)} placeholder="Optional" />
            </div>
            <div><label className="form-label" htmlFor="hotel-allowance">Whole-stay hotel allowance · USD</label>
              <input id="hotel-allowance" type="number" className="field" min={0} value={hotelAllowance} onChange={(e) => setHotelAllowance(e.target.value)} placeholder="Optional" />
            </div>
          </div>
        </details>
        {formError && <p className="text-sm font-medium text-rose-700" role="alert">{formError}</p>}
        <div className="flex flex-col items-start justify-between gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:items-center">
          <p className="max-w-xl text-xs leading-relaxed text-slate-500">Sample flight and hotel offers are simulated and non-bookable. Global city planning uses public geographic data and may have unknown costs.</p>
          <Button type="submit" size="lg" disabled={busy} className="w-full shrink-0 sm:w-auto">
            {busy ? "Planning…" : "Plan My Trip"} <ArrowRight size={17} />
          </Button>
        </div>
      </form>
    </Card>
  )
}
