import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import App from "@/App"
import { TripForm } from "@/components/TripForm"
import { TripResults } from "@/components/TripResults"
import { searchLocations, startTrip, tripResult, tripStatus } from "@/lib/api"
import type { ResolvedLocation, TripPlanResponse } from "@/types/api"

vi.mock("@/lib/api", () => ({
  searchLocations: vi.fn(),
  startTrip: vi.fn(),
  tripStatus: vi.fn(),
  tripResult: vi.fn(),
}))
vi.mock("@/components/MapPanel", () => ({
  MapPanel: () => <div>Verified map component</div>,
}))

const chicago: ResolvedLocation = {
  id: 1, name: "Chicago", region: "Illinois", country: "United States",
  country_code: "US", latitude: 41.88, longitude: -87.63,
  timezone: "America/Chicago", source: "OPEN_METEO_GEOCODING",
}
const newYork: ResolvedLocation = {
  id: 2, name: "New York", region: "New York", country: "United States",
  country_code: "US", latitude: 40.71, longitude: -74,
  timezone: "America/New_York", source: "OPEN_METEO_GEOCODING",
}
const unknown = { amount_usd: null, kind: "unknown" as const, source: "unknown" as const }
const simulated = (amount: number) => ({
  amount_usd: amount, kind: "estimated" as const, source: "simulated" as const,
})

const plan: TripPlanResponse = {
  trip_summary: {
    origin: chicago, destination: newYork, departure_date: "2026-12-15",
    return_date: "2026-12-19", days: 5, nights: 4, travelers: 2,
    rooms: 1, total_budget_usd: 2000, travel_pace: "Balanced",
    interests: ["food", "culture"],
  },
  flight_options: [{
    id: "DEMO-F001", airline: "Example Air", origin: "ORD", destination: "JFK",
    stops: 0, group_round_trip: simulated(660), bookable: false,
  }],
  hotel_options: [{
    id: "DEMO-H001", name: "Example Hotel", city: "New York City",
    nights: 4, whole_stay: simulated(640), bookable: false,
  }],
  selected_flight: {
    id: "DEMO-F001", airline: "Example Air", origin: "ORD", destination: "JFK",
    stops: 0, group_round_trip: simulated(660), bookable: false,
  },
  selected_hotel: {
    id: "DEMO-H001", name: "Example Hotel", city: "New York City",
    nights: 4, whole_stay: simulated(640), bookable: false,
  },
  flight_allowance: unknown, hotel_allowance: unknown,
  daily_itinerary: Array.from({ length: 5 }, (_, index) => ({
    day: index + 1, date: `2026-12-${15 + index}`,
    slots: [
      { period: "morning", title: "Museum visit", category: "culture",
        description: "Illustrative activity", source: "SYNTHETIC_DEMO", verified_place: false },
      { period: "afternoon", title: "Flexible time", category: "general",
        description: "", source: "GENERAL_SUGGESTION", verified_place: false },
      { period: "evening", title: "Dinner or rest", category: "general",
        description: "", source: "GENERAL_SUGGESTION", verified_place: false },
    ],
  })),
  attractions: [],
  attraction_data: { status: "not_applicable", verified_count: 0, sources: [] },
  budget_breakdown: {
    items: [
      { category: "flights", label: "Round-trip flights", price: simulated(660) },
      { category: "hotel", label: "Hotel stay", price: simulated(640) },
      { category: "food", label: "Food", price: simulated(450) },
      { category: "ground_transport", label: "Ground transport", price: simulated(100) },
      { category: "activities", label: "Activities", price: simulated(140) },
    ],
    initial_total: simulated(2270), optimized_total: simulated(1990),
    known_subtotal: simulated(1990), savings: simulated(280),
    remaining: simulated(10), budget_limit_usd: 2000,
    comparison_status: "complete", within_budget: true, nights: 4,
  },
  optimization_summary: { triggered: true, explanation: "Changed hotel", outcome: "within_budget" },
  warnings: ["Flight and hotel offers are simulated and non-bookable."],
  data_sources: ["SYNTHETIC_DEMO"],
  diagnostics: {
    model: "gemini-2.5-flash", execution_mode: "GOOGLE_ADK_SEQUENTIAL_AGENTS",
    trace: [{ agent: "flight_agent", event: "tool_result", tool: "search_flights" }],
    agent_summary: [], timings: {}, model_metrics: [], tool_metrics: [],
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(searchLocations).mockImplementation(async (query) =>
    query.toLowerCase().includes("chicago") ? [chicago] : [newYork])
})

async function chooseCities() {
  fireEvent.change(screen.getByLabelText("Flying from"), { target: { value: "Chicago" } })
  fireEvent.click(await screen.findByRole("option", { name: /Chicago.*Illinois/i }))
  fireEvent.change(screen.getByLabelText("Going to"), { target: { value: "New York" } })
  fireEvent.click(await screen.findByRole("option", { name: /New York.*United States/i }))
}

describe("travel planning journey", () => {
  it("reserves icon spacing on city, date, traveler, and budget fields", () => {
    render(<TripForm onSubmit={vi.fn()} busy={false} />)
    for (const label of ["Flying from", "Going to", "Travelers", "Total trip budget · USD"]) {
      expect(screen.getByLabelText(label)).toHaveClass("field-with-icon")
    }
    for (const label of ["Departure", "Return"]) {
      expect(screen.getByLabelText(label)).toHaveAttribute("type", "date")
      expect(screen.getByLabelText(label)).not.toHaveClass("field-with-icon")
    }
    expect(screen.getByLabelText("Rooms")).not.toHaveClass("field-with-icon")
  })

  it("submits resolved cities and trip preferences through the generated contract", async () => {
    const submit = vi.fn().mockResolvedValue(undefined)
    render(<TripForm onSubmit={submit} busy={false} />)
    await chooseCities()
    fireEvent.change(screen.getByLabelText("Departure"), { target: { value: "2026-12-15" } })
    fireEvent.change(screen.getByLabelText("Return"), { target: { value: "2026-12-19" } })
    fireEvent.change(screen.getByLabelText("Total trip budget · USD"), { target: { value: "2000" } })
    fireEvent.change(screen.getByLabelText("Anything else we should know?"), { target: { value: "Museums and local food" } })
    const form = screen.getByRole("button", { name: /Plan My Trip/i }).closest("form")!
    expect(Array.from(form.elements).filter((element) => element instanceof HTMLInputElement && !element.checkValidity()).map((element) => (element as HTMLInputElement).id)).toEqual([])
    fireEvent.click(screen.getByRole("button", { name: /Plan My Trip/i }))
    await waitFor(() => expect(submit).toHaveBeenCalledOnce())
    const request = submit.mock.calls[0][0]
    expect(request.origin.id).toBe(chicago.id)
    expect(request.destination.id).toBe(newYork.id)
    expect(request.departure_date).toBe("2026-12-15")
    expect(request.return_date).toBe("2026-12-19")
    expect(request.travelers).toBe(2)
    expect(request.rooms).toBe(1)
    expect(request.total_budget_usd).toBe(2000)
    expect(request.interests).toEqual(["culture", "food"])
    expect(request.additional_preferences).toBe("Museums and local food")
  })

  it("renders structured budget data and hides diagnostics by default", () => {
    render(<TripResults plan={plan} onBack={() => {}} />)
    expect(screen.getByText("A fresh perspective on New York")).toBeInTheDocument()
    expect(screen.getAllByText("$1,990").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Simulated demonstration data · Non-bookable").length).toBe(2)
    expect(screen.queryByText("gemini-2.5-flash")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Show developer diagnostics/i }))
    expect(screen.getByText(/gemini-2.5-flash/)).toBeInTheDocument()
  })

  it("renders a partial global plan with Wikipedia attribution and retry", () => {
    const partial = structuredClone(plan)
    partial.selected_flight = null
    partial.selected_hotel = null
    partial.flight_options = []
    partial.hotel_options = []
    partial.data_sources = ["OPEN_METEO_GEOCODING", "WIKIPEDIA_GEOSEARCH"]
    partial.attraction_data = { status: "partial", verified_count: 1, sources: ["WIKIPEDIA_GEOSEARCH"] }
    partial.warnings = ["Only a few verified attractions are available; remaining itinerary slots are general suggestions."]
    partial.budget_breakdown.comparison_status = "partial"
    partial.budget_breakdown.initial_total = unknown
    partial.budget_breakdown.optimized_total = unknown
    partial.budget_breakdown.savings = unknown
    partial.budget_breakdown.remaining = unknown
    partial.budget_breakdown.known_subtotal = { amount_usd: 880, kind: "estimated", source: "assumption" }
    partial.daily_itinerary[0].slots[0] = {
      period: "morning", title: "Roman Museum", category: "museum", description: "",
      latitude: 41.9, longitude: 12.5, source: "WIKIPEDIA_GEOSEARCH", verified_place: true,
    }
    const retry = vi.fn()
    render(<TripResults plan={partial} onBack={() => {}} onRetry={retry} />)
    expect(screen.getByText("Wikipedia place")).toBeInTheDocument()
    expect(screen.getByText(/Attraction data: 1 verified place\(s\) · Partial coverage/)).toBeInTheDocument()
    expect(screen.getByText("No verified flight offer available")).toBeInTheDocument()
    expect(screen.getByText("Known subtotal")).toBeInTheDocument()
    expect(screen.getByText(/Limited attraction coverage/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: /Retry attraction discovery and planning/i }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it("connects form, job status, and completed result", async () => {
    vi.mocked(startTrip).mockResolvedValue({ trip_id: "job-1", status: "queued", progress: [], error: null })
    vi.mocked(tripStatus).mockResolvedValue({
      trip_id: "job-1", status: "completed",
      progress: [{ agent: "flight_agent", event: "tool_result", tool: "search_flights" }],
      error: null,
    })
    vi.mocked(tripResult).mockResolvedValue(plan)
    render(<App />)
    await chooseCities()
    fireEvent.click(screen.getByRole("button", { name: /Plan My Trip/i }))
    expect(await screen.findByText("A fresh perspective on New York")).toBeInTheDocument()
    expect(startTrip).toHaveBeenCalledOnce()
    expect(tripStatus).toHaveBeenCalledWith("job-1")
    expect(tripResult).toHaveBeenCalledWith("job-1")
  })
})
