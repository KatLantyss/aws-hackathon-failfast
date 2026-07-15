<script setup lang="ts">
// Dev-only overlay: a small corner badge naming this block's backend status
// (REAL / HYBRID / STUB / UNREACHABLE), with a hover/click popover mapping
// each displayed value to the API field or frontend computation behind it.
// Renders nothing unless VITE_DEBUG_DATA_SOURCE=true — see useDataSourceDebug.ts.
import { ref } from 'vue'
import type { DataSourceInfo, DataSourceStatus } from '@/types/dataSource'
import { dataSourceDebugEnabled } from '@/composables/useDataSourceDebug'

defineProps<{ info: DataSourceInfo }>()

const pinned = ref(false)

const STATUS_LABEL: Record<DataSourceStatus, string> = {
  real: 'REAL',
  hybrid: 'HYBRID',
  stub: 'STUB',
  unreachable: 'UNREACHABLE',
}

function endpoints(e: DataSourceInfo['endpoint']): string[] {
  if (!e) return []
  return Array.isArray(e) ? e : [e]
}
</script>

<template>
  <div
    v-if="dataSourceDebugEnabled"
    class="ds-tag"
    :class="[`ds-tag--${info.status}`, { 'ds-tag--pinned': pinned }]"
    @click="pinned = !pinned"
  >
    <span class="ds-tag__badge">{{ STATUS_LABEL[info.status] }}</span>

    <div class="ds-tag__pop" @click.stop>
      <p class="ds-tag__status-line">
        <span class="ds-tag__badge ds-tag__badge--lg">{{ STATUS_LABEL[info.status] }}</span>
        <span v-if="pinned" class="ds-tag__pin-hint">已釘住，再點一次收合</span>
      </p>
      <p class="ds-tag__desc">{{ info.description }}</p>
      <p v-if="endpoints(info.endpoint).length" class="ds-tag__endpoints">
        <code v-for="e in endpoints(info.endpoint)" :key="e">{{ e }}</code>
      </p>
      <table v-if="info.fields?.length" class="ds-tag__fields">
        <thead>
          <tr>
            <th>畫面顯示</th>
            <th>資料來源</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in info.fields" :key="f.ui">
            <td>{{ f.ui }}</td>
            <td>
              <code>{{ f.source }}</code>
              <span v-if="f.note" class="ds-tag__note">— {{ f.note }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.ds-tag {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 40;
  cursor: pointer;
  font-family: 'IBM Plex Mono', monospace;
}

.ds-tag__badge {
  display: inline-flex;
  align-items: center;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 2px 6px;
  border-radius: 3px;
  color: #fff;
  line-height: 1.4;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}
.ds-tag__badge--lg { font-size: 10px; padding: 3px 8px; }

.ds-tag--real .ds-tag__badge { background: var(--color-fathom-teal); }
.ds-tag--hybrid .ds-tag__badge { background: var(--color-brass-amber); color: #2a2000; }
.ds-tag--stub .ds-tag__badge { background: var(--color-signal-red); }
.ds-tag--unreachable .ds-tag__badge { background: var(--color-ink-muted); }

.ds-tag__pop {
  display: none;
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 6px;
  width: 340px;
  max-width: min(340px, calc(100vw - 32px));
  max-height: 70vh;
  overflow-y: auto;
  background: var(--color-chart-paper-hi);
  border: 1px solid color-mix(in srgb, var(--color-ink-slate) 22%, transparent);
  border-radius: 4px;
  padding: 12px 14px;
  box-shadow: var(--elevation-3);
  text-align: left;
  cursor: default;
}

.ds-tag:hover .ds-tag__pop,
.ds-tag--pinned .ds-tag__pop {
  display: block;
}

.ds-tag__status-line { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; }
.ds-tag__pin-hint { font-size: 10px; color: var(--color-ink-muted); font-style: italic; }

.ds-tag__desc {
  font-family: 'IBM Plex Sans', sans-serif;
  font-size: 12px;
  color: var(--color-ink-slate);
  line-height: 1.5;
  margin: 0 0 8px;
}

.ds-tag__endpoints {
  margin: 0 0 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ds-tag__endpoints code {
  display: inline-block;
  font-size: 10.5px;
  color: var(--color-fathom-teal);
  background: color-mix(in srgb, var(--color-fathom-teal) 12%, transparent);
  padding: 2px 6px;
  border-radius: 3px;
  white-space: nowrap;
  overflow-x: auto;
}

.ds-tag__fields { width: 100%; border-collapse: collapse; font-size: 11px; }
.ds-tag__fields th {
  text-align: left;
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-ink-muted);
  padding: 4px 6px;
  border-bottom: 1px solid color-mix(in srgb, var(--color-ink-slate) 20%, transparent);
}
.ds-tag__fields td {
  font-family: 'IBM Plex Sans', sans-serif;
  padding: 5px 6px;
  border-bottom: 1px solid color-mix(in srgb, var(--color-ink-slate) 10%, transparent);
  color: var(--color-ink-slate);
  vertical-align: top;
}
.ds-tag__fields td:first-child { white-space: nowrap; }
.ds-tag__fields code { color: var(--color-brass-amber); }
.ds-tag__note { display: block; color: var(--color-ink-muted); font-family: 'IBM Plex Sans', sans-serif; margin-top: 1px; }
</style>
