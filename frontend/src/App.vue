<script setup lang="ts">
import { ref } from 'vue'

const apiUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const status = ref<'checking' | 'online' | 'offline'>('checking')

fetch(`${apiUrl}/health`)
  .then((res) => {
    status.value = res.ok ? 'online' : 'offline'
  })
  .catch(() => {
    status.value = 'offline'
  })
</script>

<template>
  <main>
    <h1>Ondas do Mar</h1>
    <p>Backend status: {{ status }}</p>
  </main>
</template>

<style scoped>
main {
  font-family: system-ui, sans-serif;
  text-align: center;
  margin-top: 4rem;
}
</style>
