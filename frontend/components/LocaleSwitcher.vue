<script setup lang="ts">
const { locale, locales, setLocale } = useI18n()
</script>

<template>
  <div class="inline-flex overflow-hidden rounded-md border border-neutral-200">
    <button
      v-for="loc in locales"
      :key="loc.code"
      type="button"
      class="px-2 py-1 text-xs font-medium transition-colors"
      :class="
        loc.code === locale
          ? 'bg-brand-500 text-white'
          : 'bg-white text-neutral-500 hover:bg-neutral-50'
      "
      :disabled="loc.code === locale"
      @click="setLocale(loc.code)"
    >
      {{ loc.code.toUpperCase() }}
    </button>
  </div>
</template>
