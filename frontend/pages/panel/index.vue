<script setup lang="ts">
const { t } = useI18n()
</script>

<template>
  <UCard>
    <div class="flex flex-col items-start gap-4">
      <p class="text-neutral-600">{{ t('panel.placeholder') }}</p>
      <UButton
        to="/panel/apartments"
        icon="i-lucide-building-2"
        :label="t('panel.apartmentsLink')"
      />
    </div>
  </UCard>
</template>
