import { useDark, useToggle } from '@vueuse/core'

/**
 * App-wide dark mode state, backed by @vueuse/core's useDark:
 * - toggles a `.dark` class on <html> (matches the @custom-variant + token
 *   overrides in style.css)
 * - persists the user's choice in localStorage (key: "yangming-fleet-theme")
 * - defaults to dark mode on first visit (no stored preference yet),
 *   regardless of OS `prefers-color-scheme`; once the user toggles it,
 *   their explicit choice always wins on future visits
 *
 * Call this from any component; the underlying ref is a vueuse singleton
 * keyed by storageKey, so all callers share the same reactive state.
 */
export function useAppTheme() {
  const isDark = useDark({
    storageKey: 'yangming-fleet-theme',
    selector: 'html',
    attribute: 'class',
    valueDark: 'dark',
    valueLight: '',
    initialValue: 'dark',
  })
  const toggleDark = useToggle(isDark)

  return { isDark, toggleDark }
}
