<script setup lang="ts">
// Shared top nav for every guest-facing page (home, apartment list, apartment
// ficha) — previously each page had its own bare "logo + LocaleSwitcher"
// header, so navigating away from the home page silently dropped the
// Nosotros/Apartamentos/Entorno/Reservar links. Nosotros/Entorno/Reservar are
// sections that only exist on the home page, so from anywhere else they need
// to resolve to "home + hash" rather than a same-page anchor — localePath('/')
// gives the correctly localized home path (e.g. "/" or "/en"), and appending
// the hash to a plain string `to` still lets Nuxt's router parse path+hash
// and scroll to the section after navigating there.
const localePath = useLocalePath()
const { t } = useI18n()
</script>

<template>
  <header
    class="sticky top-0 z-10 flex items-center justify-between gap-4 bg-white/90 px-6 py-3 backdrop-blur"
  >
    <AppLogo :height="40" />

    <nav class="hidden items-center gap-6 text-sm font-medium text-neutral-600 sm:flex">
      <NuxtLink :to="`${localePath('/')}#nosotros`" class="hover:text-primary-600">
        {{ t('home.nav.nosotros') }}
      </NuxtLink>
      <NuxtLinkLocale to="/apartamentos" class="hover:text-primary-600">
        {{ t('home.nav.apartments') }}
      </NuxtLinkLocale>
      <NuxtLink :to="`${localePath('/')}#entorno`" class="hover:text-primary-600">
        {{ t('home.nav.entorno') }}
      </NuxtLink>
    </nav>

    <div class="flex items-center gap-3">
      <LocaleSwitcher />
      <UButton
        :label="t('home.nav.reserve')"
        :to="`${localePath('/')}#reservar`"
        size="sm"
        class="rounded-full"
      />
    </div>
  </header>
</template>
