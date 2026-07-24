export interface AuthUser {
  id: string
  email: string
  full_name: string
  role: 'admin' | 'owner'
  is_active: boolean
}

interface TokenResponse {
  access_token: string
  token_type: string
}

export type LoginResult = { success: true } | { success: false; errorKey: string }

/**
 * Errors are returned as a translation key, not a rendered message — the
 * composable has no reliable i18n context of its own once an await has run
 * (useI18n needs to be called from the component itself), so the caller
 * (a page) is expected to translate errorKey via its own useI18n().
 */
export function useAuth() {
  const token = useAuthToken()
  const api = useApi()

  async function login(email: string, password: string): Promise<LoginResult> {
    const body = new URLSearchParams()
    body.set('username', email)
    body.set('password', password)

    try {
      const response = await api<TokenResponse>('/auth/login', {
        method: 'POST',
        body,
      })
      token.value = response.access_token
      return { success: true }
    } catch {
      // The backend collapses every failure mode (wrong password, unknown
      // email, inactive account) into the same 401 — don't reconstruct the
      // distinction client-side, just surface the one generic message.
      return { success: false, errorKey: 'login.error' }
    }
  }

  async function logout(): Promise<void> {
    try {
      await api('/auth/logout', { method: 'POST' })
    } catch {
      // Best-effort — logout is a stateless no-op server-side anyway
      // (JWTs can't be invalidated without a blacklist, see auth.py).
    }
    token.value = null
  }

  async function fetchMe(): Promise<AuthUser | null> {
    if (!token.value) return null
    try {
      return await api<AuthUser>('/auth/me')
    } catch {
      return null
    }
  }

  return { token, login, logout, fetchMe }
}
