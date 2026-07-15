import type { InjectionKey, Ref } from 'vue'
import type { MaintenanceCorrelationResponse } from '@/types/fleet'
import type { AsyncState } from '@/composables/useAsyncData'

// VesselLayout.vue fetches maintenance-correlation data once (ALT-01 needs it
// to stay visible across all vessel tabs, not just "維修效能分析") and
// provides it here; MaintenanceCorrelation.vue injects the same refs instead
// of fetching again, so switching tabs doesn't trigger a duplicate API call.
export const correlationDataKey: InjectionKey<Ref<MaintenanceCorrelationResponse | null>> = Symbol('correlationData')
export const correlationStateKey: InjectionKey<Ref<AsyncState>> = Symbol('correlationState')
