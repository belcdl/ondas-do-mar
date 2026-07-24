<script setup lang="ts">
const { locale, locales, setLocale } = useI18n()
</script>

<template>
  <div class="locale-switcher">
    <button
      v-for="loc in locales"
      :key="loc.code"
      type="button"
      :disabled="loc.code === locale"
      @click="setLocale(loc.code)"
    >
      {{ loc.code.toUpperCase() }}
    </button>
  </div>
</template>
