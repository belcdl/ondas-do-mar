<script setup lang="ts">
interface PublicApartment {
  id: string
  name: string
  description: string | null
  address_line: string
  city: string
  postal_code: string | null
  country: string
  bedrooms: number | null
  max_guests: number
  amenities: string[]
  amenities_other: string | null
  photos: string[]
}

const route = useRoute()
const apartmentId = route.params.id as string

const api = useApi()
const { t } = useI18n()

const apartment = ref<PublicApartment | null>(null)
const notFound = ref(false)

// GET .../public is unauthenticated and 404s for a missing or deactivated
// apartment (see api/apartments.py's get_apartment_public) — that's an
// expected outcome for a guest following a stale or mistyped link, not an
// error to surface as one.
try {
  apartment.value = await api<PublicApartment>(`/apartments/${apartmentId}/public`)
} catch {
  notFound.value = true
}
</script>

<template>
  <div class="min-h-screen bg-neutral-50">
    <header class="flex items-center justify-between px-6 py-4">
      <AppLogo :height="48" />
      <LocaleSwitcher />
    </header>

    <div class="mx-auto max-w-3xl px-4 pb-16 pt-4">
      <p v-if="notFound" class="text-center text-neutral-500">
        {{ t('publicApartment.notFound') }}
      </p>

      <template v-else-if="apartment">
        <div class="mb-6">
          <img
            v-if="apartment.photos.length"
            :src="apartment.photos[0]"
            :alt="apartment.name"
            class="h-80 w-full rounded-lg object-cover"
          />
          <div
            v-else
            class="flex h-80 w-full items-center justify-center rounded-lg bg-neutral-200"
          />

          <div v-if="apartment.photos.length > 1" class="mt-2 grid grid-cols-4 gap-2">
            <img
              v-for="photo in apartment.photos.slice(1)"
              :key="photo"
              :src="photo"
              :alt="apartment.name"
              class="h-20 w-full rounded object-cover"
            />
          </div>
        </div>

        <h1 class="text-2xl font-semibold text-neutral-800">{{ apartment.name }}</h1>
        <p class="text-neutral-500">{{ apartment.city }}, {{ apartment.country }}</p>

        <p v-if="apartment.description" class="mt-4 text-neutral-700">
          {{ apartment.description }}
        </p>

        <div class="mt-6 flex gap-6 text-sm text-neutral-600">
          <span>{{ t('publicApartment.bedroomsLabel') }}: {{ apartment.bedrooms ?? '—' }}</span>
          <span>{{ t('publicApartment.maxGuestsLabel') }}: {{ apartment.max_guests }}</span>
        </div>

        <div v-if="apartment.amenities.length" class="mt-6">
          <h2 class="text-lg font-medium text-neutral-800">
            {{ t('publicApartment.amenitiesTitle') }}
          </h2>
          <div class="mt-2 flex flex-wrap gap-2">
            <UBadge
              v-for="amenity in AMENITY_TYPES.filter((value) => apartment!.amenities.includes(value))"
              :key="amenity"
              variant="soft"
              :label="t(`amenities.${amenity}`)"
            />
          </div>
          <p v-if="apartment.amenities_other" class="mt-2 text-sm text-neutral-600">
            {{ apartment.amenities_other }}
          </p>
        </div>

        <UButton
          block
          size="xl"
          class="mt-8"
          :label="t('publicApartment.reserveButton')"
          :to="`/apartamentos/${apartment.id}/reservar`"
        />
      </template>
    </div>
  </div>
</template>
