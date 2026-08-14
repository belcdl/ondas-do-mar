import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CalendarPage from '../pages/panel/apartments/[id]/calendar.vue'

const { mockApi, mockToastAdd } = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockToastAdd: vi.fn(),
}))

// Same mocking boundary as panelRateRules.test.ts: useApi/useRoute/useToast
// are mocked, everything else (including the data-merging logic under test)
// runs for real. v-calendar's own rendering isn't asserted on here — the
// task only calls for testing the data/API logic, not v-calendar's visuals.
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

const BLOCKED_DATE = {
  id: 'bd-1',
  apartment_id: 'apt-1',
  start_date: '2026-08-15',
  end_date: '2026-08-17',
  reason: 'Mantenimiento',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const BOOKING = {
  id: 'bk-1',
  apartment_id: 'apt-1',
  guest_full_name: 'Jane Doe',
  check_in_date: '2026-08-20',
  check_out_date: '2026-08-23',
  status: 'confirmed',
}

async function mountWithData() {
  mockApi.mockResolvedValueOnce(APARTMENT) // GET /apartments/:id
  mockApi.mockResolvedValueOnce([RATE_RULE]) // GET .../rate-rules
  mockApi.mockResolvedValueOnce([BLOCKED_DATE]) // GET .../blocked-dates
  mockApi.mockResolvedValueOnce([BOOKING]) // GET /bookings
  return mountSuspended(CalendarPage)
}

describe('panel/apartments/[id]/calendar page', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockToastAdd.mockReset()
  })

  it('loads and combines rate rules, blocked dates and bookings', async () => {
    const component = await mountWithData()

    expect(mockApi).toHaveBeenNthCalledWith(1, '/apartments/apt-1')
    expect(mockApi).toHaveBeenNthCalledWith(2, '/apartments/apt-1/rate-rules')
    expect(mockApi).toHaveBeenNthCalledWith(3, '/apartments/apt-1/blocked-dates')
    expect(mockApi).toHaveBeenNthCalledWith(4, '/bookings', {
      query: { apartment_id: 'apt-1', status: 'confirmed' },
    })
    expect(component.text()).toContain('Casa Azul')

    // A day only covered by the rate rule reads as priced...
    expect(component.setupState.getDayInfo('2026-08-05').status).toBe('priced')
    // ...a day covered by the blocked date reads as blocked...
    expect(component.setupState.getDayInfo('2026-08-16').status).toBe('blocked')
    // ...a night of the confirmed booking reads as booked...
    expect(component.setupState.getDayInfo('2026-08-21').status).toBe('booked')
    // ...but the booking's checkout day itself is free again (last-night semantics,
    // same as services/availability.py's last_night = check_out_date - 1 day).
    expect(component.setupState.getDayInfo('2026-08-23').status).toBe('none')
  })

  it('creates a rate rule for a selected range and shows a success toast', async () => {
    const component = await mountWithData()

    component.setupState.openRateRuleCreateForm('2026-09-01', '2026-09-05')
    component.setupState.rateRuleForm.price_per_night = 95
    component.setupState.rateRuleForm.min_stay = 1

    mockApi.mockResolvedValueOnce(RATE_RULE) // POST create response
    mockApi.mockResolvedValueOnce([RATE_RULE]) // reload: rate-rules
    mockApi.mockResolvedValueOnce([BLOCKED_DATE]) // reload: blocked-dates
    mockApi.mockResolvedValueOnce([BOOKING]) // reload: bookings

    await component.setupState.submitRateRuleForm()

    expect(mockApi).toHaveBeenNthCalledWith(5, '/apartments/apt-1/rate-rules', {
      method: 'POST',
      body: {
        start_date: '2026-09-01',
        end_date: '2026-09-05',
        price_per_night: 95,
        min_stay: 1,
      },
    })
    expect(mockToastAdd).toHaveBeenCalledWith(expect.objectContaining({ color: 'success' }))
  })

  it('shows an error toast with the backend detail on an overlapping rate rule conflict', async () => {
    const component = await mountWithData()

    component.setupState.openRateRuleCreateForm('2026-08-05', '2026-08-12')
    component.setupState.rateRuleForm.price_per_night = 80
    component.setupState.rateRuleForm.min_stay = 1

    mockApi.mockRejectedValueOnce({
      data: { detail: 'This date range overlaps an existing rate rule for this apartment' },
    })

    await component.setupState.submitRateRuleForm()

    expect(mockToastAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        color: 'error',
        description: 'This date range overlaps an existing rate rule for this apartment',
      }),
    )
  })
})
