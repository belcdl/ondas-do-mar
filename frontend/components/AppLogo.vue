<script setup lang="ts">
withDefaults(
  defineProps<{
    /** Pixel height; width follows automatically (the source image's own
     * aspect ratio is ~2:1 for `variant="image"`; for `variant="wordmark"`
     * it instead scales the wordmark's font size). Kept a plain number, not
     * a Tailwind class, so every call site can pick an exact size without
     * inventing new utility classes per usage. */
    height?: number
    /** Where the logo links to. Defaults to "/", the real homepage — pass
     * to="/panel" wherever the logo is shown inside the authenticated
     * panel, since "/" there would take a logged-in owner back to the
     * marketing site instead of keeping them in the panel. */
    to?: string
    /** "image" (default) is the raster logo, for light/neutral backgrounds.
     * "wordmark" renders the brand name as text (Fredoka bold + a Dancing
     * Script tagline) in white, for use over a photo or colored hero where
     * the raster logo wouldn't read well. */
    variant?: 'image' | 'wordmark'
  }>(),
  { height: 40, to: '/', variant: 'image' },
)
</script>

<template>
  <NuxtLinkLocale :to="to" class="inline-flex items-center" aria-label="Ondas do Mar — Boutique Apartments">
    <img
      v-if="variant === 'image'"
      src="/logo.jpg"
      alt="Ondas do Mar — Boutique Apartments"
      :style="{ height: `${height}px`, width: 'auto' }"
    />
    <span v-else class="inline-flex flex-col leading-none text-white">
      <span class="font-display font-bold tracking-wide" :style="{ fontSize: `${height * 0.85}px` }">
        Ondas do Mar
      </span>
      <span class="font-script" :style="{ fontSize: `${height * 0.45}px` }">Boutique Apartments</span>
    </span>
  </NuxtLinkLocale>
</template>
