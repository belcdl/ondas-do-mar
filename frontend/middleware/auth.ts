export default defineNuxtRouteMiddleware(() => {
  const token = useAuthToken()
  if (!token.value) {
    const localePath = useLocalePath()
    return navigateTo(localePath('/login'))
  }
})
