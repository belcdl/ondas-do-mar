<script setup lang="ts">
interface PublicApartment {
  id: string
  name: string
  city: string
  country: string
  bedrooms: number | null
  max_guests: number
  photos: string[]
}

const api = useApi()
const { t } = useI18n()
const requestUrl = useRequestURL()

// Same SEO pattern as index.vue and apartamentos/[id]/index.vue (Part A).
const i18nHead = useLocaleHead()
useHead(() => ({
  htmlAttrs: { lang: i18nHead.value.htmlAttrs?.lang },
  link: [...(i18nHead.value.link || []), { rel: 'canonical', href: requestUrl.href }],
  meta: [...(i18nHead.value.meta || [])],
}))
useSeoMeta({
  title: t('apartmentsList.seo.title'),
  description: t('apartmentsList.seo.description'),
  ogTitle: t('apartmentsList.seo.title'),
  ogDescription: t('apartmentsList.seo.description'),
  ogUrl: requestUrl.href,
})

const apartments = ref<PublicApartment[]>([])
const isLoading = ref(true)
const loadError = ref(false)

try {
  apartments.value = await api<PublicApartment[]>('/apartments/public')
} catch {
  loadError.value = true
} finally {
  isLoading.value = false
}
</script>

<template>
  <div class="min-h-screen bg-neutral-50">
    <SiteHeader />

    <div class="mx-auto max-w-6xl px-4 pb-16 pt-4">
      <h1 class="text-center text-2xl font-semibold text-neutral-800">
        {{ t('apartmentsList.title') }}
      </h1>

      <UAlert
        v-if="loadError"
        class="mt-8"
        color="error"
        variant="soft"
        :title="t('apartmentsList.loadError')"
        role="alert"
      />

      <p v-else-if="!isLoading && !apartments.length" class="mt-8 text-center text-neutral-500">
        {{ t('apartmentsList.empty') }}
      </p>

      <div v-else class="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <NuxtLinkLocale
          v-for="apartment in apartments"
          :key="apartment.id"
          :to="`/apartamentos/${apartment.id}`"
          class="group overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm transition hover:shadow-md"
        >
          <img
            v-if="apartment.photos[0]"
            :src="apartment.photos[0]"
            :alt="`${apartment.name} — ${apartment.city}, ${apartment.country}`"
            loading="lazy"
            class="h-48 w-full object-cover"
          />
          <div v-else class="h-48 w-full bg-neutral-200" />
          <div class="p-4">
            <p class="font-medium text-neutral-800">{{ apartment.name }}</p>
            <p class="text-sm text-neutral-500">{{ apartment.city }}, {{ apartment.country }}</p>
            <p class="mt-1 text-sm text-neutral-500">
              {{ t('apartmentsList.maxGuestsLabel') }}: {{ apartment.max_guests }}
            </p>
          </div>
        </NuxtLinkLocale>
      </div>
    </div>
  </div>
</template>
