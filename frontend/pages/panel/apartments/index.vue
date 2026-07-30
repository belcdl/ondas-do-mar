<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

definePageMeta({ middleware: 'auth' })

interface Apartment {
  id: string
  owner_id: string
  name: string
  address_line: string
  city: string
  postal_code: string | null
  country: string
  description: string | null
  bedrooms: number | null
  max_guests: number
  is_active: boolean
  created_at: string
  updated_at: string
}

interface ApartmentFormState {
  name: string
  address_line: string
  city: string
  postal_code: string | null
  country: string
  description: string | null
  bedrooms: number | null
  max_guests: number | null
}

const api = useApi()
const { t } = useI18n()
const toast = useToast()
const { fetchOwner } = useOwner()

// No linked Owner (an admin, or a not-yet-linked owner-role user) — both
// real possibilities per app/api/deps.py's get_current_owner_or_none.
const owner = await fetchOwner()

function errorDetail(error: unknown): string | undefined {
  const data = (error as { data?: { detail?: unknown } } | undefined)?.data
  return typeof data?.detail === 'string' ? data.detail : undefined
}

const apartments = ref<Apartment[]>([])
const showInactive = ref(false)
const isLoadingApartments = ref(false)

async function loadApartments() {
  isLoadingApartments.value = true
  try {
    // GET /apartments is already scoped server-side to the caller's own
    // apartments for an owner-role user (see api/apartments.py's
    // list_apartments) — no client-side filtering needed here.
    apartments.value = await api<Apartment[]>('/apartments', {
      query: { include_inactive: showInactive.value },
    })
  } catch (error) {
    toast.add({
      title: t('panelApartments.toast.loadError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isLoadingApartments.value = false
  }
}

if (owner) {
  await loadApartments()
}

watch(showInactive, () => {
  if (owner) loadApartments()
})

const columns: TableColumn<Apartment>[] = [
  { accessorKey: 'name', header: t('panelApartments.table.name') },
  { accessorKey: 'city', header: t('panelApartments.table.city') },
  { accessorKey: 'bedrooms', header: t('panelApartments.table.bedrooms') },
  { accessorKey: 'max_guests', header: t('panelApartments.table.maxGuests') },
  { accessorKey: 'is_active', header: t('panelApartments.table.status') },
  { id: 'actions', header: t('panelApartments.table.actions') },
]

function emptyForm(): ApartmentFormState {
  return {
    name: '',
    address_line: '',
    city: '',
    postal_code: null,
    country: '',
    description: null,
    bedrooms: null,
    max_guests: 4,
  }
}

const isFormOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingApartmentId = ref<string | null>(null)
const isSubmittingForm = ref(false)
const form = reactive<ApartmentFormState>(emptyForm())

function openCreateForm() {
  formMode.value = 'create'
  editingApartmentId.value = null
  Object.assign(form, emptyForm())
  isFormOpen.value = true
}

function openEditForm(apartment: Apartment) {
  formMode.value = 'edit'
  editingApartmentId.value = apartment.id
  Object.assign(form, {
    name: apartment.name,
    address_line: apartment.address_line,
    city: apartment.city,
    postal_code: apartment.postal_code,
    country: apartment.country,
    description: apartment.description,
    bedrooms: apartment.bedrooms,
    max_guests: apartment.max_guests,
  })
  isFormOpen.value = true
}

async function onSubmitForm() {
  // The API rejects an owner creating/editing an apartment for anyone but
  // themselves (authorize_owner_match in deps.py) — owner_id always comes
  // from the logged-in owner's own profile, never from the form.
  if (!owner) return

  isSubmittingForm.value = true
  try {
    if (formMode.value === 'create') {
      await api('/apartments', {
        method: 'POST',
        body: { ...form, owner_id: owner.id },
      })
      toast.add({ title: t('panelApartments.toast.createSuccess'), color: 'success' })
    } else if (editingApartmentId.value) {
      await api(`/apartments/${editingApartmentId.value}`, {
        method: 'PATCH',
        body: { ...form },
      })
      toast.add({ title: t('panelApartments.toast.updateSuccess'), color: 'success' })
    }
    isFormOpen.value = false
    await loadApartments()
  } catch (error) {
    toast.add({
      title:
        formMode.value === 'create'
          ? t('panelApartments.toast.createError')
          : t('panelApartments.toast.updateError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isSubmittingForm.value = false
  }
}

const isConfirmOpen = ref(false)
const apartmentPendingDeactivation = ref<Apartment | null>(null)
const isDeactivating = ref(false)

function askDeactivate(apartment: Apartment) {
  apartmentPendingDeactivation.value = apartment
  isConfirmOpen.value = true
}

async function confirmDeactivate() {
  if (!apartmentPendingDeactivation.value) return

  isDeactivating.value = true
  try {
    await api(`/apartments/${apartmentPendingDeactivation.value.id}/deactivate`, {
      method: 'POST',
    })
    toast.add({ title: t('panelApartments.toast.deactivateSuccess'), color: 'success' })
    isConfirmOpen.value = false
    await loadApartments()
  } catch (error) {
    toast.add({
      title: t('panelApartments.toast.deactivateError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isDeactivating.value = false
  }
}
</script>

<template>
  <div>
    <h2>{{ t('panelApartments.title') }}</h2>

    <p v-if="!owner">{{ t('panelApartments.noLinkedOwner') }}</p>

    <template v-else>
      <div class="flex items-center justify-between gap-4 py-4">
        <UCheckbox v-model="showInactive" :label="t('panelApartments.showInactive')" />
        <UButton :label="t('panelApartments.newApartment')" @click="openCreateForm" />
      </div>

      <UTable
        :data="apartments"
        :columns="columns"
        :loading="isLoadingApartments"
        :empty="t('panelApartments.empty')"
      >
        <template #bedrooms-cell="{ row }">
          {{ row.original.bedrooms ?? '—' }}
        </template>
        <template #is_active-cell="{ row }">
          <UBadge
            :color="row.original.is_active ? 'success' : 'neutral'"
            :label="
              row.original.is_active
                ? t('panelApartments.status.active')
                : t('panelApartments.status.inactive')
            "
          />
        </template>
        <template #actions-cell="{ row }">
          <div class="flex gap-2">
            <UButton
              size="sm"
              variant="ghost"
              :label="t('panelApartments.actions.edit')"
              @click="openEditForm(row.original)"
            />
            <UButton
              size="sm"
              variant="ghost"
              :label="t('panelApartments.actions.rateRules')"
              :to="`/panel/apartments/${row.original.id}/rate-rules`"
            />
            <UButton
              v-if="row.original.is_active"
              size="sm"
              variant="ghost"
              color="error"
              :label="t('panelApartments.actions.deactivate')"
              @click="askDeactivate(row.original)"
            />
          </div>
        </template>
      </UTable>

      <UModal
        v-model:open="isFormOpen"
        :title="formMode === 'create' ? t('panelApartments.form.createTitle') : t('panelApartments.form.editTitle')"
      >
        <template #body>
          <form id="apartment-form" class="flex flex-col gap-4" @submit.prevent="onSubmitForm">
            <UFormField :label="t('panelApartments.form.name')" required>
              <UInput v-model="form.name" required class="w-full" />
            </UFormField>
            <UFormField :label="t('panelApartments.form.addressLine')" required>
              <UInput v-model="form.address_line" required class="w-full" />
            </UFormField>
            <UFormField :label="t('panelApartments.form.city')" required>
              <UInput v-model="form.city" required class="w-full" />
            </UFormField>
            <UFormField :label="t('panelApartments.form.postalCode')">
              <UInput v-model="form.postal_code" class="w-full" />
            </UFormField>
            <UFormField :label="t('panelApartments.form.country')" required>
              <UInput v-model="form.country" required class="w-full" />
            </UFormField>
            <UFormField :label="t('panelApartments.form.description')">
              <UTextarea v-model="form.description" :rows="3" class="w-full" />
            </UFormField>
            <UFormField :label="t('panelApartments.form.bedrooms')">
              <UInputNumber v-model="form.bedrooms" :min="0" class="w-full" />
            </UFormField>
            <UFormField :label="t('panelApartments.form.maxGuests')">
              <UInputNumber v-model="form.max_guests" :min="1" class="w-full" />
            </UFormField>
          </form>
        </template>
        <template #footer="{ close }">
          <UButton variant="ghost" :label="t('panelApartments.form.cancel')" @click="close" />
          <UButton
            type="submit"
            form="apartment-form"
            :label="t('panelApartments.form.submit')"
            :loading="isSubmittingForm"
          />
        </template>
      </UModal>

      <UModal v-model:open="isConfirmOpen" :title="t('panelApartments.deactivateConfirm.title')">
        <template #body>
          <p>
            {{
              t('panelApartments.deactivateConfirm.message', {
                name: apartmentPendingDeactivation?.name ?? '',
              })
            }}
          </p>
        </template>
        <template #footer="{ close }">
          <UButton
            variant="ghost"
            :label="t('panelApartments.deactivateConfirm.cancel')"
            @click="close"
          />
          <UButton
            color="error"
            :label="t('panelApartments.deactivateConfirm.confirm')"
            :loading="isDeactivating"
            @click="confirmDeactivate"
          />
        </template>
      </UModal>
    </template>
  </div>
</template>
