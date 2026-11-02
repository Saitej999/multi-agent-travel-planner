import { useEffect, useRef, useState } from "react"
import * as maplibregl from "maplibre-gl"
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url"
import { MapPin } from "lucide-react"
import type { TripPlanResponse } from "@/types/api"
import { Card } from "@/components/ui/card"

maplibregl.setWorkerUrl(mapWorkerUrl)

export function MapPanel({ plan, selectedAttractionId, selectedHotelId }: { plan: TripPlanResponse; selectedAttractionId?: string | null; selectedHotelId?: string | null }) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const markers = useRef(new Map<string, maplibregl.Marker>())
  const hotelMarkers = useRef(new Map<string, maplibregl.Marker>())
  const [mapStatus, setMapStatus] = useState<"loading" | "ready" | "error">("loading")
  const points = plan.daily_itinerary.flatMap((day) =>
    day.slots.filter((slot) =>
      slot.verified_place && slot.latitude != null && slot.longitude != null),
  )
  const hotels = plan.hotel_options.filter((item) => item.source === "OPENSTREETMAP_OVERPASS" && item.latitude != null && item.longitude != null)

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
    mapRef.current = map
    markers.current.clear()
    hotelMarkers.current.clear()
    map.on("load", () => setMapStatus("ready"))
    map.on("error", () => setMapStatus("error"))
    map.addControl(new maplibregl.NavigationControl(), "top-right")
    const bounds = new maplibregl.LngLatBounds()
    for (const point of points) {
      const coordinate: [number, number] = [point.longitude!, point.latitude!]
      bounds.extend(coordinate)
      const marker = new maplibregl.Marker({ color: "#0c7f81" })
        .setLngLat(coordinate)
        .setPopup(new maplibregl.Popup({ offset: 20 }).setText(`${point.title} · ${point.source === "WIKIPEDIA_GEOSEARCH" ? "Wikipedia" : "OpenStreetMap"}`))
        .addTo(map)
      if (point.attraction_id) markers.current.set(point.attraction_id, marker)
    }
    for (const hotel of hotels) {
      const coordinate: [number, number] = [hotel.longitude!, hotel.latitude!]
      bounds.extend(coordinate)
      hotelMarkers.current.set(hotel.id, new maplibregl.Marker({ color: "#24436a" })
        .setLngLat(coordinate)
        .setPopup(new maplibregl.Popup({ offset: 20 }).setText(`${hotel.name} · OpenStreetMap hotel location; price and availability unknown`))
        .addTo(map))
    }
    if (points.length + hotels.length > 1) map.fitBounds(bounds, { padding: 50, maxZoom: 13 })
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(container.current)
    return () => { observer.disconnect(); markers.current.clear(); hotelMarkers.current.clear(); mapRef.current = null; map.remove() }
  }, [plan])

  useEffect(() => {
    if (!selectedAttractionId || !mapRef.current) return
    const marker = markers.current.get(selectedAttractionId)
    if (!marker) return
    mapRef.current.flyTo({ center: marker.getLngLat(), zoom: 14, essential: true })
    if (!marker.getPopup()?.isOpen()) marker.togglePopup()
  }, [selectedAttractionId, plan])

  useEffect(() => {
    if (!selectedHotelId || !mapRef.current) return
    const marker = hotelMarkers.current.get(selectedHotelId)
    if (!marker) return
    mapRef.current.flyTo({ center: marker.getLngLat(), zoom: 14, essential: true })
    if (!marker.getPopup()?.isOpen()) marker.togglePopup()
  }, [selectedHotelId, plan])

  return (
    <Card className="overflow-hidden">
      <div className="p-6">
        <p className="eyebrow">03 / EXPLORE</p>
        <div className="flex items-center gap-2 text-slate-900"><MapPin className="text-teal-700" size={21} /><h3 className="text-xl font-bold">Explore your destination</h3></div>
        <p className="mt-1 text-sm text-slate-500">Source-backed attraction and hotel locations appear here. Hotel prices and availability are unknown.</p>
      </div>
      <div ref={container} className="h-[360px] w-full" aria-label="Map of recommended attractions" />
      <p className="px-6 pt-3 text-sm text-slate-600" role="status">
        {mapStatus === "error" ? "Map tiles could not load. The place list and source links above remain available." :
          points.length + hotels.length === 0 ? "No source-backed place markers are available; the map is centered on the destination." :
          mapStatus === "loading" ? "Loading destination map…" : `${points.length} attraction and ${hotels.length} hotel marker(s) shown.`}
      </p>
      <p className="px-6 py-3 text-xs text-slate-500">Map tiles © OpenFreeMap / OpenMapTiles · Map data © OpenStreetMap contributors{plan.data_sources.includes("WIKIPEDIA_GEOSEARCH") && <> · Place details © <a href="https://en.wikipedia.org/" target="_blank" rel="noreferrer" className="underline">Wikipedia contributors</a></>}</p>
    </Card>
  )
}
