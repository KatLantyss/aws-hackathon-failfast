# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
npm run dev       # start Vite dev server
npm run build     # type-check (vue-tsc -b) then production build
npm run preview   # preview the production build locally
```

There is no ESLint/Prettier/Vitest configured. `npm run build` runs `vue-tsc -b` first, so it's the way to catch type errors — always run it before considering a change complete. There is no test suite.

## Product context

**YangMing Fleet Operations Dashboard** — an internal fleet technical management platform for Yang Ming Marine Transport (陽明海運), built for a hackathon (AI 黑客松 FailFast). It gives fleet technical staff a single view into vessel condition, hull/propeller fouling, and fuel consumption to decide when to schedule drydock, hull cleaning, or propeller polishing.

Domain vocabulary:
- **Speed loss %** — reduction in speed vs. a clean-hull sea-trial baseline; the primary fouling proxy
- **Fouling grade** — `Clean | Light | Moderate | Heavy`, shown via the "fathometer" gauge
- **Noon Report** — daily vessel-reported position/speed/fuel/weather snapshot
- **UWI (Underwater Inspection)** — diver/ROV survey of hull and propeller condition
- **Fuel attribution** — decomposition of excess fuel consumption into weather / hull fouling / propeller fouling / engine degradation
- **Urgency** — `LOW | MEDIUM | HIGH`, derived from current speed loss

Core pages: fleet-wide overview map, vessel list, per-vessel Noon Reports, UWI inspections, **Speed Loss analysis** (trend + regression vs. clean baseline, cleaning-cycle comparison), **Fuel attribution** (waterfall/SHAP-style breakdown), **Maintenance advisor** (cost-benefit curve recommending a maintenance window), and cross-fleet analytics.

`design_docs/` is authoritative for product requirements, IA, and visual design tokens — consult it before UI/UX decisions, especially for Speed Loss, Fuel Attribution, and Maintenance Advisor, which have detailed interaction specs. `design_docs/theme.md` covers the brand color migration (navy/amber → Yang Ming red/black/white). Design language is a nautical-chart/ship-instrument aesthetic layered with Yang Ming's brand identity. **Brand red is for identity/interaction only** (logo, primary CTA, active nav) — functional status colors (fouling risk, anomaly flags, vessel status) must stay visually distinct from brand red so "brand decoration" is never confused with "actual data warning."

## Architecture

Vue 3 (Composition API, `<script setup lang="ts">` only — no Options API) + TypeScript + Vite, no global state library (no Pinia/Vuex). Page-level data is fetched per-view, not shared globally; if cross-view shared state becomes necessary, raise it before adding a state-management dependency.

- `src/main.ts` — bootstraps the app: creates it, installs router + echarts plugin.
- `src/App.vue` — root layout: decorative background scene layers + `AppHeader` + `<RouterView>`.
- `src/router/index.ts` — all routes in one file. `/vessels/:imo` is a layout route (`VesselLayout.vue`) with nested children (`overview`, `noon-reports`, `inspections`, `speed-loss`, `fuel-attribution`, `maintenance-advisor`); the bare `/vessels/:imo` path redirects to `overview`.
- `src/views/` — one component per route; `src/views/vessel/` holds the per-vessel nested views.
- `src/components/` — shared/presentational components used across views. `FathometerGauge` is a deliberate cross-page "signature" element (vertical fouling/risk gauge) — reuse it instead of building new gauge variants for similar risk displays.
- `src/composables/` — `useAppTheme` (dark mode via vueuse `useDark`, persisted to localStorage key `yangming-fleet-theme`), `useAsyncData` (loading/empty/error wrapper — use for any new data-fetching view instead of ad-hoc refs), `useChartTheme` (echarts tokens matching the design system), `useCountUp` (animated KPI numbers).
- `src/types/fleet.ts` — single source of truth for all domain data shapes.
- `src/utils/format.ts` — all number/date/currency formatting; don't inline formatting logic in components.
- `src/plugins/echarts.ts` — global echarts component/renderer registration, imported once in `main.ts`.

### Data layer: mixed mock + real backend

Historically the app ran entirely on mock/seeded data. **A real backend now exists** (FastAPI, base URL `http://127.0.0.1:8000` locally) but only implements 4 endpoints, all single-vessel (`/api/v1/vessels/{vessel}/...`): `performance-trend`, `maintenance-effectiveness`, `anomalies`, `maintenance-recommendation`. See `design_docs/4_api-integration-mapping.md` for the full mapping, field-level gaps between mock and real response shapes, and the recommended integration order. Everything else (fleet overview KPIs, vessel list, inspections, fuel attribution, fleet analytics) has no backend endpoint yet and stays on mock data (`src/mock/api.ts`) until one exists.

`src/mock/api.ts` is the only module views should import data from; it fakes ~260ms latency and derives data from `src/mock/reference.ts` (static vessel reference/live-state seeds), `src/mock/noonReports.ts` (noon report/speed-loss series generation), and `src/mock/seed.ts` (seeded RNG for determinism). When wiring a real endpoint, keep the mock function's signature and return shape (mapped to `types/fleet.ts`) so calling components don't need to change — swap the implementation from mock to `fetch` inside `mock/api.ts` (or a new module with the same exported function names), not scattered across views. Real API response fields often don't fully match the mock's field set (e.g. `performance-trend` has no `observedSpeed`/`beaufort`/`loadCondition`) — check `design_docs/4_api-integration-mapping.md` before assuming a one-to-one field mapping.

### Where new code goes

- New page → `.vue` under `src/views/` (or `src/views/vessel/` if per-vessel), then register the route in `src/router/index.ts`.
- New data need → typed shape in `src/types/fleet.ts`, then a `fetchX()` in `src/mock/api.ts` shaped like the intended real API (check `design_docs/1_fleet-dashboard-frontend-requirements.md` §6 and `design_docs/4_api-integration-mapping.md` first).
- Reusable UI (2+ views) → `src/components/`. Reusable stateful logic → `src/composables/`.

## Styling & conventions

- Tailwind CSS v4 via `@tailwindcss/vite` — no `tailwind.config.js`; v4 uses CSS-based `@theme` config in `src/style.css`. Check `design_docs/theme.md` and `design_docs/1_fleet-dashboard-frontend-requirements.md` §3 before hardcoding any color/spacing/radius value.
- `@/` → `src/` path alias (`vite.config.ts` + `tsconfig.json`) — use `@/...` imports instead of relative `../../` across directories.
- dayjs for all date handling — do not add moment.js or date-fns.
- `@vueuse/core` for reusable composable utilities — prefer it over hand-rolled composables when a vueuse utility already covers the need.
- `@tanstack/vue-table` for sortable/filterable tables; `maplibre-gl` for maps (fleet map + OpenSeaMap nautical layer, plus a single-vessel focus map).
- Numeric/data values (speed, tonnage, coordinates, %, currency) must use a monospace font and right-alignment in tables/readouts — a stated design requirement, not optional styling.
- Respect `prefers-reduced-motion`; keep hover/filter transitions ≤150ms, reserve stronger animation for the signature "scan" effect on Speed Loss chart load.
