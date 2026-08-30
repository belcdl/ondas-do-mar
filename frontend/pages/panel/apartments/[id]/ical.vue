<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

definePageMeta({ middleware: 'auth' })

interface Apartment {
  id: string
  name: string
}

interface IcalSource {
  id: string
  apartment_id: string
  platform_name: string
  ical_url: string
  last_synced_at: string | null
  last_sync_error: string | null
  created_at: string
  updated_at: string
}

interface IcalSourceFormState {
  platform_name: string
  ical_url: string
}

const route = useRoute()
const apartmentId = route.params.id as string

const api = useApi()
const { t } = useI18n()
const toast = useToast()
const config = useRuntimeConfig()

function errorDetail(error: unknown): string | undefined {
  const data = (error as { data?: { detail?: unknown } } | undefined)?.data
  return typeof data?.detail === 'string' ? data.detail : undefined
}

// GET /apartments/{id} is owner/admin-authorized server-side (403 if it's
// not the caller's apartment, 404 if it doesn't exist at all) — let that
// error propagate instead of catching it here, same as rate-rules.vue.
const apartment = await api<Apartment>(`/apartments/${apartmentId}`)

const exportUrl = `${config.public.apiUrl}/apartments/${apartmentId}/calendar.ics`

async function copyExportUrl() {
  await navigator.clipboard.writeText(exportUrl)
  toast.add({ title: t('panelIcal.copiedToast'), color: 'success' })
}

const icalSources = ref<IcalSource[]>([])
const isLoadingSources = ref(false)

async function loadIcalSources() {
  isLoadingSources.value = true
  try {
    icalSources.value = await api<IcalSource[]>(`/apartments/${apartmentId}/ical-sources`)
  } catch (error) {
    toast.add({
      title: t('panelIcal.toast.loadError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isLoadingSources.value = false
  }
}

await loadIcalSources()

const columns: TableColumn<IcalSource>[] = [
  { accessorKey: 'platform_name', header: t('panelIcal.table.platform') },
  { id: 'lastSynced', header: t('panelIcal.table.lastSynced') },
  { id: 'status', header: t('panelIcal.table.status') },
  { id: 'actions', header: t('panelIcal.table.actions') },
]

const syncingSourceId = ref<string | null>(null)

async function syncNow(source: IcalSource) {
  syncingSourceId.value = source.id
  try {
    const updated = await api<IcalSource>(`/ical-sources/${source.id}/sync-now`, {
      method: 'POST',
    })
    const index = icalSources.value.findIndex((existing) => existing.id === source.id)
    if (index !== -1) icalSources.value[index] = updated
    toast.add({ title: t('panelIcal.toast.syncSuccess'), color: 'success' })
  } catch (error) {
    toast.add({
      title: t('panelIcal.toast.syncError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    syncingSourceId.value = null
  }
}

function emptyForm(): IcalSourceFormState {
  return { platform_name: '', ical_url: '' }
}

const isFormOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingSourceId = ref<string | null>(null)
const isSubmittingForm = ref(false)
const form = reactive<IcalSourceFormState>(emptyForm())

function openCreateForm() {
  formMode.value = 'create'
  editingSourceId.value = null
  Object.assign(form, emptyForm())
  isFormOpen.value = true
}

function openEditForm(source: IcalSource) {
  formMode.value = 'edit'
  editingSourceId.value = source.id
  Object.assign(form, {
    platform_name: source.platform_name,
    ical_url: source.ical_url,
  })
  isFormOpen.value = true
}

async function onSubmitForm() {
  isSubmittingForm.value = true
  try {
    if (formMode.value === 'create') {
      await api(`/apartments/${apartmentId}/ical-sources`, {
        method: 'POST',
        body: { ...form },
      })
      toast.add({ title: t('panelIcal.toast.createSuccess'), color: 'success' })
    } else if (editingSourceId.value) {
      await api(`/ical-sources/${editingSourceId.value}`, {
        method: 'PATCH',
        body: { ...form },
      })
      toast.add({ title: t('panelIcal.toast.updateSuccess'), color: 'success' })
    }
    isFormOpen.value = false
    await loadIcalSources()
  } catch (error) {
    toast.add({
      title:
        formMode.value === 'create'
          ? t('panelIcal.toast.createError')
          : t('panelIcal.toast.updateError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isSubmittingForm.value = false
  }
}

const isConfirmOpen = ref(false)
const sourcePendingDeletion = ref<IcalSource | null>(null)
const isDeleting = ref(false)

function askDelete(source: IcalSource) {
  sourcePendingDeletion.value = source
  isConfirmOpen.value = true
}

async function confirmDelete() {
  if (!sourcePendingDeletion.value) return

  isDeleting.value = true
  try {
    await api(`/ical-sources/${sourcePendingDeletion.value.id}`, { method: 'DELETE' })
    toast.add({ title: t('panelIcal.toast.deleteSuccess'), color: 'success' })
    isConfirmOpen.value = false
    await loadIcalSources()
  } catch (error) {
    toast.add({
      title: t('panelIcal.toast.deleteError'),
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
      {{ t('panelIcal.backLink') }}
    </NuxtLink>
    <h2 class="mt-2 text-xl font-semibold text-neutral-800">
      {{ t('panelIcal.title', { name: apartment.name }) }}
    </h2>

    <div class="mt-4 rounded-lg border border-neutral-200 p-4">
      <h3 class="text-lg font-medium text-neutral-800">
        {{ t('panelIcal.exportSectionTitle') }}
      </h3>
      <UFormField :label="t('panelIcal.exportUrlLabel')" class="mt-2">
        <div class="flex gap-2">
          <UInput :model-value="exportUrl" readonly class="w-full" />
          <UButton
            icon="i-lucide-copy"
            :label="t('panelIcal.copyButton')"
            variant="outline"
            @click="copyExportUrl"
          />
        </div>
      </UFormField>
      <p class="mt-2 text-sm text-neutral-500">{{ t('panelIcal.exportUrlNote') }}</p>
    </div>

    <div class="flex items-center justify-end gap-4 py-4">
      <UButton :label="t('panelIcal.addSource')" @click="openCreateForm" />
    </div>

    <UTable :data="icalSources" :columns="columns" :loading="isLoadingSources">
      <template #lastSynced-cell="{ row }">
        {{
          row.original.last_synced_at
            ? new Date(row.original.last_synced_at).toLocaleString()
            : t('panelIcal.never')
        }}
      </template>
      <template #status-cell="{ row }">
        <UBadge
          :color="row.original.last_sync_error ? 'error' : 'success'"
          :label="row.original.last_sync_error ? t('panelIcal.statusError') : t('panelIcal.statusOk')"
        />
        <p v-if="row.original.last_sync_error" class="mt-1 text-xs text-error-500">
          {{ row.original.last_sync_error }}
        </p>
      </template>
      <template #actions-cell="{ row }">
        <div class="flex gap-2">
          <UButton
            size="sm"
            variant="ghost"
            :label="t('panelIcal.syncNow')"
            :loading="syncingSourceId === row.original.id"
            @click="syncNow(row.original)"
          />
          <UButton
            size="sm"
            variant="ghost"
            :label="t('panelIcal.edit')"
            @click="openEditForm(row.original)"
          />
          <UButton
            size="sm"
            variant="ghost"
            color="error"
            :label="t('panelIcal.delete')"
            @click="askDelete(row.original)"
          />
        </div>
      </template>
    </UTable>

    <UModal
      v-model:open="isFormOpen"
      :title="formMode === 'create' ? t('panelIcal.form.createTitle') : t('panelIcal.form.editTitle')"
    >
      <template #body>
        <form id="ical-source-form" class="flex flex-col gap-4" @submit.prevent="onSubmitForm">
          <UFormField :label="t('panelIcal.form.platformLabel')" required>
            <UInput v-model="form.platform_name" required class="w-full" />
          </UFormField>
          <UFormField :label="t('panelIcal.form.urlLabel')" required>
            <UInput v-model="form.ical_url" type="url" required class="w-full" />
          </UFormField>
        </form>
      </template>
      <template #footer="{ close }">
        <UButton variant="ghost" :label="t('panelIcal.form.cancel')" @click="close" />
        <UButton
          type="submit"
          form="ical-source-form"
          :label="t('panelIcal.form.submit')"
          :loading="isSubmittingForm"
        />
      </template>
    </UModal>

    <UModal v-model:open="isConfirmOpen" :title="t('panelIcal.deleteConfirm.title')">
      <template #body>
        <p>{{ t('panelIcal.deleteConfirm.message') }}</p>
      </template>
      <template #footer="{ close }">
        <UButton variant="ghost" :label="t('panelIcal.deleteConfirm.cancel')" @click="close" />
        <UButton
          color="error"
          :label="t('panelIcal.deleteConfirm.confirm')"
          :loading="isDeleting"
          @click="confirmDelete"
        />
      </template>
    </UModal>
  </div>
</template>
