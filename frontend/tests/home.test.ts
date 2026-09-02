import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HomePage from '../pages/index.vue'

const { mockApi } = vi.hoisted(() => ({
  mockApi: vi.fn(),
}))

// Same mocking boundary as publicApartment.test.ts: useApi is mocked,
// everything else (i18n, localePath, useLocaleHead, useSeoMeta) runs for real.
mockNuxtImport('useApi', () => () => mockApi)

const PUBLIC_APARTMENTS = [
  {
    id: 'apt-1',
    name: 'Casa Azul',
    city: 'Porto',
    country: 'Portugal',
    bedrooms: 2,
    max_guests: 4,
    photos: ['https://photos.example.com/apartments/apt-1/photo-1.jpg'],
  },
  {
    id: 'apt-2',
    name: 'Casa Verde',
    city: 'Vigo',
    country: 'Spain',
    bedrooms: 1,
    max_guests: 2,
    photos: [],
  },
]

const AVAILABILITY_RESULT = {
  apartment_id: 'apt-1',
  name: 'Casa Azul',
  nights: 3,
  currency: 'EUR',
  price_total: '300.00',
}

describe('index (home) page', () => {
  beforeEach(() => {
    mockApi.mockReset()
  })

  it('shows a teaser of the public apartments with a descriptive alt and only one h1', async () => {
    mockApi.mockResolvedValueOnce(PUBLIC_APARTMENTS) // GET /apartments/public

    const component = await mountSuspended(HomePage)

    expect(mockApi).toHaveBeenNthCalledWith(1, '/apartments/public')
    expect(component.text()).toContain('Casa Azul')
    expect(component.text()).toContain('Casa Verde')
    expect(
      component.find('img[alt="Casa Azul — Porto, Portugal"]').exists(),
    ).toBe(true)
    expect(component.findAll('h1')).toHaveLength(1)
  })

  it('checks availability from the hero widget and lists the results', async () => {
    mockApi.mockResolvedValueOnce([]) // GET /apartments/public
    const component = await mountSuspended(HomePage)

    mockApi.mockResolvedValueOnce([AVAILABILITY_RESULT]) // GET /availability/search
    component.setupState.checkIn.value = '2026-09-01'
    component.setupState.checkOut.value = '2026-09-04'
    component.setupState.guests.value = 2
    await component.setupState.onSearch()

    expect(mockApi).toHaveBeenNthCalledWith(2, '/availability/search', {
      query: { check_in: '2026-09-01', check_out: '2026-09-04', guests: 2 },
    })
    expect(component.text()).toContain('Casa Azul')
    expect(component.text()).toContain('300.00')
    expect(component.text()).toContain('EUR')
  })

  it('shows an error message when the availability search fails', async () => {
    mockApi.mockResolvedValueOnce([]) // GET /apartments/public
    const component = await mountSuspended(HomePage)

    mockApi.mockRejectedValueOnce(new Error('network error')) // GET /availability/search
    component.setupState.checkIn.value = '2026-09-01'
    component.setupState.checkOut.value = '2026-09-04'
    component.setupState.guests.value = 2
    await component.setupState.onSearch()

    expect(component.text()).toContain('No se pudo completar la búsqueda. Inténtalo de nuevo.')
    expect(component.setupState.results.value).toEqual([])
  })
})
