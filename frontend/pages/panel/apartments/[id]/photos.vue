<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

interface Apartment {
  id: string
  name: string
}

interface ApartmentPhoto {
  id: string
  apartment_id: string
  position: number
  created_at: string
  url: string
}

const route = useRoute()
const apartmentId = route.params.id as string

const api = useApi()
const { t } = useI18n()
const toast = useToast()

function errorDetail(error: unknown): string | undefined {
  const data = (error as { data?: { detail?: unknown } } | undefined)?.data
  return typeof data?.detail === 'string' ? data.detail : undefined
}

// GET /apartments/{id} is owner/admin-authorized server-side (403 if it's
// not the caller's apartment, 404 if it doesn't exist at all) — let that
// error propagate instead of catching it here, same as rate-rules.vue.
const apartment = await api<Apartment>(`/apartments/${apartmentId}`)

const photos = ref<ApartmentPhoto[]>([])
const isLoadingPhotos = ref(false)

async function loadPhotos() {
  isLoadingPhotos.value = true
  try {
    // Already ordered by position server-side (see api/apartment_photos.py).
    photos.value = await api<ApartmentPhoto[]>(`/apartments/${apartmentId}/photos`)
  } catch (error) {
    toast.add({
      title: t('panelPhotos.toast.loadError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isLoadingPhotos.value = false
  }
}

await loadPhotos()

const fileInput = ref<HTMLInputElement | null>(null)
const isUploading = ref(false)

function openFilePicker() {
  fileInput.value?.click()
}

async function uploadFile(file: File) {
  isUploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    // Pass a FormData body directly — $fetch sets the multipart/form-data
    // Content-Type (with boundary) on its own; setting it by hand would
    // break the boundary.
    await api(`/apartments/${apartmentId}/photos`, {
      method: 'POST',
      body: formData,
    })
    toast.add({ title: t('panelPhotos.toast.uploadSuccess'), color: 'success' })
    await loadPhotos()
  } catch (error) {
    toast.add({
      title: t('panelPhotos.toast.uploadError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isUploading.value = false
  }
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  void uploadFile(file)
}

const isConfirmOpen = ref(false)
const photoPendingDeletion = ref<ApartmentPhoto | null>(null)
const isDeleting = ref(false)

function askDelete(photo: ApartmentPhoto) {
  photoPendingDeletion.value = photo
  isConfirmOpen.value = true
}

async function confirmDelete() {
  if (!photoPendingDeletion.value) return

  isDeleting.value = true
  try {
    await api(`/apartments/${apartmentId}/photos/${photoPendingDeletion.value.id}`, {
      method: 'DELETE',
    })
    toast.add({ title: t('panelPhotos.toast.deleteSuccess'), color: 'success' })
    isConfirmOpen.value = false
    await loadPhotos()
  } catch (error) {
    toast.add({
      title: t('panelPhotos.toast.deleteError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isDeleting.value = false
  }
}
</script>

<template>
  <div>
    <NuxtLink to="/panel/apartments" class="text-sm text-brand-600 hover:underline">
      {{ t('panelPhotos.backLink') }}
    </NuxtLink>
    <h2 class="mt-2 text-xl font-semibold text-neutral-800">
      {{ t('panelPhotos.title', { name: apartment.name }) }}
    </h2>

    <div class="flex flex-col items-start gap-2 py-4">
      <UButton
        :label="t('panelPhotos.upload.button')"
        icon="i-lucide-upload"
        :loading="isUploading"
        @click="openFilePicker"
      />
      <input
        ref="fileInput"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        class="hidden"
        @change="onFileSelected"
      />
      <p class="text-sm text-neutral-500">{{ t('panelPhotos.upload.help') }}</p>
    </div>

    <p v-if="!isLoadingPhotos && photos.length === 0" class="text-neutral-500">
      {{ t('panelPhotos.empty') }}
    </p>

    <div v-else class="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
      <div
        v-for="photo in photos"
        :key="photo.id"
        class="relative aspect-square overflow-hidden rounded-lg bg-neutral-100"
      >
        <img :src="photo.url" :alt="apartment.name" class="h-full w-full object-cover" />
        <UButton
          class="absolute top-2 right-2"
          size="sm"
          color="error"
          icon="i-lucide-trash-2"
          @click="askDelete(photo)"
        />
      </div>
    </div>

    <UModal v-model:open="isConfirmOpen" :title="t('panelPhotos.deleteConfirm.title')">
      <template #body>
        <p>{{ t('panelPhotos.deleteConfirm.message') }}</p>
      </template>
      <template #footer="{ close }">
        <UButton variant="ghost" :label="t('panelPhotos.deleteConfirm.cancel')" @click="close" />
        <UButton
          color="error"
          :label="t('panelPhotos.deleteConfirm.confirm')"
          :loading="isDeleting"
          @click="confirmDelete"
        />
      </template>
    </UModal>
  </div>
</template>
