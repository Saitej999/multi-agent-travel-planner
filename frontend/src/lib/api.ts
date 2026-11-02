import type { ApiError, JobStatus, PlanTripRequest, ResolvedLocation, TripPlanResponse } from "@/types/api"

const BASE = import.meta.env.VITE_API_BASE_URL ?? ""

export class TravelApiError extends Error {
  constructor(public code: string, message: string) {
    super(message)
    this.name = "TravelApiError"
  }
}

async function responseJson<T>(response: Response): Promise<T> {
  const body = await response.json()
  if (!response.ok) {
    if (response.status === 422) {
      throw new TravelApiError("invalid_request", "Check the dates, locations, and traveler details before planning.")
    }
    const error = body as ApiError
    throw new TravelApiError(error.code ?? "request_failed", error.message ?? "The travel service is unavailable.")
  }
  return body as T
}

export async function searchLocations(query: string, signal?: AbortSignal) {
  const response = await fetch(`${BASE}/api/locations/search?q=${encodeURIComponent(query)}`, { signal })
  return responseJson<ResolvedLocation[]>(response)
}

export async function startTrip(request: PlanTripRequest) {
  const response = await fetch(`${BASE}/api/trips/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  })
  return responseJson<JobStatus>(response)
}

export async function tripStatus(id: string) {
  const response = await fetch(`${BASE}/api/trips/${encodeURIComponent(id)}/status`)
  return responseJson<JobStatus>(response)
}

export async function tripResult(id: string) {
  const response = await fetch(`${BASE}/api/trips/${encodeURIComponent(id)}/result`)
  return responseJson<TripPlanResponse>(response)
}
