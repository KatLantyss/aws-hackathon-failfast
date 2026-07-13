import { ref, shallowRef, watchEffect, type Ref } from 'vue'

export type AsyncState = 'loading' | 'success' | 'empty' | 'error'

/**
 * Fetches reactively whenever `source` changes and exposes loading / empty /
 * error / success state per design_docs section 5 ("所有頁面須支援 Loading /
 * Empty / Error 三態").
 */
export function useAsyncData<TSource, TResult>(
  source: () => TSource,
  fetcher: (arg: TSource) => Promise<TResult>,
  isEmpty: (result: TResult) => boolean = (r) => r == null || (Array.isArray(r) && r.length === 0),
) {
  const data = shallowRef<TResult | null>(null) as Ref<TResult | null>
  const state = ref<AsyncState>('loading')
  const error = ref<string | null>(null)

  watchEffect(async () => {
    const arg = source()
    state.value = 'loading'
    error.value = null
    try {
      const result = await fetcher(arg)
      data.value = result
      state.value = isEmpty(result) ? 'empty' : 'success'
    } catch (e) {
      error.value = e instanceof Error ? e.message : '發生未知錯誤'
      state.value = 'error'
    }
  })

  return { data, state, error }
}
