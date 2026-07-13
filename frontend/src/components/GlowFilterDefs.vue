<script setup lang="ts">
// Shared, invisible SVG filter definitions — mounted once in App.vue.
// Adapted from the "Animate single img gradient glow border with CSS + SVG
// filter enhancement" technique (thebabydino, CodePen bGPMOpJ): a rotating
// conic-gradient ring gets its glow-bleed from an SVG filter (dilate the
// ring, blur it, then merge the crisp ring back on top) rather than a plain
// CSS box-shadow blur, which is what gives the trace/scan-line a slightly
// luminous, non-uniform quality instead of a flat glow.
//
// Applied only to decorative ::before pseudo-elements (see .panel--map-glow
// in style.css), never to live content like the MapLibre canvas — SVG
// filters are expensive and can visually corrupt WebGL/canvas children if
// applied to an ancestor, so the glow ring is composited on a separate
// layer that merely sits on top of the map panel.
</script>

<template>
  <svg width="0" height="0" aria-hidden="true" focusable="false" style="position: fixed">
    <defs>
      <filter id="map-glow-blur" x="-60%" y="-60%" width="220%" height="220%">
        <feMorphology in="SourceGraphic" operator="dilate" radius="1.8" result="thicken" />
        <feGaussianBlur in="thicken" stdDeviation="8" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>
  </svg>
</template>
