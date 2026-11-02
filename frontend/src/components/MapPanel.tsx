import { useEffect, useRef, useState } from "react"
import * as maplibregl from "maplibre-gl"
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"
import { MapPin } from "lucide-react"
import type { TripPlanResponse } from "@/types/api"
import { Card } from "@/components/ui/card"

maplibregl.setWorkerUrl(mapWorkerUrl)

export function MapPanel({ plan }: { plan: TripPlanResponse }) {
  const container = useRef<HTMLDivElement>(null)
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "error">("loading")
  const points = plan.daily_itinerary.flatMap((day) =>
    day.slots.filter((slot) =>
      slot.verified_place && slot.latitude != null && slot.longitude != null),
  )

  useEffect(() => {
    if (!container.current) return
    const center = plan.trip_summary.destination
    const map = new maplibregl.Map({
      container: container.current,
      style: "https://tiles.openfreemap.org/styles/bright",
      center: [center.longitude, center.latitude],
      zoom: 11,
      attributionControl: { compact: false },
    })
    map.on("load", () => setMapStatus("ready"))
    map.on("error", () => setMapStatus("error"))
    map.addControl(new maplibregl.NavigationControl(), "top-right")
    const bounds = new maplibregl.LngLatBounds()
    for (const point of points) {
      const coordinate: [number, number] = [point.longitude!, point.latitude!]
      bounds.extend(coordinate)
      new maplibregl.Marker({ color: "#0c7f81" })
        .setLngLat(coordinate)
        .setPopup(new maplibregl.Popup({ offset: 20 }).setText(point.title))
        .addTo(map)
    }
    if (points.length > 1) map.fitBounds(bounds, { padding: 50, maxZoom: 13 })
    return () => map.remove()
  }, [plan])

  return (
    <Card className="overflow-hidden">
      <div className="p-6">
        <div className="flex items-center gap-2 text-slate-900"><MapPin className="text-teal-700" size={21} /><h3 className="text-xl font-bold">Explore your destination</h3></div>
        <p className="mt-1 text-sm text-slate-500">Only places with verified geographic coordinates appear here.</p>
      </div>
      <div ref={container} className="h-[360px] w-full" aria-label="Map of recommended attractions" />
      <p className="px-6 pt-3 text-sm text-slate-600" role="status">
        {mapStatus === "error" ? "Map tiles could not load. The place list and source links above remain available." :
          points.length === 0 ? "No verified place markers are available; the map is centered on the destination." :
          mapStatus === "loading" ? "Loading destination map…" : `${points.length} verified place marker(s) shown.`}
      </p>
      <p className="px-6 py-3 text-xs text-slate-500">Map tiles © OpenFreeMap / OpenMapTiles · Map data © OpenStreetMap contributors{plan.data_sources.includes("WIKIPEDIA_GEOSEARCH") && <> · Place details © <a href="https://en.wikipedia.org/" target="_blank" rel="noreferrer" className="underline">Wikipedia contributors</a></>}</p>
    </Card>
  )
}
