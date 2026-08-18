import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PublicApartmentPage from '../pages/apartamentos/[id].vue'

const { mockApi } = vi.hoisted(() => ({
  mockApi: vi.fn(),
}))

// Same mocking boundary as panelCalendar.test.ts: useApi/useRoute are
// mocked, everything else runs for real.
mockNuxtImport('useApi', () => () => mockApi)
mockNuxtImport('useRoute', () => () => ({ params: { id: 'apt-1' } }))

const PUBLIC_APARTMENT = {
  id: 'apt-1',
  name: 'Casa Azul',
  description: 'A lovely apartment by the beach.',
  address_line: 'Rua da Praia 12',
  city: 'Porto',
  postal_code: '4000-000',
  country: 'Portugal',
  bedrooms: 2,
  max_guests: 4,
  amenities: ['wifi', 'terrace'],
  amenities_other: null,
  photos: [
    'https://photos.example.com/apartments/apt-1/photo-1.jpg',
    'https://photos.example.com/apartments/apt-1/photo-2.jpg',
  ],
}

describe('apartamentos/[id] public page', () => {
  beforeEach(() => {
    mockApi.mockReset()
  })

  it('shows the apartment name, photos and only the amenities it has', async () => {
    mockApi.mockResolvedValueOnce(PUBLIC_APARTMENT) // GET /apartments/:id/public

    const component = await mountSuspended(PublicApartmentPage)

    expect(mockApi).toHaveBeenCalledWith('/apartments/apt-1/public')
    expect(component.text()).toContain('Casa Azul')
    expect(
      component.find(`img[src="${PUBLIC_APARTMENT.photos[0]}"]`).exists(),
    ).toBe(true)
    expect(
      component.find(`img[src="${PUBLIC_APARTMENT.photos[1]}"]`).exists(),
    ).toBe(true)
    expect(component.text()).toContain('Wifi')
    expect(component.text()).toContain('Terrace')
    expect(component.text()).not.toContain('Elevator')
  })

  it('shows a not-found message instead of throwing when the apartment is missing or inactive', async () => {
    mockApi.mockRejectedValueOnce(new Error('404 Not Found'))

    const component = await mountSuspended(PublicApartmentPage)

    expect(component.text()).toContain('Apartment not found.')
  })
})
