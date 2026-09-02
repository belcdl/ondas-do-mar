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

interface AvailabilityResult {
  apartment_id: string
  name: string
  nights: number
  currency: string
  price_total: string
}

const api = useApi()
const { t } = useI18n()
const localePath = useLocalePath()
const requestUrl = useRequestURL()

// Same SEO pattern as apartamentos/[id]/index.vue (Part A): useLocaleHead()
// for the hreflang alternates, plus a canonical link built from the actual
// request host rather than a hardcoded production domain (that's deferred —
// see nuxt.config.ts's i18n.baseUrl gap).
const i18nHead = useLocaleHead()
useHead(() => ({
  htmlAttrs: { lang: i18nHead.value.htmlAttrs?.lang },
  link: [...(i18nHead.value.link || []), { rel: 'canonical', href: requestUrl.href }],
  meta: [...(i18nHead.value.meta || [])],
}))
useSeoMeta({
  title: t('home.seo.title'),
  description: t('home.seo.description'),
  ogTitle: t('home.seo.title'),
  ogDescription: t('home.seo.description'),
  ogUrl: requestUrl.href,
})

const apartments = ref<PublicApartment[]>([])

async function loadApartments() {
  try {
    apartments.value = await api<PublicApartment[]>('/apartments/public')
  } catch {
    apartments.value = []
  }
}
await loadApartments()

// Only a handful of apartments exist (see backend's GET /apartments/public —
// no pagination needed there either) — a plain slice is enough, no need for
// the teaser to track its own loading/empty state beyond "show what came back".
const teaserApartments = computed(() => apartments.value.slice(0, 6))

// Hero availability widget — same check-then-list logic as disponibilidad.vue,
// kept inline here rather than shared since the two pages present results
// differently (a compact list here vs. a full table there).
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
    errorMessage.value = t('home.hero.error')
  } finally {
    hasSearched.value = true
    isSearching.value = false
  }
}
</script>

<template>
  <div class="min-h-screen bg-neutral-50">
    <SiteHeader />

    <section
      id="reservar"
      class="relative flex min-h-[34rem] scroll-mt-16 items-center justify-center overflow-hidden px-4 py-20 text-center"
    >
      <!-- Placeholder hero photo (real property photos pending, this is a
           first test shot) — a dark gradient overlay keeps the white
           wordmark/text legible on top of whatever image ends up here.
           Both are position:absolute with no z-index (stack level 0), which
           CSS paints *after* plain in-flow content — without the z-10
           wrapper below, they'd end up covering the search card instead of
           sitting behind it. -->
      <img
        src="/images/hero-ria.jpg"
        :alt="t('home.hero.imageAlt')"
        class="absolute inset-0 h-full w-full object-cover [object-position:50%_65%]"
      />
      <div class="absolute inset-0 bg-gradient-to-br from-brand-900/80 via-brand-800/60 to-sun-700/50" />

      <div class="relative z-10 flex w-full flex-col items-center gap-8">
        <div class="flex flex-col items-center gap-4">
          <AppLogo variant="wordmark" :height="56" />
          <h1 class="max-w-xl text-3xl font-semibold text-white sm:text-4xl">
            {{ t('home.hero.tagline') }}
          </h1>
        </div>

        <UCard class="w-full max-w-3xl text-left" :ui="{ root: 'bg-white/95' }">
          <form
            class="grid grid-cols-1 gap-4 sm:grid-cols-4 sm:items-end"
            @submit.prevent="onSearch"
          >
            <UFormField :label="t('home.hero.checkIn')" class="sm:col-span-1">
              <UInput v-model="checkIn" type="date" required class="w-full" />
            </UFormField>
            <UFormField :label="t('home.hero.checkOut')" class="sm:col-span-1">
              <UInput v-model="checkOut" type="date" required class="w-full" />
            </UFormField>
            <UFormField :label="t('home.hero.guests')" class="sm:col-span-1">
              <UInputNumber v-model="guests" :min="1" class="w-full" />
            </UFormField>
            <UButton
              type="submit"
              block
              size="lg"
              class="rounded-full sm:col-span-1"
              :loading="isSearching"
              :label="t('home.hero.search')"
            />
          </form>
        </UCard>

        <UAlert
          v-if="errorMessage"
          class="w-full max-w-3xl"
          color="error"
          variant="soft"
          :title="errorMessage"
          role="alert"
        />

        <UCard v-if="hasSearched && results.length" class="w-full max-w-3xl text-left">
          <ul class="flex flex-col divide-y divide-neutral-200">
            <li
              v-for="result in results"
              :key="result.apartment_id"
              class="flex items-center justify-between gap-4 py-3"
            >
              <div>
                <p class="font-medium text-neutral-800">{{ result.name }}</p>
                <p class="text-sm text-neutral-500">
                  {{ result.nights }} · {{ result.price_total }} {{ result.currency }}
                </p>
              </div>
              <UButton
                size="sm"
                variant="ghost"
                class="rounded-full"
                :label="t('home.hero.viewListing')"
                :to="localePath(`/apartamentos/${result.apartment_id}`)"
              />
            </li>
          </ul>
        </UCard>

        <p v-else-if="hasSearched && !errorMessage" class="text-white/90">
          {{ t('home.hero.noResults') }}
        </p>
      </div>
    </section>

    <section class="mx-auto max-w-6xl px-4 py-16">
      <h2 class="text-center text-2xl font-semibold text-neutral-800">
        {{ t('home.teaser.title') }}
      </h2>

      <div class="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        <NuxtLinkLocale
          v-for="apartment in teaserApartments"
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
          </div>
        </NuxtLinkLocale>
      </div>

      <div class="mt-10 flex justify-center">
        <UButton
          :label="t('home.teaser.viewAll')"
          :to="localePath('/apartamentos')"
          size="lg"
          class="rounded-full"
        />
      </div>
    </section>

    <section id="nosotros" class="scroll-mt-16 bg-white px-4 py-16">
      <div class="mx-auto max-w-3xl text-center">
        <h2 class="text-2xl font-semibold text-neutral-800">{{ t('home.nosotros.title') }}</h2>
        <p class="mt-4 text-neutral-700">{{ t('home.nosotros.body') }}</p>
        <p class="mt-2 text-sm italic text-neutral-400">{{ t('home.nosotros.pending') }}</p>
      </div>
    </section>

    <section id="entorno" class="scroll-mt-16 px-4 py-16">
      <div class="mx-auto max-w-3xl text-center">
        <h2 class="text-2xl font-semibold text-neutral-800">{{ t('home.entorno.title') }}</h2>
        <p class="mt-4 text-neutral-700">{{ t('home.entorno.body') }}</p>
        <p class="mt-2 text-sm italic text-neutral-400">{{ t('home.entorno.pending') }}</p>
      </div>

      <!-- First test photos, not final property shots — swap freely once
           real ones are ready. -->
      <div class="mx-auto mt-10 grid max-w-5xl grid-cols-2 gap-4 sm:grid-cols-4">
        <img
          src="/images/entorno-sillas.jpg"
          :alt="t('home.entorno.gallery.sillas')"
          loading="lazy"
          class="h-40 w-full rounded-2xl object-cover sm:h-56"
        />
        <img
          src="/images/entorno-paseo.jpg"
          :alt="t('home.entorno.gallery.paseo')"
          loading="lazy"
          class="h-40 w-full rounded-2xl object-cover sm:h-56"
        />
        <img
          src="/images/entorno-conchas.jpg"
          :alt="t('home.entorno.gallery.conchas')"
          loading="lazy"
          class="h-40 w-full rounded-2xl object-cover sm:h-56"
        />
        <img
          src="/images/entorno-playa.jpg"
          :alt="t('home.entorno.gallery.playa')"
          loading="lazy"
          class="h-40 w-full rounded-2xl object-cover sm:h-56"
        />
      </div>
    </section>

    <footer class="border-t border-neutral-200 bg-white px-6 py-8">
      <div class="mx-auto flex max-w-6xl flex-col items-center gap-4 sm:flex-row sm:justify-between">
        <AppLogo :height="32" />
        <p class="text-sm text-neutral-500">
          © {{ new Date().getFullYear() }} Ondas do Mar. {{ t('home.footer.rights') }}
        </p>
      </div>
    </footer>
  </div>
</template>
