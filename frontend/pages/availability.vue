<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'

interface NightPrice {
  date: string
  price: string
}

interface AvailabilityResult {
  apartment_id: string
  name: string
  guests: number
  nights: number
  currency: string
  price_total: string
  price_breakdown: NightPrice[]
}

const api = useApi()
const { t } = useI18n()

const checkIn = ref('')
const checkOut = ref('')
const guests = ref(1)
const results = ref<AvailabilityResult[]>([])
const hasSearched = ref(false)
const errorMessage = ref('')
const isSearching = ref(false)

async function onSearch() {
  errorMessage.value = ''
  isSearching.value = true
  try {
    results.value = await api<AvailabilityResult[]>('/availability/search', {
      query: {
        check_in: checkIn.value,
        check_out: checkOut.value,
        guests: guests.value,
      },
    })
  } catch {
    results.value = []
    errorMessage.value = t('availability.error')
  } finally {
    hasSearched.value = true
    isSearching.value = false
  }
}

const columns: TableColumn<AvailabilityResult>[] = [
  { accessorKey: 'name', header: t('availability.table.apartment') },
  { accessorKey: 'nights', header: t('availability.table.nights') },
  { id: 'priceTotal', header: t('availability.table.priceTotal') },
  { id: 'available', header: t('availability.table.available') },
]
</script>

<template>
  <div class="min-h-screen bg-neutral-50">
    <header class="flex items-center justify-between px-6 py-4">
      <AppLogo :height="48" />
      <LocaleSwitcher />
    </header>

    <div class="mx-auto flex max-w-3xl flex-col items-center gap-8 px-4 pb-16 pt-4">
      <h1 class="text-center text-2xl font-semibold text-neutral-800">
        {{ t('availability.title') }}
      </h1>

      <UCard class="w-full">
        <form
          class="grid grid-cols-1 gap-4 sm:grid-cols-4 sm:items-end"
          @submit.prevent="onSearch"
        >
          <UFormField :label="t('availability.checkIn')" class="sm:col-span-1">
            <UInput v-model="checkIn" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('availability.checkOut')" class="sm:col-span-1">
            <UInput v-model="checkOut" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('availability.guests')" class="sm:col-span-1">
            <UInputNumber v-model="guests" :min="1" class="w-full" />
          </UFormField>
          <UButton
            type="submit"
            block
            size="lg"
            :loading="isSearching"
            :label="t('availability.search')"
            class="sm:col-span-1"
          />
        </form>
      </UCard>

      <UAlert
        v-if="errorMessage"
        class="w-full"
        color="error"
        variant="soft"
        :title="errorMessage"
        role="alert"
      />

      <UCard v-if="results.length" class="w-full">
        <UTable :data="results" :columns="columns">
          <template #priceTotal-cell="{ row }">
            {{ row.original.price_total }} {{ row.original.currency }}
          </template>
          <template #available-cell>
            <UBadge color="success" :label="t('availability.yes')" />
          </template>
        </UTable>
      </UCard>

      <p v-else-if="hasSearched && !errorMessage" class="text-neutral-500">
        {{ t('availability.noResults') }}
      </p>
    </div>
  </div>
</template>
