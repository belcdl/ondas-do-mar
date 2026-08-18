import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ApartmentsPage from '../pages/panel/apartments/index.vue'

const { mockApi, mockToastAdd } = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockToastAdd: vi.fn(),
}))

// useOwner() calls useApi() internally (see useOwner.test.ts) — mocking
// useApi() covers both the /owners/me lookup this page makes on load and
// every /apartments call, same approach as panelRateRules.test.ts and
// panelPhotos.test.ts.
mockNuxtImport('useApi', () => () => mockApi)
mockNuxtImport('useToast', () => () => ({
  add: mockToastAdd,
  toasts: { value: [] },
  update: vi.fn(),
  remove: vi.fn(),
  clear: vi.fn(),
}))

const OWNER = {
  id: 'owner-1',
  full_name: 'Test Owner',
  email: 'owner@example.com',
  phone: null,
  user_id: 'user-1',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('panel/apartments/index page', () => {
  beforeEach(() => {
    // useState persists across tests in the same file (shared Nuxt app
    // context) — same reset useOwner.test.ts does.
    useOwner().clearOwner()
    mockApi.mockReset()
    mockToastAdd.mockReset()
  })

  it('creates an apartment with the selected amenities and free-text amenities_other', async () => {
    mockApi.mockResolvedValueOnce(OWNER) // GET /owners/me
    mockApi.mockResolvedValueOnce([]) // GET /apartments (initial load)
    mockApi.mockResolvedValueOnce({ id: 'apt-1' }) // POST create response
    mockApi.mockResolvedValueOnce([]) // reload after create

    const component = await mountSuspended(ApartmentsPage)

    component.setupState.form.name = 'Casa Azul'
    component.setupState.form.address_line = 'Rua da Praia 12'
    component.setupState.form.city = 'Porto'
    component.setupState.form.country = 'Portugal'
    component.setupState.toggleAmenity('wifi', true)
    component.setupState.toggleAmenity('tv', true)
    component.setupState.form.amenities_other = 'Portable air conditioning unit'

    await component.setupState.onSubmitForm()

    expect(mockApi).toHaveBeenNthCalledWith(3, '/apartments', {
      method: 'POST',
      body: {
        name: 'Casa Azul',
        address_line: 'Rua da Praia 12',
        city: 'Porto',
        postal_code: null,
        country: 'Portugal',
        description: null,
        bedrooms: null,
        max_guests: 4,
        amenities: ['wifi', 'tv'],
        amenities_other: 'Portable air conditioning unit',
        owner_id: 'owner-1',
      },
    })
    expect(mockToastAdd).toHaveBeenCalledWith(expect.objectContaining({ color: 'success' }))
  })
})
