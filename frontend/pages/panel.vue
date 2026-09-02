<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const { fetchMe, logout } = useAuth()
const { t } = useI18n()
const localePath = useLocalePath()

const user = await fetchMe()
if (!user) {
  await navigateTo(localePath('/login'))
}

async function onLogout() {
  await logout()
  await navigateTo(localePath('/login'))
}
</script>

<template>
  <div v-if="user" class="min-h-screen bg-neutral-50">
    <header class="flex items-center justify-between border-b border-neutral-200 bg-white px-6 py-3">
      <AppLogo :height="40" to="/panel" />

      <div class="flex items-center gap-4">
        <span class="hidden text-sm text-neutral-600 sm:inline">
          {{ t('panel.greeting', { name: user.full_name }) }}
        </span>
        <LocaleSwitcher />
        <UButton
          variant="ghost"
          color="neutral"
          size="sm"
          icon="i-lucide-log-out"
          :label="t('panel.logout')"
          @click="onLogout"
        />
      </div>
    </header>

    <main class="mx-auto max-w-5xl px-4 py-8">
      <NuxtPage />
    </main>
  </div>
</template>
