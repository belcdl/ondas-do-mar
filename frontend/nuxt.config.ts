// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  modules: ['@nuxtjs/i18n'],

  // Backend's BACKEND_CORS_ORIGINS is locked to http://localhost:5173 — the
  // dev server must stay on this port, not Nuxt's default 3000.
  devServer: {
    port: 5173,
  },

  // No marketing/guest-facing homepage yet (separate scope) — send / to the
  // one entry point that exists so far rather than 404ing.
  routeRules: {
    '/': { redirect: '/login' },
  },

  runtimeConfig: {
    public: {
      // Overridable via the NUXT_PUBLIC_API_URL env var (Nuxt's runtime-config
      // env convention). Not VITE_API_URL — that's a plain-Vite convention
      // Nuxt's runtimeConfig doesn't read automatically.
      apiUrl: 'http://localhost:8000',
    },
  },

  i18n: {
    // Opt out of @nuxtjs/i18n v9's default `i18n/locales/` layout so
    // locale files can live in the top-level `locales/` dir CLAUDE.md's
    // directory layout calls for.
    restructureDir: false,
    langDir: 'locales/',
    locales: [
      { code: 'es', name: 'Español', file: 'es.json' },
      { code: 'en', name: 'English', file: 'en.json' },
    ],
    defaultLocale: 'es',
    strategy: 'no_prefix',
    bundle: {
      optimizeTranslationDirective: false,
    },
  },
})
