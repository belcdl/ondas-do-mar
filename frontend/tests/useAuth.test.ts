import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockApi } = vi.hoisted(() => ({
  mockApi: vi.fn(),
}))

// useAuth() calls the useApi() composable to get its fetch instance — mock
// that composable rather than reaching into ofetch internals, so this test
// stays at the same boundary useAuth itself depends on.
mockNuxtImport('useApi', () => () => mockApi)

describe('useAuth login', () => {
  beforeEach(() => {
    // The cookie backing useAuthToken() persists across tests in the same
    // file (it's backed by the shared happy-dom `document`), so start each
    // test logged out rather than carrying over the previous test's token.
    useAuthToken().value = null
  })

  it('stores the access token in the auth cookie on success', async () => {
    mockApi.mockResolvedValueOnce({ access_token: 'test-token', token_type: 'bearer' })

    const { login, token } = useAuth()
    const result = await login('owner@example.com', 'correct-password')

    expect(result).toEqual({ success: true })
    expect(token.value).toBe('test-token')
  })

  it('surfaces a generic error key on 401 and leaves the cookie unset', async () => {
    mockApi.mockRejectedValueOnce(new Error('401 Unauthorized'))

    const { login, token } = useAuth()
    const result = await login('owner@example.com', 'wrong-password')

    expect(result).toEqual({ success: false, errorKey: 'login.error' })
    expect(token.value).toBeFalsy()
  })
})
