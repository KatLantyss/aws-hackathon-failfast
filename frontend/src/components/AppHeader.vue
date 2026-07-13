<script setup lang="ts">
import { ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import yangMingLogo from '@/assets/yangming_logo.png'
import { useAppTheme } from '@/composables/useAppTheme'
import { useChatContextStore } from '@/stores/chatContext'

const route = useRoute()
const { isDark, toggleDark } = useAppTheme()
const chatContext = useChatContextStore()

const navItems = [
  { to: '/', label: '船隊總覽' },
  { to: '/vessels', label: '船隊列表' },
  { to: '/fleet-analytics', label: '跨船隊分析' },
]

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

// Mobile menu — a slide-down panel, not a generic full-screen overlay, so it
// still reads as "part of the instrument header" rather than a bolted-on
// hamburger menu.
const mobileOpen = ref(false)
watch(
  () => route.fullPath,
  () => {
    mobileOpen.value = false
  },
)
</script>

<template>
  <header
    class="sticky top-0 z-30 text-[var(--color-on-navy)] border-b border-white/10"
    style="
      background:
        linear-gradient(180deg, var(--color-marine-navy-light) 0%, var(--color-marine-navy) 45%, var(--color-marine-navy-deep) 100%);
      box-shadow: 0 2px 0 var(--color-brand-red), 0 6px 20px rgba(0, 0, 0, 0.4);
    "
  >
    <div class="mx-auto max-w-[1440px] flex items-center gap-4 md:gap-8 px-4 md:px-6 h-16">
      <RouterLink to="/" class="flex items-center gap-2 md:gap-3 shrink-0 group">
        <span
          class="grid place-items-center h-9 w-9 rounded-[3px] border border-[var(--color-brand-red)]/60 bg-white/[0.06] overflow-hidden"
        >
          <img :src="yangMingLogo" alt="陽明海運" class="h-6 w-6 object-contain" />
        </span>
        <span class="flex flex-col leading-none">
          <span class="font-display text-sm font-bold tracking-[0.2em] transition-colors">
            YANG&nbsp;MING
          </span>
          <span class="font-mono text-[10px] tracking-[0.32em] text-[var(--color-on-navy)]/55">AI&nbsp;FLEET&nbsp;OPS</span>
        </span>
      </RouterLink>

      <!-- Desktop nav -->
      <nav class="hidden md:flex items-center gap-1 text-sm" aria-label="主導覽">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="relative font-display text-xs tracking-[0.12em] uppercase px-3.5 py-2 rounded-[3px] transition-all duration-150"
          :class="
            isActive(item.to)
              ? 'text-white bg-white/[0.06]'
              : 'text-[var(--color-on-navy)]/70 hover:text-[var(--color-on-navy)] hover:bg-white/[0.04]'
          "
        >
          {{ item.label }}
          <span
            v-if="isActive(item.to)"
            class="absolute left-3.5 right-3.5 -bottom-[1px] h-[2px] bg-[var(--color-brand-red)] rounded-full"
            aria-hidden="true"
          />
        </RouterLink>
      </nav>

      <div class="ml-auto flex items-center gap-2 md:gap-3">
        <!-- Theme toggle: instrument-style rocker rather than a generic sun/moon
             text switch, echoing the panel/gauge visual language elsewhere. -->
        <button
          type="button"
          class="relative grid place-items-center h-8 w-8 rounded-[3px] border border-white/10 bg-white/[0.04] text-[var(--color-on-navy)]/75 hover:text-white hover:border-[var(--color-brand-red)]/50 transition-colors duration-150"
          :aria-pressed="isDark"
          :aria-label="isDark ? '切換為淺色模式' : '切換為深色模式'"
          @click="toggleDark()"
        >
          <svg v-if="isDark" width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="12" r="4.5" stroke="currentColor" stroke-width="1.6" />
            <path
              d="M12 2.5v2.2M12 19.3v2.2M4.2 4.2l1.55 1.55M18.25 18.25l1.55 1.55M2.5 12h2.2M19.3 12h2.2M4.2 19.8l1.55-1.55M18.25 5.75l1.55-1.55"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
            />
          </svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linejoin="round"
            />
          </svg>
        </button>

        <!-- VoiceBot trigger: same instrument icon-button language as the theme
             toggle, opens the full-screen dialogue overlay (design_docs/3). -->
        <button
          type="button"
          class="relative grid place-items-center h-8 w-8 rounded-[3px] border border-white/10 bg-white/[0.04] text-[var(--color-on-navy)]/75 hover:text-white hover:border-[var(--color-fathom-teal)]/60 transition-colors duration-150"
          aria-label="對話模式 (Cmd/Ctrl+K)"
          title="對話模式 (⌘K)"
          @click="chatContext.openChat()"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle cx="12" cy="3.2" r="1.1" fill="currentColor" />
            <path d="M12 4.3v2.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            <rect x="5" y="6.5" width="14" height="12" rx="3" stroke="currentColor" stroke-width="1.6" />
            <circle cx="9.3" cy="12" r="1.15" fill="currentColor" />
            <circle cx="14.7" cy="12" r="1.15" fill="currentColor" />
            <path d="M9 15.3h6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
            <path d="M5 10.5H3M21 10.5h-2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
          </svg>
        </button>

        <div class="hidden lg:flex items-center gap-2.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5">
          <span class="relative flex h-2 w-2" aria-hidden="true">
            <span class="absolute inline-flex h-full w-full rounded-full bg-[var(--color-fathom-teal)] opacity-60 animate-ping" />
            <span class="relative inline-flex h-2 w-2 rounded-full bg-[var(--color-fathom-teal)]" />
          </span>
          <span class="font-mono text-[11px] tracking-[0.18em] text-[var(--color-on-navy)]/75">SYSTEM NOMINAL</span>
        </div>

        <!-- Mobile menu toggle -->
        <button
          type="button"
          class="md:hidden grid place-items-center h-8 w-8 rounded-[3px] border border-white/10 bg-white/[0.04] text-[var(--color-on-navy)]/85"
          :aria-expanded="mobileOpen"
          aria-controls="mobile-nav-panel"
          aria-label="開啟主導覽選單"
          @click="mobileOpen = !mobileOpen"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              v-if="!mobileOpen"
              d="M4 7h16M4 12h16M4 17h16"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
            />
            <path v-else d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </div>

    <!-- Mobile nav panel: slides down from under the header, kept within the
         same instrument-panel visual language (mono labels, brand-red active
         indicator) rather than a generic drawer. -->
    <Transition
      enter-active-class="transition-[grid-template-rows] duration-200 ease-out"
      leave-active-class="transition-[grid-template-rows] duration-150 ease-in"
      enter-from-class="mobile-nav--collapsed"
      leave-to-class="mobile-nav--collapsed"
    >
      <nav
        v-if="mobileOpen"
        id="mobile-nav-panel"
        class="mobile-nav md:hidden border-t border-white/10"
        aria-label="行動裝置主導覽"
      >
        <div class="overflow-hidden">
          <ul class="mx-auto max-w-[1440px] px-4 py-2 flex flex-col gap-1">
            <li v-for="item in navItems" :key="item.to">
              <RouterLink
                :to="item.to"
                class="flex items-center justify-between font-display text-sm tracking-[0.08em] uppercase px-3 py-2.5 rounded-[3px] transition-colors duration-150"
                :class="
                  isActive(item.to)
                    ? 'text-white bg-white/[0.07] border-l-2 border-[var(--color-brand-red)]'
                    : 'text-[var(--color-on-navy)]/75 border-l-2 border-transparent hover:bg-white/[0.04]'
                "
              >
                {{ item.label }}
                <span v-if="isActive(item.to)" class="font-mono text-[10px] text-[var(--color-brand-red)]">●</span>
              </RouterLink>
            </li>
          </ul>
        </div>
      </nav>
    </Transition>
  </header>
</template>

<style scoped>
/* grid-template-rows trick gives a smooth height animation without needing
   to know the panel's content height in advance */
.mobile-nav {
  display: grid;
  grid-template-rows: 1fr;
  background: color-mix(in srgb, var(--color-marine-navy-deep) 96%, transparent);
}
.mobile-nav--collapsed {
  grid-template-rows: 0fr;
}
</style>
