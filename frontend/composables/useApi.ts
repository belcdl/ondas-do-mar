/**
 * Every backend call in this app goes through this composable — no ad-hoc
 * $fetch/fetch calls in page/component code (see CLAUDE.md conventions).
 */
export function useApi() {
  const config = useRuntimeConfig()
  const token = useAuthToken()

  return $fetch.create({
    baseURL: config.public.apiUrl,
    onRequest({ options }) {
      if (token.value) {
        const headers = new Headers(options.headers as HeadersInit | undefined)
        headers.set('Authorization', `Bearer ${token.value}`)
        options.headers = headers
      }
    },
  })
}
