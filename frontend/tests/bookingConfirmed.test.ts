import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BookingConfirmedPage from '../pages/booking-confirmed.vue'

const { mockApi, mockRoute } = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockRoute: { query: {} as Record<string, string> },
}))

// Same mocking boundary as bookingForm.test.ts/publicApartment.test.ts:
// useApi/useRoute are mocked, everything else runs for real.
mockNuxtImport('useApi', () => () => mockApi)
mockNuxtImport('useRoute', () => () => mockRoute)

const BOOKING = {
  id: 'booking-1',
  apartment_id: 'apt-1',
  guest_count: 2,
  check_in_date: '2026-09-01',
  check_out_date: '2026-09-04',
  confirmation_code: 'ABCD1234',
  status: 'confirmed',
  total_price: '300.00',
  currency: 'EUR',
}

const PUBLIC_APARTMENT = {
  id: 'apt-1',
  name: 'Casa Azul',
}

describe('booking-confirmed page', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockRoute.query = {}
  })

  it('shows the confirmation code, apartment name and dates on success', async () => {
    mockRoute.query = { confirmation_code: 'ABCD1234' }
    mockApi.mockResolvedValueOnce(BOOKING) // GET /bookings/by-confirmation/ABCD1234
    mockApi.mockResolvedValueOnce(PUBLIC_APARTMENT) // GET /apartments/apt-1/public

    const component = await mountSuspended(BookingConfirmedPage)

    expect(mockApi).toHaveBeenNthCalledWith(1, '/bookings/by-confirmation/ABCD1234')
    expect(mockApi).toHaveBeenNthCalledWith(2, '/apartments/apt-1/public')
    expect(component.text()).toContain('ABCD1234')
    expect(component.text()).toContain('Casa Azul')
    expect(component.text()).toContain('2026-09-01')
    expect(component.text()).toContain('2026-09-04')
  })

  it('still shows the confirmation without the apartment name when the apartment lookup fails', async () => {
    mockRoute.query = { confirmation_code: 'ABCD1234' }
    mockApi.mockResolvedValueOnce(BOOKING) // GET /bookings/by-confirmation/ABCD1234
    mockApi.mockRejectedValueOnce(new Error('404 Not Found')) // GET /apartments/apt-1/public

    const component = await mountSuspended(BookingConfirmedPage)

    expect(component.text()).toContain('ABCD1234')
    expect(component.text()).toContain('tu apartamento')
  })

  it('shows a not-found message and does not call the API when there is no confirmation_code in the query', async () => {
    mockRoute.query = {}

    const component = await mountSuspended(BookingConfirmedPage)

    expect(mockApi).not.toHaveBeenCalled()
    expect(component.text()).toContain('No se ha encontrado la reserva.')
  })

  it('shows a not-found message when the booking lookup 404s', async () => {
    mockRoute.query = { confirmation_code: 'NOPE0000' }
    mockApi.mockRejectedValueOnce(new Error('404 Not Found'))

    const component = await mountSuspended(BookingConfirmedPage)

    expect(mockApi).toHaveBeenCalledTimes(1)
    expect(component.text()).toContain('No se ha encontrado la reserva.')
  })
})
