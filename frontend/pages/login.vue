<script setup lang="ts">
const { login } = useAuth()
const { t } = useI18n()

const email = ref('')
const password = ref('')
const errorMessage = ref('')
const isSubmitting = ref(false)

async function onSubmit() {
  errorMessage.value = ''
  isSubmitting.value = true
  const result = await login(email.value, password.value)
  isSubmitting.value = false

  if (result.success) {
    await navigateTo('/panel')
  } else {
    errorMessage.value = t(result.errorKey)
  }
}
</script>

<template>
  <div>
    <LocaleSwitcher />
    <h1>{{ t('login.title') }}</h1>
    <form @submit.prevent="onSubmit">
      <div>
        <label for="email">{{ t('login.email') }}</label>
        <input id="email" v-model="email" type="email" autocomplete="username" required />
      </div>
      <div>
        <label for="password">{{ t('login.password') }}</label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
        />
      </div>
      <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>
      <button type="submit" :disabled="isSubmitting">{{ t('login.submit') }}</button>
    </form>
  </div>
</template>
