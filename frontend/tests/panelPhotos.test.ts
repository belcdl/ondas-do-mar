import { mockNuxtImport, mountSuspended } from '@nuxt/test-utils/runtime'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PhotosPage from '../pages/panel/apartments/[id]/photos.vue'

const { mockApi, mockToastAdd } = vi.hoisted(() => ({
  mockApi: vi.fn(),
  mockToastAdd: vi.fn(),
}))

// Same approach as panelRateRules.test.ts: mock useApi/useToast/useRoute at
// the boundary the page actually calls, and supply the [id] dynamic segment
// directly since mounting the component in isolation doesn't go through
// Nuxt's real page router.
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

const PHOTO = {
  id: 'photo-1',
  apartment_id: 'apt-1',
  position: 0,
  created_at: '2026-01-01T00:00:00Z',
  url: 'https://photos.example.com/apartments/apt-1/photo-1.jpg',
}

describe('panel/apartments/[id]/photos page', () => {
  beforeEach(() => {
    mockApi.mockReset()
    mockToastAdd.mockReset()
  })

  it('loads the apartment and lists its photos', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT) // GET /apartments/:id
    mockApi.mockResolvedValueOnce([PHOTO]) // GET /apartments/:id/photos

    const component = await mountSuspended(PhotosPage)

    expect(mockApi).toHaveBeenNthCalledWith(1, '/apartments/apt-1')
    expect(mockApi).toHaveBeenNthCalledWith(2, '/apartments/apt-1/photos')
    expect(component.text()).toContain('Casa Azul')
    expect(component.find(`img[src="${PHOTO.url}"]`).exists()).toBe(true)
  })

  it('uploads a photo and shows a success toast', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([]) // no photos yet
    mockApi.mockResolvedValueOnce(PHOTO) // POST upload response
    mockApi.mockResolvedValueOnce([PHOTO]) // reload after upload

    const component = await mountSuspended(PhotosPage)

    const file = new File(['fake-image-bytes'], 'photo.jpg', { type: 'image/jpeg' })
    await component.setupState.uploadFile(file)

    expect(mockApi).toHaveBeenNthCalledWith(3, '/apartments/apt-1/photos', {
      method: 'POST',
      body: expect.any(FormData),
    })
    const uploadCall = mockApi.mock.calls[2]
    const uploadedFormData = uploadCall[1].body as FormData
    expect(uploadedFormData.get('file')).toBe(file)

    expect(mockToastAdd).toHaveBeenCalledWith(
      expect.objectContaining({ color: 'success' }),
    )
    expect(mockApi).toHaveBeenNthCalledWith(4, '/apartments/apt-1/photos')
  })

  it('shows an error toast with the backend detail when the file type is rejected', async () => {
    mockApi.mockResolvedValueOnce(APARTMENT)
    mockApi.mockResolvedValueOnce([])
    mockApi.mockRejectedValueOnce({
      data: { detail: 'Photo must be one of: image/jpeg, image/png, image/webp' },
    })

    const component = await mountSuspended(PhotosPage)

    const file = new File(['not-an-image'], 'doc.pdf', { type: 'application/pdf' })
    await component.setupState.uploadFile(file)

    expect(mockToastAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        color: 'error',
        description: 'Photo must be one of: image/jpeg, image/png, image/webp',
      }),
    )
  })
})
