import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IcalPage from '../pages/panel/apartments/[id]/ical.vue'

const { mockApi, mockToastAdd } = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockToastAdd: vi.fn(),
}))

// Same mocking boundary as panelRateRules.test.ts/panelPhotos.test.ts:
// useApi/useRoute/useToast are mocked, everything else (including
// useRuntimeConfig, needed for the export URL) runs for real.
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

const SOURCE = {
  id: 'ical-1',
  apartment_id: 'apt-1',
  platform_name: 'Booking.com',
  ical_url: 'https://admin.booking.com/hotel/hoteladmin/ical.ics?t=abc123',
  last_synced_at: null,
  last_sync_error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

describe('panel/apartments/[id]/ical page', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockToastAdd.mockReset()
  })

  it('loads the apartment and lists its iCal sources', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT) // GET /apartments/:id
    mockApi.mockResolvedValueOnce([SOURCE]) // GET /apartments/:id/ical-sources

    const component = await mountSuspended(IcalPage)

    expect(mockApi).toHaveBeenNthCalledWith(1, '/apartments/apt-1')
    expect(mockApi).toHaveBeenNthCalledWith(2, '/apartments/apt-1/ical-sources')
    expect(component.text()).toContain('Casa Azul')
    expect(component.text()).toContain('Booking.com')
  })

  it('creates an iCal source and shows it after reloading the list', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([]) // no sources yet
    mockApi.mockResolvedValueOnce(SOURCE) // POST create response
    mockApi.mockResolvedValueOnce([SOURCE]) // reload after create

    const component = await mountSuspended(IcalPage)

    component.setupState.form.platform_name = 'Booking.com'
    component.setupState.form.ical_url =
      'https://admin.booking.com/hotel/hoteladmin/ical.ics?t=abc123'

    await component.setupState.onSubmitForm()

    expect(mockApi).toHaveBeenNthCalledWith(3, '/apartments/apt-1/ical-sources', {
      method: 'POST',
      body: {
        platform_name: 'Booking.com',
        ical_url: 'https://admin.booking.com/hotel/hoteladmin/ical.ics?t=abc123',
      },
    })
    expect(mockApi).toHaveBeenNthCalledWith(4, '/apartments/apt-1/ical-sources')
    expect(component.text()).toContain('Booking.com')
  })

  it('syncs a source now and updates just that row without reloading the whole list', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([SOURCE])
    const synced = { ...SOURCE, last_synced_at: '2026-08-25T10:00:00Z', last_sync_error: null }
    mockApi.mockResolvedValueOnce(synced) // POST /ical-sources/:id/sync-now response

    const component = await mountSuspended(IcalPage)

    await component.setupState.syncNow(SOURCE)

    expect(mockApi).toHaveBeenNthCalledWith(3, '/ical-sources/ical-1/sync-now', {
      method: 'POST',
    })
    // No extra GET to reload the whole list — only the two initial loads plus the sync call.
    expect(mockApi).toHaveBeenCalledTimes(3)
    expect(component.setupState.icalSources.value).toEqual([synced])
    expect(mockToastAdd).toHaveBeenCalledWith(expect.objectContaining({ color: 'success' }))
  })

  it('deletes a source after confirmation and removes it from the list', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([SOURCE])
    mockApi.mockResolvedValueOnce(undefined) // DELETE
    mockApi.mockResolvedValueOnce([]) // reload after delete

    const component = await mountSuspended(IcalPage)

    component.setupState.askDelete(SOURCE)
    await component.setupState.confirmDelete()

    expect(mockApi).toHaveBeenNthCalledWith(3, '/ical-sources/ical-1', { method: 'DELETE' })
    expect(component.setupState.icalSources.value).toEqual([])
  })

  it('copies the export URL to the clipboard', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([])

    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      configurable: true,
    })

    const component = await mountSuspended(IcalPage)

    await component.setupState.copyExportUrl()

    expect(writeText).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/apartments/apt-1/calendar.ics',
    )
    expect(mockToastAdd).toHaveBeenCalledWith(expect.objectContaining({ color: 'success' }))
  })
})
