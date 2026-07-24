<script setup lang="ts">
definePageMeta({ middleware: 'auth' })

const { fetchMe, logout } = useAuth()
const { t } = useI18n()

const user = await fetchMe()
if (!user) {
  await navigateTo('/login')
}

async function onLogout() {
  await logout()
  await navigateTo('/login')
}
</script>

<template>
  <div v-if="user">
    <LocaleSwitcher />
    <h1>{{ t('panel.greeting', { name: user.full_name }) }}</h1>
    <button type="button" @click="onLogout">{{ t('panel.logout') }}</button>
    <p>{{ t('panel.placeholder') }}</p>
  </div>
</template>
