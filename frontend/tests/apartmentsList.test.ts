import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ApartmentsListPage from '../pages/apartamentos/index.vue'

const { mockApi } = vi.hoisted(() => ({
  mockApi: vi.fn(),
}))

// Same mocking boundary as publicApartment.test.ts/home.test.ts: useApi is
// mocked, everything else runs for real.
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

describe('apartamentos/index page', () => {
  beforeEach(() => {
    mockApi.mockReset()
  })

  it('shows the full grid of public apartments with a descriptive alt and only one h1', async () => {
    mockApi.mockResolvedValueOnce(PUBLIC_APARTMENTS) // GET /apartments/public

    const component = await mountSuspended(ApartmentsListPage)

    expect(mockApi).toHaveBeenCalledWith('/apartments/public')
    expect(component.text()).toContain('Casa Azul')
    expect(component.text()).toContain('Casa Verde')
    expect(
      component.find('img[alt="Casa Azul — Porto, Portugal"]').exists(),
    ).toBe(true)
    expect(component.findAll('h1')).toHaveLength(1)
  })

  it('shows an empty message instead of a grid when there are no apartments', async () => {
    mockApi.mockResolvedValueOnce([]) // GET /apartments/public

    const component = await mountSuspended(ApartmentsListPage)

    expect(component.text()).toContain('No hay apartamentos disponibles en este momento.')
  })

  it('shows an error message when the apartments fail to load', async () => {
    mockApi.mockRejectedValueOnce(new Error('network error')) // GET /apartments/public

    const component = await mountSuspended(ApartmentsListPage)

    expect(component.text()).toContain('No se pudieron cargar los apartamentos.')
  })
})
