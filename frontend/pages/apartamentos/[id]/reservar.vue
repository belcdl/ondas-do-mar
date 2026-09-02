<script setup lang="ts">
interface PublicApartment {
  id: string
  name: string
  max_guests: number
}

interface AvailabilityResult {
  apartment_id: string
  nights: number
  currency: string
  price_total: string
}

const route = useRoute()
const apartmentId = route.params.id as string

const api = useApi()
const { t } = useI18n()
const toast = useToast()

const apartment = ref<PublicApartment | null>(null)
const notFound = ref(false)

// Same reasoning as apartamentos/[id].vue: a missing or deactivated
// apartment is an expected outcome for a guest following a stale link, not
// an error to surface as one.
try {
  apartment.value = await api<PublicApartment>(`/apartments/${apartmentId}/public`)
} catch {
  notFound.value = true
}

function errorDetail(error: unknown): string | undefined {
  const data = (error as { data?: { detail?: unknown } } | undefined)?.data
  return typeof data?.detail === 'string' ? data.detail : undefined
}

function isConflict(error: unknown): boolean {
  return (error as { status?: number } | undefined)?.status === 409
}

const checkIn = ref('')
const checkOut = ref('')
const guests = ref(1)
const isCheckingAvailability = ref(false)
const hasCheckedAvailability = ref(false)
const availabilityResult = ref<AvailabilityResult | null>(null)

async function onCheckAvailability() {
  // Hide the guest-details step immediately — re-checking with different
  // dates must not leave a stale Phase 2 form around that no longer
  // matches what's about to be shown.
  hasCheckedAvailability.value = false
  availabilityResult.value = null
  showConflictError.value = false

  isCheckingAvailability.value = true
  try {
    const results = await api<AvailabilityResult[]>('/availability/search', {
      query: {
        check_in: checkIn.value,
        check_out: checkOut.value,
        guests: guests.value,
      },
    })
    availabilityResult.value = results.find((result) => result.apartment_id === apartmentId) ?? null
  } catch {
    availabilityResult.value = null
  } finally {
    isCheckingAvailability.value = false
    hasCheckedAvailability.value = true
  }
}

const guestFullName = ref('')
const guestEmail = ref('')
const guestPhone = ref('')
const isSubmittingBooking = ref(false)
const showConflictError = ref(false)

async function onSubmitBooking() {
  if (!availabilityResult.value) return

  if (!guestPhone.value) {
    toast.add({
      title: t('bookingForm.phoneRequired'),
      color: 'error',
    })
    return
  }

  showConflictError.value = false
  isSubmittingBooking.value = true
  try {
    const booking = await api<{ id: string }>('/bookings', {
      method: 'POST',
      body: {
        apartment_id: apartmentId,
        guest_full_name: guestFullName.value,
        guest_email: guestEmail.value,
        guest_phone: guestPhone.value || null,
        guest_count: guests.value,
        check_in_date: checkIn.value,
        check_out_date: checkOut.value,
      },
    })

    const session = await api<{ checkout_url: string }>(
      `/bookings/${booking.id}/checkout-session`,
      { method: 'POST' },
    )

    await navigateTo(session.checkout_url, { external: true })
  } catch (error) {
    if (isConflict(error)) {
      // Someone else booked these dates while the guest was filling in the
      // form — the availability just shown is stale, so hide Phase 2 again
      // rather than let them resubmit against dates that no longer hold.
      showConflictError.value = true
      hasCheckedAvailability.value = false
      availabilityResult.value = null
    } else {
      toast.add({
        title: t('bookingForm.submitError'),
        description: errorDetail(error),
        color: 'error',
      })
    }
  } finally {
    isSubmittingBooking.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-neutral-50">
    <SiteHeader />

    <div class="mx-auto flex max-w-xl flex-col gap-6 px-4 pb-16 pt-4">
      <p v-if="notFound" class="text-center text-neutral-500">
        {{ t('bookingForm.apartmentNotFound') }}
      </p>

      <template v-else-if="apartment">
        <h1 class="text-center text-2xl font-semibold text-neutral-800">{{ apartment.name }}</h1>

        <UCard>
          <form class="flex flex-col gap-4" @submit.prevent="onCheckAvailability">
            <UFormField :label="t('bookingForm.checkIn')" required>
              <UInput v-model="checkIn" type="date" required class="w-full" />
            </UFormField>
            <UFormField :label="t('bookingForm.checkOut')" required>
              <UInput v-model="checkOut" type="date" required class="w-full" />
            </UFormField>
            <UFormField :label="t('bookingForm.guests')" required>
              <UInputNumber v-model="guests" :min="1" :max="apartment.max_guests" class="w-full" />
            </UFormField>
            <UButton
              type="submit"
              block
              :loading="isCheckingAvailability"
              :label="t('bookingForm.checkAvailability')"
            />
          </form>
        </UCard>

        <UAlert
          v-if="showConflictError"
          color="error"
          variant="soft"
          :title="t('bookingForm.conflictError')"
          role="alert"
        />

        <p
          v-if="hasCheckedAvailability && !availabilityResult"
          class="text-center text-neutral-500"
        >
          {{ t('bookingForm.notAvailable') }}
        </p>

        <UCard v-if="availabilityResult">
          <h2 class="text-lg font-medium text-neutral-800">
            {{ t('bookingForm.summaryTitle') }}
          </h2>
          <p class="text-neutral-700">
            {{ t('bookingForm.checkInLabel') }}: {{ checkIn }}
          </p>
          <p class="text-neutral-700">
            {{ t('bookingForm.checkOutLabel') }}: {{ checkOut }}
          </p>
          <p class="text-neutral-700">
            {{ t('bookingForm.guestsLabel') }}: {{ guests }}
          </p>
          <p class="text-neutral-700">
            {{ t('bookingForm.nights') }}: {{ availabilityResult.nights }}
          </p>
          <p class="text-neutral-700">
            {{ t('bookingForm.totalPrice') }}: {{ availabilityResult.price_total }}
            {{ availabilityResult.currency }}
          </p>

          <form class="mt-4 flex flex-col gap-4" @submit.prevent="onSubmitBooking">
            <UFormField :label="t('bookingForm.fullName')" required>
              <UInput v-model="guestFullName" required class="w-full" />
            </UFormField>
            <UFormField :label="t('bookingForm.email')" required>
              <UInput v-model="guestEmail" type="email" required class="w-full" />
            </UFormField>
            <UFormField :label="t('bookingForm.phone')" required>
              <UInput v-model="guestPhone" required type="tel" class="w-full" />
            </UFormField>
            <UButton
              type="submit"
              block
              size="lg"
              :loading="isSubmittingBooking"
              :label="t('bookingForm.submit')"
            />
          </form>
        </UCard>
      </template>
    </div>
  </div>
</template>
