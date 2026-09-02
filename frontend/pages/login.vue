<script setup lang="ts">
const { login, fetchMe } = useAuth()
const { t } = useI18n()
const localePath = useLocalePath()

// Landing here with an existing, still-valid token (e.g. the logo on a
// public page links to "/", which redirects to /login regardless of auth
// state) shouldn't show the form again — send an already-authenticated
// owner straight to the panel instead.
const existingUser = await fetchMe()
if (existingUser) {
  await navigateTo(localePath('/panel'))
}

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
    await navigateTo(localePath('/panel'))
  } else {
    errorMessage.value = t(result.errorKey)
  }
}
</script>

<template>
  <div class="min-h-screen flex flex-col items-center justify-center gap-8 bg-neutral-50 px-4">
    <div class="absolute top-4 right-4">
      <LocaleSwitcher />
    </div>

    <AppLogo :height="72" />

    <UCard class="w-full max-w-sm" :ui="{ body: 'flex flex-col gap-5' }">
      <h1 class="text-center text-xl font-semibold text-neutral-800">
        {{ t('login.title') }}
      </h1>

      <form class="flex flex-col gap-4" @submit.prevent="onSubmit">
        <UFormField :label="t('login.email')" required>
          <UInput
            v-model="email"
            type="email"
            autocomplete="username"
            required
            icon="i-lucide-mail"
            class="w-full"
          />
        </UFormField>

        <UFormField :label="t('login.password')" required>
          <UInput
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            icon="i-lucide-lock"
            class="w-full"
          />
        </UFormField>

        <UAlert
          v-if="errorMessage"
          color="error"
          variant="soft"
          :title="errorMessage"
          role="alert"
        />

        <UButton
          type="submit"
          block
          size="lg"
          :loading="isSubmitting"
          :label="t('login.submit')"
        />
      </form>
    </UCard>
  </div>
</template>
