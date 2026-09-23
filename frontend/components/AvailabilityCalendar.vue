<script setup lang="ts">
interface DayPricing {
  date: string
  price: string | null
  available: boolean
}

const props = defineProps<{ apartmentId: string }>()

const api = useApi()
const { t } = useI18n()

// The backend allows up to 400 days (see backend/app/services/availability.py's
// _MAX_PRICING_CALENDAR_DAYS) — 180 comfortably covers the 2-month view plus
// forward navigation without needing to refetch on every month change.
const PRICING_CALENDAR_RANGE_DAYS = 180

function toIsoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = new Date()
const rangeEnd = new Date(today)
rangeEnd.setDate(rangeEnd.getDate() + PRICING_CALENDAR_RANGE_DAYS)

const days = ref<DayPricing[]>([])

try {
  days.value = await api<DayPricing[]>(`/apartments/${props.apartmentId}/pricing-calendar`, {
    query: { from_date: toIsoDate(today), to_date: toIsoDate(rangeEnd) },
  })
} catch {
  // Purely informational widget on a public page — if it can't load, just
  // render an empty calendar instead of breaking the apartment page.
}

const daysByDate = computed(() => {
  const map = new Map<string, DayPricing>()
  for (const day of days.value) map.set(day.date, day)
  return map
})

// "120 €" for a whole number, "120,50 €" when there are real cents — the
// API always sends a fixed 2-decimal string (Numeric(10, 2) server-side),
// so ".00" is the only case worth collapsing.
function formatPrice(price: string): string {
  const value = Number(price)
  const formatted = Number.isInteger(value) ? String(value) : value.toFixed(2).replace('.', ',')
  return `${formatted} €`
}

function dayInfo(iso: string): { classes: Record<string, boolean>; priceLabel: string | null } {
  const entry = daysByDate.value.get(iso)

  if (entry && !entry.available) {
    return { classes: { 'bg-red-100 text-red-800': true }, priceLabel: null }
  }
  if (entry && entry.price !== null) {
    return { classes: { 'bg-green-100 text-green-800': true }, priceLabel: formatPrice(entry.price) }
  }
  return { classes: { 'bg-neutral-100 text-neutral-500': true }, priceLabel: null }
}
</script>

<template>
  <div>
    <h2 class="text-lg font-medium text-neutral-800">{{ t('availabilityCalendar.title') }}</h2>

    <div class="mt-2 flex flex-wrap gap-4 text-sm text-neutral-600">
      <span class="flex items-center gap-2">
        <span class="h-3 w-3 rounded bg-green-100"></span>{{ t('availabilityCalendar.legend.available') }}
      </span>
      <span class="flex items-center gap-2">
        <span class="h-3 w-3 rounded bg-red-100"></span>{{ t('availabilityCalendar.legend.booked') }}
      </span>
    </div>

    <ClientOnly>
      <VCalendar :columns="2" :rows="1" expanded class="mt-4">
        <template #day-content="{ day }">
          <div
            class="flex h-full w-full flex-col items-center justify-center rounded"
            :class="dayInfo(day.id).classes"
          >
            <span class="text-sm">{{ day.day }}</span>
            <span v-if="dayInfo(day.id).priceLabel" class="text-[10px] leading-none">
              {{ dayInfo(day.id).priceLabel }}
            </span>
          </div>
        </template>
      </VCalendar>
    </ClientOnly>
  </div>
</template>
