import VCalendar from 'v-calendar'
import 'v-calendar/style.css'

// Registers the <VCalendar>/<VDatePicker> global components (default
// componentPrefix is "V") — the calendar/pricing library CLAUDE.md calls
// for, in place of forcing this use case into Nuxt UI's Calendar.
export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.use(VCalendar, {})
})
