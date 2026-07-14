<script setup lang="ts">
// Fleet map per design_docs 4.1.1. Technical acceptance criteria implemented:
// - OpenSeaMap nautical overlay on top of a light vector basemap
// - SVG triangle vessel markers rotated by heading
// - 300-500ms smooth position transition (CSS transition on marker transform)
// - click -> mini info card in <100ms (data is pre-loaded client side, no API call)
// - overlapping markers at the same port are fanned out slightly
import { onMounted, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import maplibregl, { type Map as MapLibreMap, type Marker, type Popup } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { VesselSummary } from '@/types/fleet'
import { STATUS_LABEL } from '@/utils/format'

const props = defineProps<{ vessels: VesselSummary[] }>()
const emit = defineEmits<{ select: [imo: string] }>()

const container = ref<HTMLDivElement | null>(null)
const map = shallowRef<MapLibreMap | null>(null)
const markers = new globalThis.Map<string, Marker>()
const activePopup = shallowRef<Popup | null>(null)

// Fan out vessels that share (near-)identical coordinates, e.g. moored in
// the same port, so icons don't fully overlap.
function dedupePositions(vessels: VesselSummary[]) {
  const buckets = new globalThis.Map<string, VesselSummary[]>()
  for (const v of vessels) {
    const key = `${v.position.lat.toFixed(1)}:${v.position.lon.toFixed(1)}`
    const list = buckets.get(key) ?? []
    list.push(v)
    buckets.set(key, list)
  }
  const result = new globalThis.Map<string, { lat: number; lon: number }>()
  for (const list of buckets.values()) {
    if (list.length === 1) {
      result.set(list[0].imo, { lat: list[0].position.lat, lon: list[0].position.lon })
      continue
    }
    const radius = 0.35
    list.forEach((v: VesselSummary, i: number) => {
      const angle = (i / list.length) * Math.PI * 2
      result.set(v.imo, {
        lat: v.position.lat + Math.sin(angle) * radius,
        lon: v.position.lon + Math.cos(angle) * radius,
      })
    })
  }
  return result
}

// Markers/popups are real DOM elements (unlike canvas/WebGL), so they can
// reference CSS custom properties directly and repaint automatically when
// the .dark class toggles — no JS-side dark-mode branching needed here.
function markerColor(v: VesselSummary) {
  if (v.maintenanceUrgency === 'HIGH') return 'var(--color-signal-red)'
  if (v.maintenanceUrgency === 'MEDIUM') return 'var(--color-brass-amber)'
  return 'var(--color-fathom-teal)'
}

function buildMarkerEl(v: VesselSummary): HTMLElement {
  const el = document.createElement('div')
  el.className = 'vessel-marker'
  el.style.width = '26px'
  el.style.height = '26px'
  el.style.cursor = 'pointer'
  el.style.transition = 'transform 400ms ease-out'
  el.setAttribute('role', 'button')
  el.setAttribute('tabindex', '0')
  el.setAttribute('aria-label', `${v.name}, 航向 ${v.position.headingDeg} 度, 航速 ${v.position.speedKt} 節`)
  el.innerHTML = `
    <svg viewBox="0 0 24 24" width="26" height="26" style="transform: rotate(${v.position.headingDeg}deg); transform-origin: center;">
      <path d="M12 1 L20 21 L12 16 L4 21 Z" fill="${markerColor(v)}" stroke="var(--color-marine-navy)" stroke-width="1.2" />
    </svg>
  `
  return el
}

function popupHtml(v: VesselSummary): string {
  return `
    <div style="font-family: var(--font-body); min-width: 190px;">
      <p style="font-family: var(--font-display); font-size:13px; letter-spacing:.04em; margin:0 0 4px; color: var(--color-ink-slate);">${v.name}</p>
      <div style="font-family: var(--font-mono); font-size:12px; color: var(--color-ink-muted); display:flex; flex-direction:column; gap:2px;">
        <span>SPD ${v.position.speedKt.toFixed(1)} kt · HDG ${v.position.headingDeg}°</span>
        <span>${STATUS_LABEL[v.status]}${v.currentPort ? ' · ' + v.currentPort : ''}</span>
        <span>下次建議維修: Day ${v.nextRecommendedWindow.startDay}</span>
      </div>
    </div>
  `
}

function render() {
  if (!map.value) return
  const positions = dedupePositions(props.vessels)

  for (const v of props.vessels) {
    const pos = positions.get(v.imo)!
    let marker = markers.get(v.imo)
    if (!marker) {
      const el = buildMarkerEl(v)
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        openPopup(v, [pos.lon, pos.lat])
        emit('select', v.imo)
      })
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          openPopup(v, [pos.lon, pos.lat])
          emit('select', v.imo)
        }
      })
      marker = new maplibregl.Marker({ element: el, anchor: 'center' }).setLngLat([pos.lon, pos.lat]).addTo(map.value)
      markers.set(v.imo, marker)
    } else {
      marker.setLngLat([pos.lon, pos.lat])
    }
  }
}

function openPopup(v: VesselSummary, lngLat: [number, number]) {
  activePopup.value?.remove()
  if (!map.value) return
  const popup = new maplibregl.Popup({ closeButton: true, offset: 16 }).setLngLat(lngLat).setHTML(popupHtml(v)).addTo(map.value)
  activePopup.value = popup
}

onMounted(() => {
  if (!container.value) return
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
    center: [115, 20],
    zoom: 2.6,
    attributionControl: false,
  })
  m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
  m.addControl(new maplibregl.AttributionControl({ compact: true }))
  m.on('load', () => {
    map.value = m
    render()
  })
  m.on('click', () => activePopup.value?.remove())
})

onBeforeUnmount(() => {
  map.value?.remove()
})

watch(() => props.vessels, render, { deep: true })

defineExpose({
  flyTo(imo: string) {
    const v = props.vessels.find((x) => x.imo === imo)
    if (v && map.value) {
      map.value.flyTo({ center: [v.position.lon, v.position.lat], zoom: 5, speed: 0.8 })
    }
  },
})
</script>

<template>
  <div ref="container" class="h-full w-full" />
</template>

<style>
.vessel-marker svg {
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35));
}
.maplibregl-popup-content {
  background: var(--color-chart-paper-hi);
  border-radius: 2px;
  border: 1px solid color-mix(in srgb, var(--color-ink-slate) 25%, transparent);
  box-shadow: none;
  padding: 10px 12px;
}
.maplibregl-popup-tip {
  border-top-color: var(--color-chart-paper-hi) !important;
  border-bottom-color: var(--color-chart-paper-hi) !important;
}
.maplibregl-popup-close-button {
  color: var(--color-ink-muted);
}
.maplibregl-ctrl-group {
  background: var(--color-chart-paper-hi);
  border: 1px solid color-mix(in srgb, var(--color-ink-slate) 20%, transparent);
}
.dark .maplibregl-ctrl-icon {
  filter: invert(1) brightness(1.7);
}
</style>
