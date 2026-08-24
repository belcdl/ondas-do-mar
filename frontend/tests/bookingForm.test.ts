import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BookingPage from '../pages/apartamentos/[id]/reservar.vue'

const { mockApi, mockToastAdd, mockNavigateTo } = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockToastAdd: vi.fn(),
  mockNavigateTo: vi.fn(),
}))

// Same mocking boundary as panelCalendar.test.ts/publicApartment.test.ts:
// useApi/useRoute/useToast are mocked, everything else runs for real.
// navigateTo is mocked too — the page uses it (not a bare <a> or
// window.location) specifically so the redirect to Stripe is testable here.
mockNuxtImport('useApi', () => () => mockApi)
mockNuxtImport('useRoute', () => () => ({ params: { id: 'apt-1' } }))
mockNuxtImport('useToast', () => () => ({
  add: mockToastAdd,
  toasts: { value: [] },
  update: vi.fn(),
  remove: vi.fn(),
  clear: vi.fn(),
}))
mockNuxtImport('navigateTo', () => mockNavigateTo)

const PUBLIC_APARTMENT = {
  id: 'apt-1',
  name: 'Casa Azul',
  max_guests: 4,
}

const AVAILABILITY_RESULT = {
  apartment_id: 'apt-1',
  nights: 3,
  currency: 'EUR',
  price_total: '300.00',
}

async function mountWithApartment() {
  mockApi.mockResolvedValueOnce(PUBLIC_APARTMENT) // GET /apartments/apt-1/public
  return mountSuspended(BookingPage)
}

describe('apartamentos/[id]/reservar page', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockToastAdd.mockReset()
    mockNavigateTo.mockReset()
  })

  it('checks availability, submits the booking and redirects to the Stripe checkout URL', async () => {
    const component = await mountWithApartment()

    mockApi.mockResolvedValueOnce([AVAILABILITY_RESULT]) // GET /availability/search

    component.setupState.checkIn.value = '2026-09-01'
    component.setupState.checkOut.value = '2026-09-04'
    component.setupState.guests.value = 2
    await component.setupState.onCheckAvailability()

    expect(mockApi).toHaveBeenNthCalledWith(2, '/availability/search', {
      query: { check_in: '2026-09-01', check_out: '2026-09-04', guests: 2 },
    })
    expect(component.text()).toContain('300.00')
    expect(component.text()).toContain('EUR')

    mockApi.mockResolvedValueOnce({ id: 'booking-1' }) // POST /bookings
    mockApi.mockResolvedValueOnce({ checkout_url: 'https://checkout.stripe.com/session-abc' }) // POST checkout-session

    component.setupState.guestFullName.value = 'Jane Doe'
    component.setupState.guestEmail.value = 'jane@example.com'
    component.setupState.guestPhone.value = '+34600000000'
    await component.setupState.onSubmitBooking()

    expect(mockApi).toHaveBeenNthCalledWith(3, '/bookings', {
      method: 'POST',
      body: {
        apartment_id: 'apt-1',
        guest_full_name: 'Jane Doe',
        guest_email: 'jane@example.com',
        guest_phone: '+34600000000',
        guest_count: 2,
        check_in_date: '2026-09-01',
        check_out_date: '2026-09-04',
      },
    })
    expect(mockApi).toHaveBeenNthCalledWith(4, '/bookings/booking-1/checkout-session', {
      method: 'POST',
    })
    expect(mockNavigateTo).toHaveBeenCalledWith('https://checkout.stripe.com/session-abc', {
      external: true,
    })
  })

  it('shows a not-available message and keeps the guest form hidden when no result matches', async () => {
    const component = await mountWithApartment()

    mockApi.mockResolvedValueOnce([]) // GET /availability/search — no results at all

    component.setupState.checkIn.value = '2026-09-01'
    component.setupState.checkOut.value = '2026-09-04'
    component.setupState.guests.value = 2
    await component.setupState.onCheckAvailability()

    expect(component.text()).toContain('Not available for those dates.')
    expect(component.setupState.availabilityResult.value).toBeNull()
    expect(component.find('input[type="email"]').exists()).toBe(false)
  })

  it('does not call the API and shows an error toast when guest phone is empty', async () => {
    const component = await mountWithApartment()

    mockApi.mockResolvedValueOnce([AVAILABILITY_RESULT]) // GET /availability/search
    component.setupState.checkIn.value = '2026-09-01'
    component.setupState.checkOut.value = '2026-09-04'
    component.setupState.guests.value = 2
    await component.setupState.onCheckAvailability()

    component.setupState.guestFullName.value = 'Jane Doe'
    component.setupState.guestEmail.value = 'jane@example.com'
    component.setupState.guestPhone.value = ''
    await component.setupState.onSubmitBooking()

    expect(mockApi).toHaveBeenCalledTimes(2) // only the public-apartment GET and availability search
    expect(mockToastAdd).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Phone is required' }),
    )
    expect(mockNavigateTo).not.toHaveBeenCalled()
  })

  it('shows a conflict message and hides the guest form again on a 409 from POST /bookings', async () => {
    const component = await mountWithApartment()

    mockApi.mockResolvedValueOnce([AVAILABILITY_RESULT]) // GET /availability/search
    component.setupState.checkIn.value = '2026-09-01'
    component.setupState.checkOut.value = '2026-09-04'
    component.setupState.guests.value = 2
    await component.setupState.onCheckAvailability()

    mockApi.mockRejectedValueOnce({
      status: 409,
      data: { detail: 'These dates are no longer available' },
    })

    component.setupState.guestFullName.value = 'Jane Doe'
    component.setupState.guestEmail.value = 'jane@example.com'
    component.setupState.guestPhone.value = '+34600000000'
    await component.setupState.onSubmitBooking()

    expect(component.text()).toContain('Those dates are no longer available. Please check availability again.')
    expect(component.setupState.availabilityResult.value).toBeNull()
    expect(component.find('input[type="email"]').exists()).toBe(false)
    expect(mockNavigateTo).not.toHaveBeenCalled()
  })
})
