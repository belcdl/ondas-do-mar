import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AvailabilityCalendar from '../components/AvailabilityCalendar.vue'

const { mockApi } = vi.hoisted(() => ({
  mockApi: vi.fn(),
}))

// Same mocking boundary as panelCalendar.test.ts/publicApartment.test.ts:
// useApi is mocked, everything else (including the day-classification logic
// under test) runs for real. v-calendar's own rendering isn't asserted on
// here, same rationale as panelCalendar.test.ts.
mockNuxtImport('useApi', () => () => mockApi)

function toIsoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

describe('AvailabilityCalendar component', () => {
  beforeEach(() => {
    mockApi.mockReset()
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 7, 1, 12, 0, 0)) // 2026-08-01
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('requests the pricing calendar for today through +180 days on mount', async () => {
    mockApi.mockResolvedValueOnce([])
    const today = new Date()
    const rangeEnd = new Date(today)
    rangeEnd.setDate(rangeEnd.getDate() + 180)

    await mountSuspended(AvailabilityCalendar, { props: { apartmentId: 'apt-1' } })

    expect(mockApi).toHaveBeenCalledWith('/apartments/apt-1/pricing-calendar', {
      query: { from_date: toIsoDate(today), to_date: toIsoDate(rangeEnd) },
    })
  })

  it('shows an available priced day in green with the price, collapsing whole-number cents', async () => {
    mockApi.mockResolvedValueOnce([{ date: '2026-08-05', price: '120.00', available: true }])

    const component = await mountSuspended(AvailabilityCalendar, {
      props: { apartmentId: 'apt-1' },
    })

    const info = component.setupState.dayInfo('2026-08-05')
    expect(info.classes).toEqual({ 'bg-green-100 text-green-800': true })
    expect(info.priceLabel).toBe('120 €')
  })

  it('shows real cents with a comma decimal separator', async () => {
    mockApi.mockResolvedValueOnce([{ date: '2026-08-05', price: '120.50', available: true }])

    const component = await mountSuspended(AvailabilityCalendar, {
      props: { apartmentId: 'apt-1' },
    })

    expect(component.setupState.dayInfo('2026-08-05').priceLabel).toBe('120,50 €')
  })

  it('shows a booked day in red', async () => {
    mockApi.mockResolvedValueOnce([{ date: '2026-08-06', price: '120.00', available: false }])

    const component = await mountSuspended(AvailabilityCalendar, {
      props: { apartmentId: 'apt-1' },
    })

    const info = component.setupState.dayInfo('2026-08-06')
    expect(info.classes).toEqual({ 'bg-red-100 text-red-800': true })
  })

  it('does not break on a day with no rate rule yet', async () => {
    mockApi.mockResolvedValueOnce([{ date: '2026-08-07', price: null, available: true }])

    const component = await mountSuspended(AvailabilityCalendar, {
      props: { apartmentId: 'apt-1' },
    })

    const info = component.setupState.dayInfo('2026-08-07')
    expect(info.classes).toEqual({ 'bg-neutral-100 text-neutral-500': true })
    expect(info.priceLabel).toBeNull()
  })
})
