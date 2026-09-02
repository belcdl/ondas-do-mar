<script setup lang="ts">
withDefaults(
  defineProps<{
    /** Pixel height; width follows automatically (the source image's own
     * aspect ratio is ~2:1). Kept a plain number, not a Tailwind class, so
     * every call site can pick an exact size without inventing new utility
     * classes per usage. */
    height?: number
    /** Where the logo links to. Defaults to "/", which is fine on public
     * pages (it just redirects to /login, effectively "home" for a guest)
     * — but inside the authenticated panel, "/" would bounce a logged-in
     * owner straight back to /login (nuxt.config.ts's routeRules redirect
     * is unconditional, it doesn't check auth state). Pass to="/panel"
     * wherever the logo is shown inside the panel. */
    to?: string
  }>(),
  { height: 40, to: '/' },
)
</script>

<template>
  <NuxtLinkLocale :to="to" class="inline-flex items-center" aria-label="Ondas do Mar">
    <img
      src="/logo.jpg"
      alt="Ondas do Mar — Boutique Apartments"
      :style="{ height: `${height}px`, width: 'auto' }"
    />
  </NuxtLinkLocale>
</template>
