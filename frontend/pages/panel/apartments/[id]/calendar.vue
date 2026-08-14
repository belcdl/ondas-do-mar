<script setup lang="ts">
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

interface BlockedDate {
  id: string
  apartment_id: string
  start_date: string
  end_date: string
  reason: string | null
  created_at: string
  updated_at: string
}

interface Booking {
  id: string
  apartment_id: string
  guest_full_name: string
  check_in_date: string
  check_out_date: string
  status: string
}

type DayStatus = 'booked' | 'blocked' | 'priced' | 'none'

interface DayInfo {
  status: DayStatus
  rateRule?: RateRule
  blockedDate?: BlockedDate
  booking?: Booking
}

interface RateRuleFormState {
  start_date: string
  end_date: string
  price_per_night: number | null
  min_stay: number | null
}

interface BlockedDateFormState {
  start_date: string
  end_date: string
  reason: string
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
// error propagate instead of catching it here, same as rate-rules.vue/photos.vue.
const apartment = await api<Apartment>(`/apartments/${apartmentId}`)

const rateRules = ref<RateRule[]>([])
const blockedDates = ref<BlockedDate[]>([])
const bookings = ref<Booking[]>([])
const isLoadingCalendar = ref(false)

async function loadCalendarData() {
  isLoadingCalendar.value = true
  try {
    const [rateRulesResult, blockedDatesResult, bookingsResult] = await Promise.all([
      api<RateRule[]>(`/apartments/${apartmentId}/rate-rules`),
      api<BlockedDate[]>(`/apartments/${apartmentId}/blocked-dates`),
      api<Booking[]>('/bookings', { query: { apartment_id: apartmentId, status: 'confirmed' } }),
    ])
    rateRules.value = rateRulesResult
    blockedDates.value = blockedDatesResult
    bookings.value = bookingsResult
  } catch (error) {
    toast.add({
      title: t('panelCalendar.toast.loadError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isLoadingCalendar.value = false
  }
}

await loadCalendarData()

function parseLocalDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date)
  result.setDate(result.getDate() + days)
  return result
}

function isoInRange(iso: string, start: string, end: string): boolean {
  return iso >= start && iso <= end
}

// Priority when resolving what a single day "is": a confirmed booking wins
// over a blocked date, which wins over a rate rule — see the task's
// overlap-priority rule. Genuinely overlapping data shouldn't normally
// happen (rate rules/blocked dates each reject their own overlaps
// server-side), but bookings live in a separate table with no such
// constraint against blocked dates, so this still needs a defined order.
function getDayInfo(iso: string): DayInfo {
  const booking = bookings.value.find((b) => iso >= b.check_in_date && iso < b.check_out_date)
  if (booking) return { status: 'booked', booking }

  const blockedDate = blockedDates.value.find((bd) => isoInRange(iso, bd.start_date, bd.end_date))
  if (blockedDate) return { status: 'blocked', blockedDate }

  const rateRule = rateRules.value.find((rr) => isoInRange(iso, rr.start_date, rr.end_date))
  if (rateRule) return { status: 'priced', rateRule }

  return { status: 'none' }
}

interface CalendarAttribute {
  key: string
  dates: { start: Date; end: Date }[]
  highlight: { color: string; fillMode: 'solid' | 'light' }
  popover?: { label: string; visibility: 'hover' }
  order: number
}

// Drives v-calendar's built-in hover popovers (tooltips) — the actual cell
// background/price text is rendered by the day-content slot below instead
// of these highlights, since that slot gives full control over showing the
// price per day.
const attributes = computed<CalendarAttribute[]>(() => {
  const attrs: CalendarAttribute[] = []

  for (const rateRule of rateRules.value) {
    attrs.push({
      key: `rate-${rateRule.id}`,
      dates: [{ start: parseLocalDate(rateRule.start_date), end: parseLocalDate(rateRule.end_date) }],
      highlight: { color: 'blue', fillMode: 'light' },
      popover: {
        label: t('panelCalendar.tooltip.pricePerNight', { price: rateRule.price_per_night }),
        visibility: 'hover',
      },
      order: 1,
    })
  }

  for (const blockedDate of blockedDates.value) {
    attrs.push({
      key: `blocked-${blockedDate.id}`,
      dates: [
        { start: parseLocalDate(blockedDate.start_date), end: parseLocalDate(blockedDate.end_date) },
      ],
      highlight: { color: 'gray', fillMode: 'solid' },
      // reason is optional on BlockedDate (a future iCal-synced block may or
      // may not set it) — only attach a popover when there's something to show.
      ...(blockedDate.reason
        ? { popover: { label: blockedDate.reason, visibility: 'hover' as const } }
        : {}),
      order: 2,
    })
  }

  for (const booking of bookings.value) {
    attrs.push({
      key: `booking-${booking.id}`,
      dates: [
        {
          start: parseLocalDate(booking.check_in_date),
          end: addDays(parseLocalDate(booking.check_out_date), -1),
        },
      ],
      highlight: { color: 'orange', fillMode: 'solid' },
      popover: {
        label: t('panelCalendar.tooltip.booking', {
          name: booking.guest_full_name,
          start: booking.check_in_date,
          end: booking.check_out_date,
        }),
        visibility: 'hover',
      },
      order: 3,
    })
  }

  return attrs
})

function dayContentView(iso: string): { classes: Record<string, boolean>; priceLabel: string | null } {
  const info = getDayInfo(iso)
  return {
    classes: {
      'bg-orange-200 text-orange-900': info.status === 'booked',
      'bg-neutral-300 text-neutral-700': info.status === 'blocked',
      'bg-brand-100 text-brand-800': info.status === 'priced',
      'bg-white text-neutral-400': info.status === 'none',
      'ring-2 ring-brand-500': rangeStart.value === iso,
    },
    priceLabel: info.status === 'priced' ? `${info.rateRule!.price_per_night}€` : null,
  }
}

const rangeStart = ref<string | null>(null)
const selectedRange = reactive({ start: '', end: '' })
const isRangeActionOpen = ref(false)

function onDayClick(day: { id: string }) {
  const iso = day.id

  if (rangeStart.value) {
    completeRangeSelection(iso)
    return
  }

  const info = getDayInfo(iso)
  if (info.status === 'booked') return // read-only — no editing/cancelling bookings from this screen
  if (info.status === 'blocked') {
    openBlockedDateEditForm(info.blockedDate!)
    return
  }
  if (info.status === 'priced') {
    openRateRuleEditForm(info.rateRule!)
    return
  }

  rangeStart.value = iso
}

function completeRangeSelection(iso: string) {
  if (getDayInfo(iso).status === 'booked') return // keep waiting for a valid end date

  const [start, end] = [rangeStart.value as string, iso].sort()
  selectedRange.start = start
  selectedRange.end = end
  rangeStart.value = null
  isRangeActionOpen.value = true
}

function chooseSetPrice() {
  isRangeActionOpen.value = false
  openRateRuleCreateForm(selectedRange.start, selectedRange.end)
}

function chooseBlock() {
  isRangeActionOpen.value = false
  openBlockedDateCreateForm(selectedRange.start, selectedRange.end)
}

function emptyRateRuleForm(): RateRuleFormState {
  return { start_date: '', end_date: '', price_per_night: null, min_stay: 1 }
}

const isRateRuleModalOpen = ref(false)
const rateRuleFormMode = ref<'create' | 'edit'>('create')
const editingRateRuleId = ref<string | null>(null)
const isSubmittingRateRule = ref(false)
const rateRuleForm = reactive<RateRuleFormState>(emptyRateRuleForm())

function openRateRuleCreateForm(startDate: string, endDate: string) {
  rateRuleFormMode.value = 'create'
  editingRateRuleId.value = null
  Object.assign(rateRuleForm, emptyRateRuleForm(), { start_date: startDate, end_date: endDate })
  isRateRuleModalOpen.value = true
}

function openRateRuleEditForm(rateRule: RateRule) {
  rateRuleFormMode.value = 'edit'
  editingRateRuleId.value = rateRule.id
  Object.assign(rateRuleForm, {
    start_date: rateRule.start_date,
    end_date: rateRule.end_date,
    price_per_night: Number(rateRule.price_per_night),
    min_stay: rateRule.min_stay,
  })
  isRateRuleModalOpen.value = true
}

async function submitRateRuleForm() {
  isSubmittingRateRule.value = true
  try {
    if (rateRuleFormMode.value === 'create') {
      await api(`/apartments/${apartmentId}/rate-rules`, {
        method: 'POST',
        body: { ...rateRuleForm },
      })
      toast.add({ title: t('panelCalendar.toast.rateRuleCreateSuccess'), color: 'success' })
    } else if (editingRateRuleId.value) {
      await api(`/rate-rules/${editingRateRuleId.value}`, {
        method: 'PATCH',
        body: { ...rateRuleForm },
      })
      toast.add({ title: t('panelCalendar.toast.rateRuleUpdateSuccess'), color: 'success' })
    }
    isRateRuleModalOpen.value = false
    await loadCalendarData()
  } catch (error) {
    toast.add({
      title:
        rateRuleFormMode.value === 'create'
          ? t('panelCalendar.toast.rateRuleCreateError')
          : t('panelCalendar.toast.rateRuleUpdateError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isSubmittingRateRule.value = false
  }
}

async function deleteRateRule() {
  if (!editingRateRuleId.value) return
  isSubmittingRateRule.value = true
  try {
    await api(`/rate-rules/${editingRateRuleId.value}`, { method: 'DELETE' })
    toast.add({ title: t('panelCalendar.toast.rateRuleDeleteSuccess'), color: 'success' })
    isRateRuleModalOpen.value = false
    await loadCalendarData()
  } catch (error) {
    toast.add({
      title: t('panelCalendar.toast.rateRuleDeleteError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isSubmittingRateRule.value = false
  }
}

function emptyBlockedDateForm(): BlockedDateFormState {
  return { start_date: '', end_date: '', reason: '' }
}

const isBlockedDateModalOpen = ref(false)
const blockedDateFormMode = ref<'create' | 'edit'>('create')
const editingBlockedDateId = ref<string | null>(null)
const isSubmittingBlockedDate = ref(false)
const blockedDateForm = reactive<BlockedDateFormState>(emptyBlockedDateForm())

function openBlockedDateCreateForm(startDate: string, endDate: string) {
  blockedDateFormMode.value = 'create'
  editingBlockedDateId.value = null
  Object.assign(blockedDateForm, emptyBlockedDateForm(), { start_date: startDate, end_date: endDate })
  isBlockedDateModalOpen.value = true
}

function openBlockedDateEditForm(blockedDate: BlockedDate) {
  blockedDateFormMode.value = 'edit'
  editingBlockedDateId.value = blockedDate.id
  Object.assign(blockedDateForm, {
    start_date: blockedDate.start_date,
    end_date: blockedDate.end_date,
    reason: blockedDate.reason ?? '',
  })
  isBlockedDateModalOpen.value = true
}

async function submitBlockedDateForm() {
  isSubmittingBlockedDate.value = true
  try {
    const body = {
      start_date: blockedDateForm.start_date,
      end_date: blockedDateForm.end_date,
      reason: blockedDateForm.reason || null,
    }
    if (blockedDateFormMode.value === 'create') {
      await api(`/apartments/${apartmentId}/blocked-dates`, { method: 'POST', body })
      toast.add({ title: t('panelCalendar.toast.blockedDateCreateSuccess'), color: 'success' })
    } else if (editingBlockedDateId.value) {
      await api(`/blocked-dates/${editingBlockedDateId.value}`, { method: 'PATCH', body })
      toast.add({ title: t('panelCalendar.toast.blockedDateUpdateSuccess'), color: 'success' })
    }
    isBlockedDateModalOpen.value = false
    await loadCalendarData()
  } catch (error) {
    toast.add({
      title:
        blockedDateFormMode.value === 'create'
          ? t('panelCalendar.toast.blockedDateCreateError')
          : t('panelCalendar.toast.blockedDateUpdateError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isSubmittingBlockedDate.value = false
  }
}

async function deleteBlockedDate() {
  if (!editingBlockedDateId.value) return
  isSubmittingBlockedDate.value = true
  try {
    await api(`/blocked-dates/${editingBlockedDateId.value}`, { method: 'DELETE' })
    toast.add({ title: t('panelCalendar.toast.blockedDateDeleteSuccess'), color: 'success' })
    isBlockedDateModalOpen.value = false
    await loadCalendarData()
  } catch (error) {
    toast.add({
      title: t('panelCalendar.toast.blockedDateDeleteError'),
      description: errorDetail(error),
      color: 'error',
    })
  } finally {
    isSubmittingBlockedDate.value = false
  }
}
</script>

<template>
  <div>
    <NuxtLink to="/panel/apartments" class="text-sm text-brand-600 hover:underline">
      {{ t('panelCalendar.backLink') }}
    </NuxtLink>
    <h2 class="mt-2 text-xl font-semibold text-neutral-800">
      {{ t('panelCalendar.title', { name: apartment.name }) }}
    </h2>

    <div class="flex flex-wrap gap-4 py-4 text-sm text-neutral-600">
      <span class="flex items-center gap-2">
        <span class="h-3 w-3 rounded bg-brand-100"></span>{{ t('panelCalendar.legend.priced') }}
      </span>
      <span class="flex items-center gap-2">
        <span class="h-3 w-3 rounded bg-neutral-300"></span>{{ t('panelCalendar.legend.blocked') }}
      </span>
      <span class="flex items-center gap-2">
        <span class="h-3 w-3 rounded bg-orange-200"></span>{{ t('panelCalendar.legend.booked') }}
      </span>
    </div>

    <ClientOnly>
      <VCalendar :attributes="attributes" expanded @dayclick="onDayClick">
        <template #day-content="{ day }">
          <div
            class="flex h-full w-full cursor-pointer flex-col items-center justify-center rounded"
            :class="dayContentView(day.id).classes"
          >
            <span class="text-sm">{{ day.day }}</span>
            <span v-if="dayContentView(day.id).priceLabel" class="text-[10px] leading-none">
              {{ dayContentView(day.id).priceLabel }}
            </span>
          </div>
        </template>
      </VCalendar>
    </ClientOnly>

    <p class="mt-4 text-sm text-neutral-500">{{ t('panelCalendar.legend.noPrice') }}</p>

    <UModal
      v-model:open="isRangeActionOpen"
      :title="t('panelCalendar.rangeAction.title', { start: selectedRange.start, end: selectedRange.end })"
    >
      <template #body>
        <div class="flex flex-col gap-3">
          <UButton :label="t('panelCalendar.rangeAction.setPrice')" @click="chooseSetPrice" />
          <UButton
            :label="t('panelCalendar.rangeAction.block')"
            color="neutral"
            @click="chooseBlock"
          />
        </div>
      </template>
      <template #footer="{ close }">
        <UButton variant="ghost" :label="t('panelCalendar.rangeAction.cancel')" @click="close" />
      </template>
    </UModal>

    <UModal
      v-model:open="isRateRuleModalOpen"
      :title="
        rateRuleFormMode === 'create'
          ? t('panelCalendar.rateRuleForm.createTitle')
          : t('panelCalendar.rateRuleForm.editTitle')
      "
    >
      <template #body>
        <form
          id="calendar-rate-rule-form"
          class="flex flex-col gap-4"
          @submit.prevent="submitRateRuleForm"
        >
          <UFormField :label="t('panelCalendar.rateRuleForm.startDate')" required>
            <UInput v-model="rateRuleForm.start_date" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('panelCalendar.rateRuleForm.endDate')" required>
            <UInput v-model="rateRuleForm.end_date" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('panelCalendar.rateRuleForm.pricePerNight')" required>
            <UInputNumber
              v-model="rateRuleForm.price_per_night"
              :min="0.01"
              :step="0.01"
              class="w-full"
            />
          </UFormField>
          <UFormField :label="t('panelCalendar.rateRuleForm.minStay')" required>
            <UInputNumber v-model="rateRuleForm.min_stay" :min="1" class="w-full" />
          </UFormField>
        </form>
      </template>
      <template #footer="{ close }">
        <UButton
          v-if="rateRuleFormMode === 'edit'"
          variant="ghost"
          color="error"
          :label="t('panelCalendar.rateRuleForm.delete')"
          :loading="isSubmittingRateRule"
          @click="deleteRateRule"
        />
        <UButton variant="ghost" :label="t('panelCalendar.rateRuleForm.cancel')" @click="close" />
        <UButton
          type="submit"
          form="calendar-rate-rule-form"
          :label="t('panelCalendar.rateRuleForm.submit')"
          :loading="isSubmittingRateRule"
        />
      </template>
    </UModal>

    <UModal
      v-model:open="isBlockedDateModalOpen"
      :title="
        blockedDateFormMode === 'create'
          ? t('panelCalendar.blockedDateForm.createTitle')
          : t('panelCalendar.blockedDateForm.editTitle')
      "
    >
      <template #body>
        <form
          id="calendar-blocked-date-form"
          class="flex flex-col gap-4"
          @submit.prevent="submitBlockedDateForm"
        >
          <UFormField :label="t('panelCalendar.blockedDateForm.startDate')" required>
            <UInput v-model="blockedDateForm.start_date" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('panelCalendar.blockedDateForm.endDate')" required>
            <UInput v-model="blockedDateForm.end_date" type="date" required class="w-full" />
          </UFormField>
          <UFormField :label="t('panelCalendar.blockedDateForm.reason')">
            <UInput v-model="blockedDateForm.reason" class="w-full" />
          </UFormField>
        </form>
      </template>
      <template #footer="{ close }">
        <UButton
          v-if="blockedDateFormMode === 'edit'"
          variant="ghost"
          color="error"
          :label="t('panelCalendar.blockedDateForm.delete')"
          :loading="isSubmittingBlockedDate"
          @click="deleteBlockedDate"
        />
        <UButton variant="ghost" :label="t('panelCalendar.blockedDateForm.cancel')" @click="close" />
        <UButton
          type="submit"
          form="calendar-blocked-date-form"
          :label="t('panelCalendar.blockedDateForm.submit')"
          :loading="isSubmittingBlockedDate"
        />
      </template>
    </UModal>
  </div>
</template>
