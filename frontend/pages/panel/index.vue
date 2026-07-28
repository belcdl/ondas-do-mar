<script setup lang="ts">
const { t } = useI18n()
</script>

<template>
  <div>
    <p>
      <NuxtLink to="/panel/apartments">{{ t('panel.apartmentsLink') }}</NuxtLink>
    </p>
    <p>{{ t('panel.placeholder') }}</p>
  </div>
</template>
