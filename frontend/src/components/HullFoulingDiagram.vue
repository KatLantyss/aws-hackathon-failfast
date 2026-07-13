<script setup lang="ts">
// Simplified top-down hull diagram, sections colored by fouling grade.
import type { HullSectionFouling } from '@/types/fleet'

const props = defineProps<{ sections: HullSectionFouling[] }>()

const gradeColor: Record<string, string> = {
  Clean: 'var(--color-fathom-teal)',
  Light: 'var(--color-fouling-light)',
  Moderate: 'var(--color-brass-amber)',
  Heavy: 'var(--color-signal-red)',
}

function colorFor(section: HullSectionFouling['section']) {
  const s = props.sections.find((x) => x.section === section)
  return s ? gradeColor[s.grade] : '#ccc'
}
</script>

<template>
  <svg viewBox="0 0 200 420" class="w-full max-w-[220px]" role="img" aria-label="船體污損分區示意圖">
    <!-- hull outline: bow at top, stern at bottom -->
    <path
      d="M100 10 C 40 60, 20 140, 20 210 C 20 320, 50 380, 100 410 C 150 380, 180 320, 180 210 C 180 140, 160 60, 100 10 Z"
      fill="none"
      stroke="var(--color-ink-slate)"
      stroke-width="2"
    />
    <!-- bow -->
    <path d="M100 10 C 60 45, 40 90, 32 140 L168 140 C160 90, 140 45, 100 10 Z" :fill="colorFor('bow')" opacity="0.85" />
    <!-- forward flat -->
    <rect x="32" y="140" width="136" height="80" :fill="colorFor('forward-flat')" opacity="0.85" />
    <!-- aft flat -->
    <rect x="32" y="220" width="136" height="80" :fill="colorFor('aft-flat')" opacity="0.85" />
    <!-- stern -->
    <path d="M32 300 L168 300 C160 350, 140 385, 100 410 C 60 385, 40 350, 32 300 Z" :fill="colorFor('stern')" opacity="0.85" />
    <!-- port side sliver -->
    <path d="M20 210 C20 260,26 300,32 300 L32 140 C 26 170, 20 190, 20 210Z" :fill="colorFor('port-side')" opacity="0.85" />
    <!-- starboard side sliver -->
    <path d="M180 210 C180 260,174 300,168 300 L168 140 C 174 170, 180 190, 180 210Z" :fill="colorFor('starboard-side')" opacity="0.85" />
    <!-- propeller -->
    <circle cx="100" cy="395" r="12" :fill="colorFor('propeller')" stroke="var(--color-ink-slate)" stroke-width="1.5" />
    <!-- rudder -->
    <rect x="94" y="405" width="12" height="10" :fill="colorFor('rudder')" stroke="var(--color-ink-slate)" stroke-width="1" />

    <text x="100" y="26" text-anchor="middle" class="font-data" font-size="9" fill="var(--color-ink-slate)">BOW</text>
    <text x="100" y="402" text-anchor="middle" class="font-data" font-size="8" fill="white">PROP</text>
  </svg>
</template>
