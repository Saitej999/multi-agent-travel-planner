import { useEffect, useState } from "react"
import { ArrowRight, Compass, Globe2, MapPinned, PlaneTakeoff, ShieldCheck, Sparkles } from "lucide-react"
import { startTrip, tripResult, tripStatus, updateTripBudget } from "@/lib/api"
import { TripForm } from "@/components/TripForm"
import { TripResults } from "@/components/TripResults"
import { Button } from "@/components/ui/button"
import type { BudgetEstimateRequest, JobStatus, PlanTripRequest, TripPlanResponse } from "@/types/api"

function progressLabel(event: NonNullable<JobStatus["progress"]>[number]) {
  const names: Record<string, string> = {
    flight_agent: "Flight search",
    hotel_agent: "Hotel search",
    itinerary_agent: "Itinerary planning",
    budget_agent: "Budget calculation",
    travel_coordinator: "Final recommendations",
  }
  const stage = names[event.agent] ?? event.agent.replaceAll("_", " ")
  if (event.event === "attractions_found") return `${event.count} named attractions found`
  if (event.event === "attractions_unavailable") return "No verified attractions available; itinerary coverage is incomplete"
  if (event.event === "final_response") return `${stage} completed`
  return `${stage}: ${event.tool ?? event.event} completed`
}

export default function App() {
  const [tripId, setTripId] = useState<string | null>(null)
  const [job, setJob] = useState<JobStatus | null>(null)
  const [plan, setPlan] = useState<TripPlanResponse | null>(null)
  const [error, setError] = useState("")
  const [lastRequest, setLastRequest] = useState<PlanTripRequest | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(request: PlanTripRequest) {
    setBusy(true)
    setError("")
    setPlan(null)
    setJob(null)
    setTripId(null)
    setLastRequest(request)
    try {
      const started = await startTrip(request)
      setJob(started)
      setTripId(started.trip_id)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The trip could not be started.")
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!tripId) return
    let active = true
    let timer: number | undefined
    async function poll() {
      try {
        const status = await tripStatus(tripId!)
        if (!active) return
        setJob(status)
        if (status.status === "failed") {
          setError(status.error?.message ?? "The planning workflow stopped.")
          setBusy(false)
          return
        }
        if (status.status === "completed") {
          const result = await tripResult(tripId!)
          if (active) { setPlan(result); setBusy(false) }
          return
        }
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "Could not check the trip status.")
          setBusy(false)
        }
        return
      }
      if (active) timer = window.setTimeout(poll, 1300)
    }
    void poll()
    return () => { active = false; if (timer) window.clearTimeout(timer) }
  }, [tripId])

  function reset() {
    setPlan(null)
    setJob(null)
    setTripId(null)
    setError("")
    setBusy(false)
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  async function reviseBudget(estimates: BudgetEstimateRequest) {
    if (!tripId) throw new Error("The trip job is no longer available. Plan the trip again.")
    setPlan(await updateTripBudget(tripId, estimates))
  }

  return <div className="min-h-screen bg-[#f8faf9]">
    <header className="border-b border-slate-200/80 bg-white/90">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
        <a href="/" className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-[#102d43]" onClick={(e) => { e.preventDefault(); reset() }}>
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#0c7f81] text-white"><Compass size={21} /></span>
          wayfinder<span className="text-[#0c7f81]">.</span>
        </a>
        <div className="flex items-center gap-4">
          <span className="hidden items-center gap-1.5 text-xs font-medium text-slate-500 sm:flex"><ShieldCheck size={15} className="text-teal-700" /> Clear sources, honest costs</span>
          <a href="#how-it-works" className="text-sm font-semibold text-slate-700 hover:text-teal-700">How it works</a>
        </div>
      </div>
    </header>

    {plan ? <TripResults plan={plan} onBack={reset} onRetry={lastRequest ? () => void submit(lastRequest) : undefined} onBudgetUpdate={reviseBudget} /> : <>
      <main>
        <section className="hero-grid relative overflow-hidden">
          <div className="pointer-events-none absolute -right-28 -top-48 h-[570px] w-[570px] rounded-full border-[70px] border-white/10" />
          <div className="pointer-events-none absolute -left-36 bottom-[-340px] h-[600px] w-[600px] rounded-full border-[70px] border-teal-300/10" />
          <div className="relative mx-auto max-w-7xl px-5 pb-36 pt-16 text-center text-white sm:px-8 sm:pt-20 lg:pb-44 lg:pt-24">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-1.5 text-xs font-bold tracking-wide text-teal-50"><Sparkles size={14} /> A SMARTER WAY TO EXPLORE</span>
            <h1 className="mx-auto mt-7 max-w-4xl text-4xl font-extrabold leading-[1.12] tracking-tight sm:text-6xl lg:text-7xl">Your Next Adventure,<br /><span className="text-[#98e5dc]">Planned by AI</span></h1>
            <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-slate-200 sm:text-lg">Discover incredible destinations and create personalized travel plans tailored to your interests and budget.</p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-x-7 gap-y-3 text-xs font-semibold text-slate-200 sm:text-sm">
              <span className="flex items-center gap-2"><Globe2 size={16} className="text-teal-200" /> Explore cities worldwide</span>
              <span className="flex items-center gap-2"><MapPinned size={16} className="text-teal-200" /> Verified places</span>
              <span className="flex items-center gap-2"><PlaneTakeoff size={16} className="text-teal-200" /> Transparent travel costs</span>
            </div>
          </div>
        </section>
        <div className="relative mx-auto -mt-24 max-w-7xl px-5 sm:px-8"><TripForm onSubmit={submit} busy={busy} /></div>

        {(busy || error) && <div className="section-wrap pt-8">
          {busy && <div className="rounded-2xl border border-teal-100 bg-white p-6 shadow-sm" role="status">
            <div className="flex items-center gap-3"><span className="h-5 w-5 animate-spin rounded-full border-[3px] border-teal-100 border-t-teal-700" />
              <div><p className="font-bold text-slate-900">Your trip is taking shape</p>
                <p className="text-sm text-slate-500">Status: {job?.status ?? "submitting"} · Updates below come from observed workflow events.</p>
              </div></div>
            {!!job?.progress?.length && <ul className="mt-4 space-y-2 border-t border-slate-100 pt-4 text-sm text-slate-700">
              {job.progress.map((event, index) => <li key={index} className="flex items-center gap-2"><ShieldCheck size={15} className="text-teal-700" />{progressLabel(event)}</li>)}
            </ul>}
          </div>}
          {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6" role="alert">
            <p className="font-bold text-rose-900">We couldn’t complete this plan</p>
            <p className="mt-1 text-sm text-rose-800">{error}</p>
            {lastRequest && <Button variant="outline" size="sm" className="mt-4" onClick={() => void submit(lastRequest)}>Try again <ArrowRight size={14} /></Button>}
          </div>}
        </div>}

        <section id="how-it-works" className="section-wrap pb-20 pt-20 text-center">
          <p className="eyebrow">A PLAN YOU CAN UNDERSTAND</p>
          <h2 className="text-3xl font-extrabold tracking-tight text-[#102d43] sm:text-4xl">Travel planning, made more thoughtful</h2>
          <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-slate-600">Five specialized stages collaborate through Google ADK. Gemini interprets your interests while Python grounds trip dates, retrieves data, and calculates costs.</p>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {[
              [Globe2, "Tell us your story", "Choose real cities, your dates, interests, pace, and budget."],
              [Compass, "Agents work together", "Flight, hotel, itinerary, budget, and coordinator stages share validated results."],
              [ShieldCheck, "Know what is real", "See simulated offers, verified attractions, your estimates, and unknown costs clearly labeled."],
            ].map(([Icon, title, text]) => {
              const FeatureIcon = Icon as typeof Globe2
              return <div key={title as string} className="rounded-2xl border border-slate-200 bg-white p-7 text-left shadow-sm"><span className="icon-tile"><FeatureIcon size={22} /></span>
                <h3 className="mt-5 text-lg font-bold text-slate-900">{title as string}</h3><p className="mt-2 text-sm leading-relaxed text-slate-600">{text as string}</p></div>
            })}
          </div>
        </section>
      </main>
    </>}
    <footer className="border-t border-slate-200 bg-white px-5 py-7 text-center text-xs text-slate-500">wayfinder. · A local AI engineering learning project · No bookings or live travel prices</footer>
  </div>
}
