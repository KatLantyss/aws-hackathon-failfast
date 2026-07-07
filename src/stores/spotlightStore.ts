import { defineStore } from 'pinia'

export const useSpotlightStore = defineStore('spotlight', {
  state: () => ({
    targetSelector: null as string | null
  }),
  actions: {
    show(selector: string) {
      this.targetSelector = null
      requestAnimationFrame(() => {
        this.targetSelector = selector
      })
    },
    hide() {
      this.targetSelector = null
    }
  }
})
