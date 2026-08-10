// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  modules: ['@nuxtjs/i18n', '@nuxt/ui'],

  css: ['~/assets/css/main.css'],

  app: {
    head: {
      title: 'Ondas do Mar',
      link: [{ rel: 'icon', type: 'image/jpeg', href: '/logo.jpg' }],
    },
  },

  // Backend's BACKEND_CORS_ORIGINS is locked to http://localhost:5173 — the
  // dev server must stay on this port, not Nuxt's default 3000.
  devServer: {
    port: 5173,
  },

  // Docker Desktop on Windows doesn't reliably forward native filesystem
  // change events (inotify) from the host into the Linux container across
  // the bind mount — Vite's dev server can end up never noticing a file
  // changed on disk, silently serving stale JS until the container is
  // fully restarted. Polling checks file mtimes directly instead of
  // waiting for those events, trading a little CPU for actually picking up
  // every edit.
  vite: {
    server: {
      watch: {
        usePolling: true,
      },
    },
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
      // Nuxt's runtimeConfig doesn't read automatically. Includes /api/v1 to
      // match the backend's versioned routes (Decision 043) — this fallback
      // only matters if NUXT_PUBLIC_API_URL isn't set at all.
      apiUrl: 'http://localhost:8000/api/v1',
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
