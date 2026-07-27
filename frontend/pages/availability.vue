<script setup lang="ts">
interface NightPrice {
  date: string
  price: string
}

interface AvailabilityResult {
  apartment_id: string
  name: string
  guests: number
  nights: number
  currency: string
  price_total: string
  price_breakdown: NightPrice[]
}

const api = useApi()
const { t } = useI18n()

const checkIn = ref('')
const checkOut = ref('')
const guests = ref(1)
const results = ref<AvailabilityResult[]>([])
const hasSearched = ref(false)
const errorMessage = ref('')
const isSearching = ref(false)

async function onSearch() {
  errorMessage.value = ''
  isSearching.value = true
  try {
    results.value = await api<AvailabilityResult[]>('/availability/search', {
      query: {
        check_in: checkIn.value,
        check_out: checkOut.value,
        guests: guests.value,
      },
    })
  } catch {
    results.value = []
    errorMessage.value = t('availability.error')
  } finally {
    hasSearched.value = true
    isSearching.value = false
  }
}
</script>

<template>
  <div>
    <LocaleSwitcher />
    <h1>{{ t('availability.title') }}</h1>

    <form @submit.prevent="onSearch">
      <div>
        <label for="check-in">{{ t('availability.checkIn') }}</label>
        <input id="check-in" v-model="checkIn" type="date" required />
      </div>
      <div>
        <label for="check-out">{{ t('availability.checkOut') }}</label>
        <input id="check-out" v-model="checkOut" type="date" required />
      </div>
      <div>
        <label for="guests">{{ t('availability.guests') }}</label>
        <input id="guests" v-model.number="guests" type="number" min="1" required />
      </div>
      <button type="submit" :disabled="isSearching">{{ t('availability.search') }}</button>
    </form>

    <p v-if="errorMessage" role="alert">{{ errorMessage }}</p>

    <table v-if="results.length">
      <thead>
        <tr>
          <th>{{ t('availability.table.apartment') }}</th>
          <th>{{ t('availability.table.nights') }}</th>
          <th>{{ t('availability.table.priceTotal') }}</th>
          <th>{{ t('availability.table.available') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="result in results" :key="result.apartment_id">
          <td>{{ result.name }}</td>
          <td>{{ result.nights }}</td>
          <td>{{ result.price_total }} {{ result.currency }}</td>
          <td>{{ t('availability.yes') }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else-if="hasSearched && !errorMessage">{{ t('availability.noResults') }}</p>
  </div>
</template>
