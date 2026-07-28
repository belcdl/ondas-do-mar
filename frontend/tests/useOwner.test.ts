import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockApi } = vi.hoisted(() => ({
  mockApi: vi.fn(),
}))

// useOwner() calls the useApi() composable to get its fetch instance — mock
// that composable rather than reaching into ofetch internals, same approach
// as useAuth.test.ts.
mockNuxtImport('useApi', () => () => mockApi)

describe('useOwner fetchOwner', () => {
  beforeEach(() => {
    // useState persists across tests in the same file (shared Nuxt app
    // context), so start each test with no cached owner.
    useOwner().clearOwner()
    mockApi.mockReset()
  })

  it('fetches /owners/me and caches the result', async () => {
    const profile = {
      id: 'owner-1',
      full_name: 'Test Owner',
      email: 'owner@example.com',
      phone: null,
      user_id: 'user-1',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    }
    mockApi.mockResolvedValueOnce(profile)

    const { owner, fetchOwner } = useOwner()
    const result = await fetchOwner()

    expect(result).toEqual(profile)
    expect(owner.value).toEqual(profile)
    expect(mockApi).toHaveBeenCalledWith('/owners/me')
  })

  it('does not re-fetch once the owner is cached', async () => {
    mockApi.mockResolvedValueOnce({
      id: 'owner-1',
      full_name: 'Test Owner',
      email: 'owner@example.com',
      phone: null,
      user_id: 'user-1',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })

    const { fetchOwner } = useOwner()
    await fetchOwner()
    await fetchOwner()

    expect(mockApi).toHaveBeenCalledTimes(1)
  })

  it('returns null without throwing when there is no linked owner (e.g. an admin)', async () => {
    mockApi.mockRejectedValueOnce(new Error('404 Not Found'))

    const { owner, fetchOwner } = useOwner()
    const result = await fetchOwner()

    expect(result).toBeNull()
    expect(owner.value).toBeNull()
  })

  it('clearOwner resets the cache so the next fetchOwner call hits the API again', async () => {
    mockApi.mockResolvedValue({
      id: 'owner-1',
      full_name: 'Test Owner',
      email: 'owner@example.com',
      phone: null,
      user_id: 'user-1',
      is_active: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    })

    const { owner, fetchOwner, clearOwner } = useOwner()
    await fetchOwner()
    clearOwner()
    expect(owner.value).toBeNull()

    await fetchOwner()
    expect(mockApi).toHaveBeenCalledTimes(2)
  })
})
