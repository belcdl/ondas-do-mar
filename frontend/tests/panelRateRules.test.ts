import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import RateRulesPage from '../pages/panel/apartments/[id]/rate-rules.vue'

const { mockApi, mockToastAdd } = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockToastAdd: vi.fn(),
}))

// The page calls useApi() for every backend call and useToast() to surface
// success/error feedback — mock both at that boundary, same approach as
// useAuth.test.ts/useOwner.test.ts mocking useApi. useRoute is mocked too:
// mounting the page component in isolation (rather than through Nuxt's
// actual page router) doesn't resolve the [id] dynamic segment from a
// plain route path, so the apartment id is supplied directly instead.
mockNuxtImport('useApi', () => () => mockApi)
mockNuxtImport('useRoute', () => () => ({ params: { id: 'apt-1' } }))
mockNuxtImport('useToast', () => () => ({
  add: mockToastAdd,
  toasts: { value: [] },
  update: vi.fn(),
  remove: vi.fn(),
  clear: vi.fn(),
}))

const APARTMENT = { id: 'apt-1', name: 'Casa Azul' }

const RATE_RULE = {
  id: 'rr-1',
  apartment_id: 'apt-1',
  start_date: '2026-08-01',
  end_date: '2026-08-10',
  price_per_night: '120.00',
  min_stay: 2,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('panel/apartments/[id]/rate-rules page', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockToastAdd.mockReset()
  })

  it('loads the apartment and lists its rate rules', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT) // GET /apartments/:id
    mockApi.mockResolvedValueOnce([RATE_RULE]) // GET /apartments/:id/rate-rules

    const component = await mountSuspended(RateRulesPage)

    expect(mockApi).toHaveBeenNthCalledWith(1, '/apartments/apt-1')
    expect(mockApi).toHaveBeenNthCalledWith(2, '/apartments/apt-1/rate-rules')
    expect(component.text()).toContain('Casa Azul')
    expect(component.text()).toContain('2026-08-01')
    expect(component.text()).toContain('2026-08-10')
  })

  it('creates a rate rule and shows a success toast', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([]) // no rate rules yet
    mockApi.mockResolvedValueOnce(RATE_RULE) // POST create response
    mockApi.mockResolvedValueOnce([RATE_RULE]) // reload after create

    const component = await mountSuspended(RateRulesPage)

    component.setupState.form.start_date = '2026-08-01'
    component.setupState.form.end_date = '2026-08-10'
    component.setupState.form.price_per_night = 120
    component.setupState.form.min_stay = 2

    await component.setupState.onSubmitForm()

    expect(mockApi).toHaveBeenNthCalledWith(3, '/apartments/apt-1/rate-rules', {
      method: 'POST',
      body: {
        start_date: '2026-08-01',
        end_date: '2026-08-10',
        price_per_night: 120,
        min_stay: 2,
      },
    })
    expect(mockToastAdd).toHaveBeenCalledWith(
      expect.objectContaining({ color: 'success' }),
    )
  })

  it('shows an error toast with the backend detail on an overlapping date conflict', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([RATE_RULE])
    mockApi.mockRejectedValueOnce({
      data: { detail: 'This date range overlaps an existing rate rule for this apartment' },
    })

    const component = await mountSuspended(RateRulesPage)

    component.setupState.form.start_date = '2026-08-05'
    component.setupState.form.end_date = '2026-08-15'
    component.setupState.form.price_per_night = 90
    component.setupState.form.min_stay = 1

    await component.setupState.onSubmitForm()

    expect(mockToastAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        color: 'error',
        description: 'This date range overlaps an existing rate rule for this apartment',
      }),
    )
  })
})
