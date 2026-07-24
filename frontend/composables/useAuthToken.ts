/**
 * The JWT lives in a cookie, not localStorage — localStorage doesn't exist
 * during SSR and this app renders server-side, so a cookie is what lets an
 * authenticated page know the user's logged in before the first paint.
 * Not httpOnly since it's set from client-side JS (the token only ever
 * comes back in the /auth/login response body, never as a Set-Cookie header
 * — the backend sets no cookies at all, see backend/app/core/config.py).
 */
export function useAuthToken() {
  return useCookie<string | null>('auth_token', {
    default: () => null,
    sameSite: 'lax',
    secure: !import.meta.dev,
  })
}
