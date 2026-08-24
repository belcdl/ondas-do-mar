<script setup lang="ts">
interface Booking {
  id: string
  apartment_id: string
  guest_count: number
  check_in_date: string
  check_out_date: string
  confirmation_code: string
  status: string
  total_price: string
  currency: string
}

interface PublicApartment {
  id: string
  name: string
}

const route = useRoute()
const api = useApi()
const { t } = useI18n()

const booking = ref<Booking | null>(null)
const apartmentName = ref<string | null>(null)
const notFound = ref(false)

const rawCode = route.query.confirmation_code
const confirmationCode = typeof rawCode === 'string' ? rawCode : ''

if (!confirmationCode) {
  notFound.value = true
} else {
  try {
    booking.value = await api<Booking>(`/bookings/by-confirmation/${confirmationCode}`)
  } catch {
    notFound.value = true
  }
}

// The apartment name is a nice-to-have here, not essential — a guest
// following a Stripe redirect should still see their confirmation code and
// booking details even if this second call fails.
if (booking.value) {
  try {
    const apartment = await api<PublicApartment>(
      `/apartments/${booking.value.apartment_id}/public`,
    )
    apartmentName.value = apartment.name
  } catch {
    apartmentName.value = null
  }
}
</script>

<template>
  <div class="min-h-screen bg-neutral-50">
    <header class="flex items-center justify-between px-6 py-4">
      <AppLogo :height="48" />
      <LocaleSwitcher />
    </header>

    <div class="mx-auto flex max-w-xl flex-col gap-6 px-4 pb-16 pt-4">
      <p v-if="notFound" class="text-center text-neutral-500">
        {{ t('bookingConfirmed.notFound') }}
      </p>

      <UCard v-else-if="booking">
        <div class="flex flex-col items-center gap-2 text-center">
          <UIcon name="i-lucide-check-circle" class="h-12 w-12 text-primary-500" />
          <h1 class="text-2xl font-semibold text-neutral-800">
            {{ t('bookingConfirmed.title') }}
          </h1>
        </div>

        <div class="mt-6 flex flex-col items-center gap-1">
          <p class="text-sm text-neutral-500">
            {{ t('bookingConfirmed.confirmationCodeLabel') }}
          </p>
          <p class="font-mono text-xl font-semibold tracking-wide text-neutral-800">
            {{ booking.confirmation_code }}
          </p>
        </div>

        <div class="mt-6 flex flex-col gap-2 text-neutral-700">
          <p class="text-center font-medium text-neutral-800">
            {{ apartmentName ?? t('bookingConfirmed.apartmentFallback') }}
          </p>
          <p>{{ t('bookingForm.checkInLabel') }}: {{ booking.check_in_date }}</p>
          <p>{{ t('bookingForm.checkOutLabel') }}: {{ booking.check_out_date }}</p>
          <p>{{ t('bookingForm.guestsLabel') }}: {{ booking.guest_count }}</p>
          <p>{{ t('bookingForm.totalPrice') }}: {{ booking.total_price }} {{ booking.currency }}</p>
        </div>
      </UCard>
    </div>
  </div>
</template>
