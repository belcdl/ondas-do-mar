<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

definePageMeta({ middleware: 'auth' })

interface Apartment {
  id: string
  name: string
}

interface RateRule {
  id: string
  apartment_id: string
  start_date: string
  end_date: string
  price_per_night: string
  min_stay: number
  created_at: string
  updated_at: string
}

interface RateRuleFormState {
  start_date: string
  end_date: string
  price_per_night: number | null
  min_stay: number | null
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
// error propagate instead of catching it here, same as the rest of the
// panel relies on the backend's own authorization rather than duplicating it.
const apartment = await api<Apartment>(`/apartments/${apartmentId}`)

const rateRules = ref<RateRule[]>([])
const isLoadingRateRules = ref(false)

async function loadRateRules() {
  isLoadingRateRules.value = true
  try {
    rateRules.value = await api<RateRule[]>(`/apartments/${apartmentId}/rate-rules`)
  } catch (error) {
    toast.add({
      title: t('panelRateRules.toast.loadError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isLoadingRateRules.value = false
  }
}

await loadRateRules()

const columns: TableColumn<RateRule>[] = [
  { id: 'dateRange', header: t('panelRateRules.table.dateRange') },
  { accessorKey: 'price_per_night', header: t('panelRateRules.table.pricePerNight') },
  { accessorKey: 'min_stay', header: t('panelRateRules.table.minStay') },
  { id: 'actions', header: t('panelRateRules.table.actions') },
]

function emptyForm(): RateRuleFormState {
  return {
    start_date: '',
    end_date: '',
    price_per_night: null,
    min_stay: 1,
  }
}

const isFormOpen = ref(false)
const formMode = ref<'create' | 'edit'>('create')
const editingRateRuleId = ref<string | null>(null)
const isSubmittingForm = ref(false)
const form = reactive<RateRuleFormState>(emptyForm())

function openCreateForm() {
  formMode.value = 'create'
  editingRateRuleId.value = null
  Object.assign(form, emptyForm())
  isFormOpen.value = true
}

function openEditForm(rateRule: RateRule) {
  formMode.value = 'edit'
  editingRateRuleId.value = rateRule.id
  Object.assign(form, {
    start_date: rateRule.start_date,
    end_date: rateRule.end_date,
    price_per_night: Number(rateRule.price_per_night),
    min_stay: rateRule.min_stay,
  })
  isFormOpen.value = true
}

async function onSubmitForm() {
  isSubmittingForm.value = true
  try {
    if (formMode.value === 'create') {
      await api(`/apartments/${apartmentId}/rate-rules`, {
        method: 'POST',
        body: { ...form },
      })
      toast.add({ title: t('panelRateRules.toast.createSuccess'), color: 'success' })
    } else if (editingRateRuleId.value) {
      await api(`/rate-rules/${editingRateRuleId.value}`, {
        method: 'PATCH',
        body: { ...form },
      })
      toast.add({ title: t('panelRateRules.toast.updateSuccess'), color: 'success' })
    }
    isFormOpen.value = false
    await loadRateRules()
  } catch (error) {
    toast.add({
      title:
        formMode.value === 'create'
          ? t('panelRateRules.toast.createError')
          : t('panelRateRules.toast.updateError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isSubmittingForm.value = false
  }
}

const isConfirmOpen = ref(false)
const rateRulePendingDeletion = ref<RateRule | null>(null)
const isDeleting = ref(false)

function askDelete(rateRule: RateRule) {
  rateRulePendingDeletion.value = rateRule
  isConfirmOpen.value = true
}

async function confirmDelete() {
  if (!rateRulePendingDeletion.value) return

  isDeleting.value = true
  try {
    await api(`/rate-rules/${rateRulePendingDeletion.value.id}`, { method: 'DELETE' })
    toast.add({ title: t('panelRateRules.toast.deleteSuccess'), color: 'success' })
    isConfirmOpen.value = false
    await loadRateRules()
  } catch (error) {
    toast.add({
      title: t('panelRateRules.toast.deleteError'),
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
      {{ t('panelRateRules.backLink') }}
    </NuxtLink>
    <h2 class="mt-2 text-xl font-semibold text-neutral-800">
      {{ t('panelRateRules.title', { name: apartment.name }) }}
    </h2>

    <div class="flex items-center justify-end gap-4 py-4">
      <UButton :label="t('panelRateRules.newRule')" @click="openCreateForm" />
    </div>

    <UTable
      :data="rateRules"
      :columns="columns"
      :loading="isLoadingRateRules"
      :empty="t('panelRateRules.empty')"
    >
      <template #dateRange-cell="{ row }">
        {{ row.original.start_date }} — {{ row.original.end_date }}
      </template>
      <template #actions-cell="{ row }">
        <div class="flex gap-2">
          <UButton
            size="sm"
            variant="ghost"
            :label="t('panelRateRules.actions.edit')"
            @click="openEditForm(row.original)"
          />
          <UButton
            size="sm"
            variant="ghost"
            color="error"
            :label="t('panelRateRules.actions.delete')"
            @click="askDelete(row.original)"
          />
        </div>
      </template>
    </UTable>

    <UModal
      v-model:open="isFormOpen"
      :title="formMode === 'create' ? t('panelRateRules.form.createTitle') : t('panelRateRules.form.editTitle')"
    >
      <template #body>
        <form id="rate-rule-form" class="flex flex-col gap-4" @submit.prevent="onSubmitForm">
          <UFormField :label="t('panelRateRules.form.startDate')" required>
            <UInput v-model="form.start_date" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('panelRateRules.form.endDate')" required>
            <UInput v-model="form.end_date" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('panelRateRules.form.pricePerNight')" required>
            <UInputNumber
              v-model="form.price_per_night"
              :min="0.01"
              :step="0.01"
              class="w-full"
            />
          </UFormField>
          <UFormField :label="t('panelRateRules.form.minStay')" required>
            <UInputNumber v-model="form.min_stay" :min="1" class="w-full" />
          </UFormField>
        </form>
      </template>
      <template #footer="{ close }">
        <UButton variant="ghost" :label="t('panelRateRules.form.cancel')" @click="close" />
        <UButton
          type="submit"
          form="rate-rule-form"
          :label="t('panelRateRules.form.submit')"
          :loading="isSubmittingForm"
        />
      </template>
    </UModal>

    <UModal v-model:open="isConfirmOpen" :title="t('panelRateRules.deleteConfirm.title')">
      <template #body>
        <p>
          {{
            t('panelRateRules.deleteConfirm.message', {
              dateRange: rateRulePendingDeletion
                ? `${rateRulePendingDeletion.start_date} — ${rateRulePendingDeletion.end_date}`
                : '',
            })
          }}
        </p>
      </template>
      <template #footer="{ close }">
        <UButton variant="ghost" :label="t('panelRateRules.deleteConfirm.cancel')" @click="close" />
        <UButton
          color="error"
          :label="t('panelRateRules.deleteConfirm.confirm')"
          :loading="isDeleting"
          @click="confirmDelete"
        />
      </template>
    </UModal>
  </div>
</template>
