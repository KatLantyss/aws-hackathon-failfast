<script setup lang="ts">
// Single-vessel focused map for the Vessel Overview page (design_docs 4.3
// "目前位置"). Reuses the same OpenSeaMap + rotated SVG marker approach as
// FleetMap, but centers and zooms on one vessel instead of showing the whole
// fleet.
import { onMounted, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import maplibregl, { type Map as MapLibreMap, type Marker } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { VesselSummary } from '@/types/fleet'

const props = defineProps<{ vessel: VesselSummary }>()

const container = ref<HTMLDivElement | null>(null)
const map = shallowRef<MapLibreMap | null>(null)
const marker = shallowRef<Marker | null>(null)

// Marker is a real DOM element, so CSS custom properties resolve and repaint
// automatically when the .dark class toggles — no JS-side branching needed.
function markerColor(v: VesselSummary) {
  if (v.maintenanceUrgency === 'HIGH') return 'var(--color-signal-red)'
  if (v.maintenanceUrgency === 'MEDIUM') return 'var(--color-brass-amber)'
  return 'var(--color-fathom-teal)'
}

function buildMarkerEl(v: VesselSummary): HTMLElement {
  const el = document.createElement('div')
  el.style.width = '30px'
  el.style.height = '30px'
  el.setAttribute('role', 'img')
  el.setAttribute('aria-label', `${v.name} 目前位置, 航向 ${v.position.headingDeg} 度, 航速 ${v.position.speedKt} 節`)
  el.innerHTML = `
    <svg viewBox="0 0 24 24" width="30" height="30" style="transform: rotate(${v.position.headingDeg}deg); transform-origin: center; filter: drop-shadow(0 1px 3px rgba(0,0,0,0.4));">
      <path d="M12 1 L20 21 L12 16 L4 21 Z" fill="${markerColor(v)}" stroke="var(--color-marine-navy)" stroke-width="1.2" />
    </svg>
  `
  return el
}

function render() {
  if (!map.value) return
  const { lat, lon } = props.vessel.position
  if (!marker.value) {
    marker.value = new maplibregl.Marker({ element: buildMarkerEl(props.vessel), anchor: 'center' })
      .setLngLat([lon, lat])
      .addTo(map.value)
  } else {
    marker.value.setLngLat([lon, lat])
  }
  map.value.flyTo({ center: [lon, lat], zoom: map.value.getZoom() < 4 ? 5.5 : map.value.getZoom(), speed: 0.8 })
}

onMounted(() => {
  if (!container.value) return
  const { lat, lon } = props.vessel.position
  const m = new maplibregl.Map({
    container: container.value,
    style: {
      version: 8,
      sources: {
        osm: {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '© OpenStreetMap contributors',
        },
        openseamap: {
          type: 'raster',
          tiles: ['https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png'],
          tileSize: 256,
          attribution: '© OpenSeaMap contributors',
        },
      },
      layers: [
        { id: 'osm', type: 'raster', source: 'osm' },
        { id: 'openseamap', type: 'raster', source: 'openseamap' },
      ],
    },
    center: [lon, lat],
    zoom: 5.5,
    attributionControl: false,
  })
  m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
  m.addControl(new maplibregl.AttributionControl({ compact: true }))
  m.on('load', () => {
    map.value = m
    render()
  })
})

onBeforeUnmount(() => {
  map.value?.remove()
})

watch(() => props.vessel, render, { deep: true })
</script>

<template>
  <div ref="container" class="h-full w-full" />
</template>
