export default defineNuxtRouteMiddleware(() => {
  const token = useAuthToken()
  if (!token.value) {
    return navigateTo('/login')
  }
})
