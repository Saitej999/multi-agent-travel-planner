import { useState, type FormEvent } from "react"
import { ArrowLeft, BedDouble, CalendarDays, ChevronDown, Clock3, Compass, DollarSign, MapPin, Plane, ShieldCheck, Sparkles, Users, Wallet } from "lucide-react"
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { MapPanel } from "@/components/MapPanel"
import { money, shortDate } from "@/lib/utils"
import type { BudgetEstimateRequest, Price, TripPlanResponse } from "@/types/api"

const COLORS = ["#0b777c", "#329ba1", "#65b6b1", "#89c6c0", "#bbddd6"]

function priceText(price: Price) {
  return price.kind === "unknown" ? "Price unavailable" : money(price.amount_usd)
}

function sourceText(price: Price) {
  return {
    simulated: "Simulated demo price",
    user_estimate: "Your estimate",
    assumption: "Planning allowance",
    mixed_estimate: "Estimate based on your inputs",
    verified: "Verified provider price",
    unknown: "Unknown price",
  }[price.source]
}

function SectionTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text?: string }) {
  return <div className="mb-6"><p className="eyebrow">{eyebrow}</p><h2 className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">{title}</h2>{text && <p className="mt-2 text-sm text-slate-500">{text}</p>}</div>
}

function BudgetSection({ plan }: { plan: TripPlanResponse }) {
  const budget = plan.budget_breakdown
  const complete = budget.comparison_status === "complete"
  const estimateComplete = budget.comparison_status === "estimate_complete"
  const estimate = budget.estimate_based_total?.amount_usd
  const difference = budget.estimate_difference_usd
  const costs = budget.items.filter((item) => item.price.amount_usd != null)
    .map((item) => ({ name: item.label, amount: item.price.amount_usd ?? 0 }))
  const initial = budget.initial_total.amount_usd
  const optimized = budget.optimized_total.amount_usd
  const limit = budget.budget_limit_usd
  const displayedTotal = optimized ?? estimate
  const utilization = displayedTotal == null ? null : Math.round(displayedTotal / limit * 100)
  const ring = displayedTotal == null ? [] : [
    { name: "Planned", value: Math.min(displayedTotal, limit) },
    { name: "Available", value: Math.max(0, limit - displayedTotal) },
  ]

  return <section id="budget" className="section-wrap">
    <SectionTitle eyebrow="05 / THE NUMBERS" title={complete ? "Your optimized budget" : "Your travel budget"}
      text={complete ? "Python calculates every total and compares the original plan with the optimized one." : estimateComplete ? "Python combines your estimates with planning allowances. Actual prices may differ." : "Only supported amounts are added. Unknown travel or admission costs stay unknown."} />
    <div className={`grid gap-4 sm:grid-cols-2 ${complete ? "xl:grid-cols-4" : ""}`}>
      {(complete ? [
        ["Initial estimate", priceText(budget.initial_total), "Before optimization"],
        [complete ? "Optimized estimate" : "Known subtotal", complete ? priceText(budget.optimized_total) : priceText(budget.known_subtotal), complete ? "Current plan" : "Not a full trip total"],
        ["Amount saved", priceText(budget.savings), "Compared with the initial plan"],
        ["Remaining budget", priceText(budget.remaining), complete ? (budget.within_budget ? "Within your limit" : "Over your limit") : "Comparison unavailable"],
      ] : [
        [estimate == null ? "Partial budget estimate" : estimateComplete ? "Estimated trip cost" : "Estimate before admission", estimate == null ? priceText(budget.known_subtotal) : money(estimate), estimate == null ? "Known and user-entered amounts only" : "User estimates plus planning allowances"],
        ["Your budget", money(limit), "Your stated limit"],
        ...(difference == null ? [] : [["Estimated difference", money(difference), estimateComplete ? "Estimate-based comparison" : "Admission remains unknown"]]),
      ]).map(([label, value, note]) =>
        <Card key={label} className="p-5"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p><p className="mt-3 text-2xl font-extrabold text-[#102d43]">{value}</p><p className="mt-1 text-xs text-slate-500">{note}</p></Card>,
      )}
    </div>
    <div className="mt-5 grid gap-5 lg:grid-cols-2">
      <Card className="p-6">
        <h3 className="font-bold text-slate-900">Where the money goes</h3>
        <p className="mt-1 text-xs text-slate-500">Known and estimated amounts in USD</p>
        {costs.length > 0 && <div className="mt-5 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={costs} margin={{ top: 4, right: 8, left: -20, bottom: 30 }}>
              <CartesianGrid vertical={false} stroke="#e8eef0" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "#64748b" }} angle={-25} textAnchor="end" height={56} />
              <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
              <Tooltip formatter={(value) => money(Number(value))} />
              <Bar dataKey="amount" radius={[6, 6, 0, 0]}>{costs.map((_, index) => <Cell key={index} fill={COLORS[index % COLORS.length]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>}
      </Card>
      <Card className="p-6">
        <h3 className="font-bold text-slate-900">Budget comparison</h3>
        {complete && initial != null && optimized != null ? <>
          <div className="mt-5 h-36"><ResponsiveContainer width="100%" height="100%">
            <BarChart data={[{ name: "Initial", amount: initial }, { name: "Optimized", amount: optimized }]} layout="vertical" margin={{ left: 4, right: 8 }}>
              <XAxis type="number" hide /><YAxis type="category" dataKey="name" width={72} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(value) => money(Number(value))} />
              <Bar dataKey="amount" radius={[0, 7, 7, 0]}>{[0, 1].map((index) => <Cell key={index} fill={index ? "#0c7f81" : "#9bc7c6"} />)}</Bar>
            </BarChart>
          </ResponsiveContainer></div>
          <div className="mt-4 flex items-center gap-4 border-t border-slate-100 pt-4">
            <div className="h-28 w-28 shrink-0"><ResponsiveContainer width="100%" height="100%">
              <PieChart><Pie data={ring} dataKey="value" innerRadius={36} outerRadius={50} startAngle={90} endAngle={-270} stroke="none">
                <Cell fill="#0c7f81" /><Cell fill="#e2eeec" />
              </Pie></PieChart>
            </ResponsiveContainer></div>
            <div><p className="text-2xl font-extrabold text-slate-900">{utilization}%</p><p className="text-xs text-slate-500">of your {money(limit)} budget</p></div>
          </div>
        </> : estimate != null ? <div className="mt-5 flex items-center gap-4">
          <div className="h-28 w-28 shrink-0"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={ring} dataKey="value" innerRadius={36} outerRadius={50} stroke="none"><Cell fill="#0c7f81" /><Cell fill="#e2eeec" /></Pie></PieChart></ResponsiveContainer></div>
          <div><p className="text-2xl font-extrabold text-slate-900">{utilization}%</p><p className="text-xs text-slate-500">of {money(limit)} based on user estimates{estimateComplete ? "" : "; admission excluded"}</p></div>
        </div> : <div className="mt-6 rounded-xl bg-amber-50 p-5 text-sm leading-relaxed text-amber-900">
          {estimateComplete ? "Every major category has a user estimate or planning allowance. The comparison is estimate-based; taxes, fees, and actual prices may differ." :
            "Missing categories remain outside this comparison. No savings or complete affordability claim is made."}
        </div>}
      </Card>
    </div>
    {!complete && !estimateComplete && <p className="mt-5 text-sm text-slate-600">Missing costs: {budget.items.filter((item) => item.price.amount_usd == null).map((item) => item.label.toLowerCase()).join(", ")}.</p>}
    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      {budget.items.filter((item) => complete || item.price.amount_usd != null).map((item) => <div key={item.category} className="rounded-xl border border-slate-200 bg-white px-4 py-3">
        <p className="text-xs text-slate-500">{item.label}</p><p className="mt-1 font-bold text-slate-900">{priceText(item.price)}</p>
        <p className="mt-1 text-[11px] text-teal-700">{sourceText(item.price)}</p>
      </div>)}
    </div>
  </section>
}

function TravelOptions({ plan, onBudgetUpdate, onHotelSelect }: { plan: TripPlanResponse; onBudgetUpdate?: (value: BudgetEstimateRequest) => Promise<void>; onHotelSelect: (id: string) => void }) {
  const [flightCost, setFlightCost] = useState(plan.flight_allowance.amount_usd?.toString() ?? "")
  const [hotelCost, setHotelCost] = useState(plan.hotel_allowance.amount_usd?.toString() ?? "")
  const [hotelMode, setHotelMode] = useState<"nightly" | "whole">("whole")
  const [admissionCost, setAdmissionCost] = useState("")
  const [saving, setSaving] = useState(false)
  const [estimateError, setEstimateError] = useState("")
  async function saveEstimates(event: FormEvent) {
    event.preventDefault()
    if (!onBudgetUpdate) return
    setSaving(true)
    setEstimateError("")
    try {
      await onBudgetUpdate({
        flights_usd: flightCost === "" ? null : Number(flightCost),
        hotel_nightly_rate_usd: hotelMode === "nightly" && hotelCost !== "" ? Number(hotelCost) : null,
        hotel_whole_stay_usd: hotelMode === "whole" && hotelCost !== "" ? Number(hotelCost) : null,
        admission_usd: admissionCost === "" ? null : Number(admissionCost),
      })
    } catch (error) {
      setEstimateError(error instanceof Error ? error.message : "The estimate could not be updated.")
    } finally { setSaving(false) }
  }
  return <section className="section-wrap">
    <SectionTitle eyebrow="04 / THE ESSENTIALS" title="Travel and accommodation"
      text="All offers are shown with their real data status. Nothing here can be booked." />
    <div className="grid gap-5 lg:grid-cols-2">
      <Card className="p-6"><div className="flex items-center justify-between"><div className="flex items-center gap-3"><span className="icon-tile"><Plane size={22} /></span><h3 className="text-xl font-bold">Flights</h3></div><Badge>Round trip</Badge></div>
        {plan.flight_options.some((item) => item.source === "DUFFEL_TEST") ? <div className="mt-5 space-y-3">{plan.flight_options.map((item) => <div key={item.id} className="rounded-xl border border-teal-100 bg-teal-50/40 p-4">
          <p className="text-xs font-bold uppercase text-teal-800">Duffel developer test offer · Simulated and non-bookable</p>
          <p className="mt-2 font-bold text-slate-900">Operated by {item.airline}</p>
          <p className="mt-1 text-sm text-slate-600">{item.origin} → {item.destination} · {item.stops} connection(s) across the round trip</p>
          <p className="mt-1 text-sm text-slate-600">{item.departure_date} → {item.return_date} · {plan.trip_summary.travelers} traveler(s)</p>
          <p className="mt-2 font-bold text-[#102d43]">{priceText(item.group_round_trip)} <span className="text-xs font-normal">test total for the group</span></p>
        </div>)}</div> : plan.selected_flight ? <div className="mt-5"><p className="text-lg font-bold text-slate-900">{plan.selected_flight.airline}</p>
          <p className="mt-1 text-sm text-slate-600">{plan.selected_flight.origin} → {plan.selected_flight.destination} · {plan.selected_flight.stops} stop(s)</p>
          <p className="mt-5 text-2xl font-extrabold text-[#102d43]">{priceText(plan.selected_flight.group_round_trip)}</p>
          <p className="mt-1 text-xs font-semibold text-amber-700">Simulated demonstration data · Non-bookable</p>
        </div> : <div className="mt-5"><p className="font-semibold text-slate-800">No verified flight offer available</p>
          <p className="mt-1 text-sm text-slate-500">Live flight pricing is unavailable. Add your estimated round-trip group cost below.</p>
          {plan.flight_provider_note && <p className="mt-2 text-xs text-amber-800">{plan.flight_provider_note}</p>}
          {plan.flight_allowance.amount_usd != null && <p className="mt-4 text-sm">Your group flight estimate: <strong>{priceText(plan.flight_allowance)}</strong></p>}
        </div>}
        {!!plan.flight_options.length && <div className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-500">{plan.flight_options.length} simulated option(s) returned by the Python tool. Test fares are excluded from budget totals.</div>}
      </Card>
      <Card className="p-6"><div className="flex items-center justify-between"><div className="flex items-center gap-3"><span className="icon-tile"><BedDouble size={22} /></span><h3 className="text-xl font-bold">Stay</h3></div><Badge>{plan.trip_summary.nights} nights</Badge></div>
        {plan.hotel_options.some((item) => item.source === "OPENSTREETMAP_OVERPASS") ? <div className="mt-5 max-h-[420px] space-y-3 overflow-y-auto">{plan.hotel_options.map((item) => <div key={item.id} className="rounded-xl border border-slate-200 p-4">
          <p className="font-bold text-slate-900">{item.name}</p>
          <p className="mt-1 text-sm capitalize text-slate-600">{item.category.replaceAll("_", " ")} · {item.city}</p>
          <p className="mt-1 text-xs text-slate-500">OpenStreetMap location · Price, rating, and availability unverified</p>
          <div className="mt-2 flex gap-4 text-sm"><button type="button" className="font-semibold text-teal-700 underline" onClick={() => { onHotelSelect(item.id); document.getElementById("destination-map")?.scrollIntoView({ behavior: "smooth", block: "center" }) }}>View on map</button>
            {item.source_url && <a href={item.source_url} target="_blank" rel="noreferrer" className="font-semibold text-teal-700 underline">OpenStreetMap source</a>}</div>
        </div>)}</div> : plan.selected_hotel ? <div className="mt-5"><p className="text-lg font-bold text-slate-900">{plan.selected_hotel.name}</p>
          <p className="mt-1 text-sm text-slate-600">{plan.selected_hotel.city} · {plan.selected_hotel.nights} nights</p>
          <p className="mt-5 text-2xl font-extrabold text-[#102d43]">{priceText(plan.selected_hotel.whole_stay)}</p>
          <p className="mt-1 text-xs font-semibold text-amber-700">Simulated demonstration data · Non-bookable</p>
        </div> : <div className="mt-5"><p className="font-semibold text-slate-800">No verified hotel offer available</p>
          <p className="mt-1 text-sm text-slate-500">Live hotel pricing is unavailable. Add a nightly rate or whole-stay estimate below.</p>
          {plan.hotel_provider_note && <p className="mt-2 text-xs text-amber-800">{plan.hotel_provider_note}</p>}
          {plan.hotel_allowance.amount_usd != null && <p className="mt-4 text-sm">Your hotel estimate for the stay: <strong>{priceText(plan.hotel_allowance)}</strong></p>}
        </div>}
        {!!plan.hotel_options.length && <div className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-500">{plan.hotel_options.length} {plan.hotel_options[0].source === "SYNTHETIC_DEMO" ? "simulated option(s)" : "source-backed property location(s)"} returned by the Python tool.</div>}
      </Card>
    </div>
    {plan.attraction_data.status !== "not_applicable" && onBudgetUpdate && <Card className="mt-5 p-5 sm:p-6">
      <h3 className="font-bold text-slate-900">Add your cost estimates</h3>
      <p className="mt-1 text-sm text-slate-500">These are user-provided estimates, never verified prices. Updating them recalculates the budget in Python without rerunning AI planning.</p>
      <form onSubmit={(event) => void saveEstimates(event)} className="mt-5 grid gap-4 sm:grid-cols-2">
        <div><label className="form-label" htmlFor="result-flight-cost">Round-trip flights for your group · USD</label>
          <input id="result-flight-cost" type="number" min="0" step="0.01" className="field" value={flightCost} onChange={(event) => setFlightCost(event.target.value)} placeholder="Your estimate" /></div>
        <div><label className="form-label" htmlFor="result-hotel-mode">Hotel estimate type</label>
          <select id="result-hotel-mode" className="field" value={hotelMode} onChange={(event) => setHotelMode(event.target.value as "nightly" | "whole")}>
            <option value="whole">Whole stay</option><option value="nightly">Per room per night</option>
          </select></div>
        <div><label className="form-label" htmlFor="result-hotel-cost">{hotelMode === "nightly" ? "Rate per room per night · USD" : "Whole-stay hotel cost · USD"}</label>
          <input id="result-hotel-cost" type="number" min="0" step="0.01" className="field" value={hotelCost} onChange={(event) => setHotelCost(event.target.value)} placeholder="Your estimate" />
          {hotelMode === "nightly" && <p className="mt-1 text-xs text-slate-500">Applied to {plan.trip_summary.rooms} room(s) × {plan.trip_summary.nights} night(s).</p>}</div>
        <div><label className="form-label" htmlFor="result-admission-cost">Total activities and admission · USD (optional)</label>
          <input id="result-admission-cost" type="number" min="0" step="0.01" className="field" value={admissionCost} onChange={(event) => setAdmissionCost(event.target.value)} placeholder="Leave unknown" /></div>
        {estimateError && <p className="text-sm text-rose-700 sm:col-span-2" role="alert">{estimateError}</p>}
        <Button type="submit" disabled={saving} className="sm:col-span-2 sm:w-fit">{saving ? "Updating budget…" : "Update budget without AI"}</Button>
      </form>
    </Card>}
  </section>
}

function Itinerary({ plan, onSelect }: { plan: TripPlanResponse; onSelect: (id: string) => void }) {
  const categoryIcon = (category: string) => category.includes("food") ? "🍽️" : category.includes("park") || category.includes("outdoor") ? "🌿" : category.includes("museum") || category.includes("culture") ? "🏛️" : "📍"
  return <section id="itinerary" className="section-wrap">
    <SectionTitle eyebrow="02 / YOUR DAYS" title={plan.attraction_data.status === "insufficient_data" ? "Itinerary incomplete" : "Your personalized itinerary"} text={plan.attraction_data.status === "insufficient_data" ? "Verified attractions were unavailable. Retry later to build a place-based itinerary." : "Source-backed places are grouped by day. First and final day plans are provisional when travel times are unknown."} />
    {plan.attraction_data.status === "insufficient_data" ? null : <>
    <div className="space-y-3">
      {plan.daily_itinerary.map((day) => <details key={day.day} className="group overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm" open={day.day === 1}>
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-5 sm:px-7">
          <div className="flex items-center gap-4"><span className="flex h-12 w-12 items-center justify-center rounded-xl bg-teal-50 font-extrabold text-teal-800">{String(day.day).padStart(2, "0")}</span>
            <div><p className="font-bold text-slate-900">Day {day.day} <span className="font-normal text-slate-500">· {shortDate(day.date)}</span></p>
              <p className="mt-0.5 text-xs text-slate-500">{day.slots.filter((slot) => slot.verified_place).length} verified place(s)</p>
            </div></div>
          <ChevronDown size={20} className="text-slate-500 transition-transform group-open:rotate-180" />
        </summary>
        {day.note && <p className="border-t border-slate-100 px-5 pt-3 text-xs text-amber-800 sm:px-7">{day.note}</p>}
        <div className="grid gap-0 border-t border-slate-100 px-5 py-2 sm:px-7 lg:grid-cols-3">
          {day.slots.length === 0 && <p className="py-5 text-sm text-slate-500">No verified place available for this day.</p>}
          {day.slots.map((slot) => <div key={slot.period} className="relative border-b border-slate-100 py-5 last:border-0 lg:border-b-0 lg:pr-5">
            <p className="text-[11px] font-extrabold uppercase tracking-[.15em] text-teal-700">{slot.period}</p>
            <p className="mt-2 font-bold text-slate-900">{categoryIcon(slot.category)} {slot.attraction_id ? <button type="button" className="text-left underline-offset-4 hover:text-teal-700 hover:underline" onClick={() => { onSelect(slot.attraction_id!); document.getElementById("destination-map")?.scrollIntoView({ behavior: "smooth", block: "center" }) }}>{slot.title}</button> : slot.title}</p>
            <p className="mt-2 text-xs leading-relaxed text-slate-500">{slot.description || (slot.verified_place ? "Named place from a geographic source." : "Flexible planning suggestion.")}</p>
            <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
              {slot.duration_minutes && <span className="flex items-center gap-1"><Clock3 size={13} /> About {slot.duration_minutes} min</span>}
              <span>{slot.verified_place ? slot.source === "WIKIPEDIA_GEOSEARCH" ? "Wikipedia place" : "OpenStreetMap place" : slot.source === "SYNTHETIC_DEMO" ? "Illustrative demo idea" : "General suggestion"}</span>
              {slot.source_url && <a href={slot.source_url} target="_blank" rel="noreferrer" className="font-semibold text-teal-700 underline">View place source</a>}
            </div>
          </div>)}
        </div>
      </details>)}
    </div>
    <p className="mt-4 text-xs text-slate-500">Opening hours, travel times, crowds, and admission are not verified. Confirm before visiting.</p>
    </>}
  </section>
}

export function TripResults({ plan, onBack, onRetry, onBudgetUpdate }: { plan: TripPlanResponse; onBack: () => void; onRetry?: () => void; onBudgetUpdate?: (value: BudgetEstimateRequest) => Promise<void> }) {
  const [diagnostics, setDiagnostics] = useState(false)
  const [selectedAttractionId, setSelectedAttractionId] = useState<string | null>(null)
  const [selectedHotelId, setSelectedHotelId] = useState<string | null>(null)
  const trip = plan.trip_summary
  return <div className="pb-20">
    <div className="section-wrap pt-10">
      <Button variant="ghost" onClick={onBack} className="mb-6 pl-0"><ArrowLeft size={16} /> Plan another trip</Button>
      <p className="eyebrow">YOUR PERSONAL TRAVEL PLAN</p>
      <h1 className="max-w-4xl text-3xl font-extrabold tracking-tight text-[#102d43] sm:text-5xl">A fresh perspective on {trip.destination.name}</h1>
      <p className="mt-4 max-w-2xl text-slate-600">A plan shaped around your time, interests, and budget—with every data source clearly labeled.</p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          [MapPin, "The journey", `${trip.origin.name} → ${trip.destination.name}`, `${trip.destination.region}, ${trip.destination.country}`],
          [CalendarDays, "Your dates", `${shortDate(trip.departure_date)} – ${shortDate(trip.return_date)}`, `${trip.days} days · ${trip.nights} nights`],
          [Users, "Your people", `${trip.travelers} traveler${trip.travelers === 1 ? "" : "s"}`, `${trip.rooms} room${trip.rooms === 1 ? "" : "s"}`],
          [Wallet, "Your budget", money(trip.total_budget_usd), `${trip.travel_pace} pace`],
        ].map(([Icon, label, value, note]) => {
          const IconComponent = Icon as typeof MapPin
          return <Card key={label as string} className="p-5"><IconComponent size={20} className="text-teal-700" /><p className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">{label as string}</p><p className="mt-1 font-bold text-slate-900">{value as string}</p><p className="mt-1 text-xs text-slate-500">{note as string}</p></Card>
        })}
      </div>
      {(trip.arrival_time || trip.departure_time) && <p className="mt-3 text-sm text-slate-600">Destination local times: arrival {trip.arrival_time ?? "unknown"} · departure {trip.departure_time ?? "unknown"}.</p>}
      {plan.attraction_data.status !== "not_applicable" &&
        <p className="mt-4 text-sm font-semibold text-slate-700" role="status">
          Attraction data: {plan.attraction_data.verified_count} verified place(s) · {plan.attraction_data.status === "partial" ? "Partial coverage" : plan.attraction_data.status === "insufficient_data" ? "Insufficient data" : "Complete for planned slots"}
        </p>}
      {onRetry && ["partial", "insufficient_data"].includes(plan.attraction_data.status) &&
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          Retry attraction discovery and planning
        </Button>}
    </div>
    <Itinerary plan={plan} onSelect={setSelectedAttractionId} />
    <div id="destination-map" className="section-wrap"><MapPanel plan={plan} selectedAttractionId={selectedAttractionId} selectedHotelId={selectedHotelId} /></div>
    <TravelOptions plan={plan} onBudgetUpdate={onBudgetUpdate} onHotelSelect={setSelectedHotelId} />
    <BudgetSection plan={plan} />
    <section className="section-wrap pt-0">
      <SectionTitle eyebrow="06 / TRIP INFORMATION" title="What to confirm before you go" />
      {plan.warnings.length > 0 && <div className="mb-5 rounded-xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-900" role="status">
        {plan.attraction_data.status === "not_applicable" ? plan.warnings[0] : <>
          <strong>{plan.attraction_data.status === "insufficient_data" ? "Planning incomplete." : plan.attraction_data.status === "partial" ? "Limited attraction coverage." : "Data limits."}</strong>{" "}
          {plan.attraction_data.status === "insufficient_data" ? "No verified places were found." : "Named places have source links, but current access and hours are unverified."} Flight, hotel, and admission amounts are shown according to their source above.
        </>}
      </div>}
      <Card className="p-6"><div className="flex items-center gap-3"><span className="icon-tile"><Sparkles size={21} /></span><div><h3 className="font-bold text-slate-900">How this plan came together</h3><p className="text-xs text-slate-500">Google ADK coordinated specialized stages with shared validated state.</p></div></div>
        <div className="mt-5 flex flex-wrap gap-2">
          {[["Flight", Plane], ["Hotel", BedDouble], ["Itinerary", Compass], ["Budget", DollarSign], ["Coordinator", ShieldCheck]].map(([name, Icon]) => {
            const StageIcon = Icon as typeof Plane
            return <span key={name as string} className="flex items-center gap-2 rounded-full border border-teal-100 bg-teal-50 px-3 py-1.5 text-xs font-semibold text-teal-800"><StageIcon size={14} />{name as string}</span>
          })}
        </div>
      </Card>
      <button className="mt-6 text-sm font-semibold text-slate-500 underline underline-offset-4 hover:text-teal-700" onClick={() => setDiagnostics((value) => !value)}>
        {diagnostics ? "Hide" : "Show"} developer diagnostics
      </button>
      {diagnostics && <Card className="mt-4 space-y-4 p-5 text-xs text-slate-700">
        <p><strong>Model:</strong> {plan.diagnostics.model} · <strong>Execution:</strong> {plan.diagnostics.execution_mode}</p>
        <div><strong>Agent timing (seconds)</strong><pre className="mt-2 overflow-x-auto rounded-lg bg-slate-50 p-3">{JSON.stringify(plan.diagnostics.timings, null, 2)}</pre></div>
        <div><strong>Observed ADK events</strong><pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-50 p-3">{JSON.stringify(plan.diagnostics.trace, null, 2)}</pre></div>
        <div><strong>Model requests</strong><pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-50 p-3">{JSON.stringify(plan.diagnostics.model_metrics, null, 2)}</pre></div>
        <div><strong>Geographic discovery</strong><pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-50 p-3">{JSON.stringify(plan.diagnostics.geographic_discovery, null, 2)}</pre></div>
      </Card>}
    </section>
  </div>
}
