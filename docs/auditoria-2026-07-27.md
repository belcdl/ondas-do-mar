# Auditoría de estado — Ondas do Mar

**Fecha:** 27 de julio de 2026
**Alcance:** revisión completa y de solo lectura del repositorio (backend, frontend, migraciones, tests, Docker, documentación, variables de entorno). No se ha modificado ni implementado nada como parte de esta auditoría.

**Base revisada:** árbol completo de archivos, historial de git, los 20 ficheros de tests del backend (216 tests) y 2 ficheros de tests del frontend (6 tests), los 42 registros de `docs/decisions.md`, `docs/architecture.md`, `CLAUDE.md`, `README.md`, `docker-compose.yml`, ambos `Dockerfile`, `docker/postgres/init.sql`, `.env`/`.env.example`, `backend/pyproject.toml`, `backend/app/main.py`, y el código fuente de los módulos `models/`, `schemas/`, `repositories/`, `services/`, `api/` y `frontend/pages`, `frontend/composables`.

---

## ⚠️ Atención urgente

No hay bugs activos ni funcionalidad rota en este momento. Sí hay dos focos de deriva que conviene corregir pronto, antes de que se acumulen más capas encima:

1. **Dependencias sin usar en el frontend.** `frontend/package.json` arrastra un bloque grande de paquetes `@tiptap/*` (editor de texto enriquecido, ~15 subpaquetes) y `tailwindcss`, introducidos de forma transitiva por `@nuxt/ui` v3 (su componente de editor), aunque en el proyecto solo se usan Tabla/Modal/Formulario/Botón. Esto infla el `node_modules`, el tiempo de instalación/build y la superficie de auditoría de seguridad sin ningún beneficio real. Se puede resolver revisando la configuración de `@nuxt/ui` para excluir ese módulo, o aceptándolo conscientemente si se prevé necesitar un editor enriquecido pronto.
2. **`docs/architecture.md` desactualizado.** Todavía describe el frontend como "Vue 3 + Vite + TypeScript" (la decisión real, ya reflejada en `CLAUDE.md`, es Nuxt 3 SSR/SSG) y describe Stripe Connect de forma genérica como "no implementado", cuando en realidad la integración de pagos de cuenta única (Stripe Checkout) sí está hecha — solo el *payout splitting* multi-propietario (Connect) sigue pendiente. Es un documento de referencia para futuros colaboradores (o para ti dentro de unos meses); vale la pena sincronizarlo.

Ninguno de los dos bloquea el siguiente sprint, pero ambos son deuda de bajo coste y alto valor si se atacan ahora.

---

## 1. Funcionalidades terminadas

**Backend — dominio Owner:** modelo, repositorio, servicio y API CRUD completos (`POST/GET/PATCH /owners`, `GET /owners/me`, `POST /owners/{id}/deactivate`, `GET /owners/{id}/apartments`), con autorización basada en roles (admin/owner) y en pertenencia (`authorize_owner_match`).

**Backend — autenticación:** JWT (PyJWT) con `OAuth2PasswordBearer`, hashing con `passlib[bcrypt]` (pinado a `bcrypt<4.1` por una incompatibilidad real con `passlib`), dependencias `get_current_user` → `get_current_active_user` → `require_admin`/`require_owner`, y un flujo de invitación de propietarios con tokens de un solo uso hasheados en SHA-256 (no bcrypt, porque necesitan búsqueda por coincidencia exacta) y expiración configurable.

**Backend — Apartment:** CRUD completo, autorizado y escopado a su propietario, con endpoint público de listado para el buscador de huéspedes ya cubierto por disponibilidad (ver más abajo). *Salvedad:* el listado/detalle de apartamentos en `api/apartments.py` **no** es público — todas sus rutas exigen usuario autenticado, así que hoy no existe forma de que un huésped vea ficha o fotos de un apartamento fuera del panel.

**Backend — RateRule y motor de precios:** CRUD de reglas de temporada con detección de solapamiento (`OverlappingRateRuleError`) y bloqueo de borrado si está en uso (`RateRuleInUseError`); `RateRuleService.price_stay()` centraliza el cálculo de precio por noche y la validación de estancia mínima, compartido entre `BookingService` y `AvailabilityService` (una sola fuente de verdad, sin lógica duplicada).

**Backend — Booking:** creación **pública** (sin cuenta de huésped, decisión de diseño explícita), con `total_price`/`currency` siempre calculados en servidor, nunca aceptados del cliente. Confirmación, cancelación y finalización idempotentes. Prevención de solapamiento de reservas a nivel de base de datos vía restricción `EXCLUDE USING gist` parcial (solo `status='confirmed'`), reutilizando la extensión `btree_gist` (habilitada en migración, no en `init.sql`) para permitir igualdad de UUID dentro del `EXCLUDE`.

**Backend — Availability:** `GET /availability/search` **público**, combina capacidad (`max_guests`), solapamiento de reservas confirmadas, solapamiento de `blocked_dates` y cobertura/mínimo de `rate_rules` en una sola búsqueda, reutilizando los repositorios existentes sin duplicar reglas.

**Backend — BlockedDate:** modelo y restricción GIST de solapamiento ya existen y se consumen (en modo lectura) desde `AvailabilityService`. **No** tiene schemas, servicio ni API propia — un propietario no puede crear o editar bloqueos todavía (ver Sección 6).

**Backend — Pagos (Stripe, cuenta única, modo test):** `Payment` model, `POST /bookings/{id}/checkout-session`, `POST /webhooks/stripe` con verificación de firma sobre el cuerpo crudo, manejo idempotente de `checkout.session.completed` (confirma la reserva) y `checkout.session.expired` (marca el pago fallido solo si sigue `pending`, protegiendo contra entregas de webhook fuera de orden).

**Backend — infraestructura transversal:** jerarquía de excepciones de dominio centralizada (`ApplicationError` y subclases mapeadas a 404/409/422/401/403) con un único `register_exception_handlers(app)`; healthchecks `/health` y `/health/db`.

**Base de datos:** PostgreSQL 16 con imagen `pgvector/pgvector:pg16`, extensión `vector` habilitada desde el primer arranque (`docker/postgres/init.sql`) para la futura integración de RAG; `btree_gist` habilitada vía migración Alembic para las restricciones de exclusión de `bookings`, `rate_rules` y `blocked_dates`.

**Frontend:** scaffold Nuxt 3 (SSR/SSG) con `@nuxtjs/i18n` (ES por defecto, EN, sin prefijo de ruta) y `@nuxt/ui`; composable único `useApi` envolviendo `$fetch.create`; JWT guardado en cookie (no `localStorage`, por compatibilidad SSR); `useAuth`/`useAuthToken`/`useOwner` y guard `middleware/auth.ts`; página de login; página pública mínima de búsqueda de disponibilidad (`/availability`, HTML plano, sin Nuxt UI, sin flujo de reserva ni checkout); panel de propietario (`/panel`, layout anidado con `/panel/apartments`) con CRUD completo de apartamentos (tabla, modal de alta/edición, baja con confirmación), errores de API mostrados vía `toast`.

**Tests:** 216 tests de backend (pytest + pytest-asyncio, patrón de rollback transaccional por test) repartidos en 20 ficheros; 6 tests de frontend (Vitest, `@nuxt/test-utils`, `happy-dom`) en 2 ficheros. No se ha ejecutado la suite como parte de esta auditoría (fuera de alcance de "solo analiza"); esto es un análisis estático de qué existe, no una verificación de que todo pase.

**Documentación:** `CLAUDE.md` (convenciones, ya corregido para reflejar Nuxt), `docs/decisions.md` (42 decisiones registradas), `README.md` (ya corregido — antes decía que no existían otras entidades de negocio).

---

## 2. Bugs o problemas ya solucionados

- `ModuleNotFoundError: No module named 'app'` al ejecutar `scripts/create_admin.py` directamente → resuelto añadiendo `backend/` al `sys.path` (el proyecto no se instala como paquete editable, coherente con `[tool.uv] package = false`).
- Incompatibilidad de `psycopg` async con el `ProactorEventLoop` por defecto de Windows → resuelto forzando `WindowsSelectorEventLoopPolicy` cuando `sys.platform == "win32"`.
- Incompatibilidad real entre `passlib` y versiones de `bcrypt` ≥ 4.1 → resuelto fijando `bcrypt>=4.0.1,<4.1` en `pyproject.toml`.
- `docker-compose.yml` todavía usaba la variable antigua `VITE_API_URL` en vez de `NUXT_PUBLIC_API_URL` tras el cambio de stack a Nuxt → corregido.
- `README.md` afirmaba que no existían más entidades de negocio aparte de Owner, cuando ya existían Apartment/Booking/RateRule/User/OwnerInvitation → corregido.

**Fricción recurrente sin causa raíz confirmada (no es un bug de código):** bloqueos repetidos de `.git/index.lock`, tanto en tu PowerShell nativa como desde el sandbox — mitigado manualmente cada vez (cerrar VS Code, matar procesos `git.exe` residuales, borrar el lock a mano), sin que se haya identificado con certeza el proceso que lo deja huérfano (sospecha: extensión de Git de VS Code, posiblemente en combinación con OneDrive/antivirus). Puede volver a aparecer.

---

## 3. Decisiones importantes tomadas

- Frontend: **Vue 3 + Nuxt (SSR/SSG)** en vez de Vite+Vue plano o React/Next, priorizando SEO para *direct booking* y porque SSR ya era requisito.
- Pagos: **Stripe Checkout de cuenta única** (hosted page), explícitamente **sin** Stripe Connect por ahora — el reparto de pagos entre los 6 propietarios queda diferido.
- Componentes UI: **Nuxt UI** para tablas/formularios/botones del panel, con `v-calendar` como alternativa de reserva solo si el calendario de Nuxt UI resulta demasiado limitado para necesidades específicas de reservas (marcar días ocupados, precio por día).
- Gestión de dependencias Python: **`uv`**, con `package = false` (es una aplicación, no una librería distribuible).
- Un único driver **`psycopg` v3** para el engine async y para Alembic (sync), evitando mantener dos drivers.
- Prevención de doble reserva **a nivel de base de datos** (no solo en el servicio) vía restricciones `EXCLUDE USING gist`, patrón reutilizado en `bookings`, `rate_rules` y `blocked_dates`.
- Tokens de invitación de propietario hasheados con **SHA-256, no bcrypt** (necesitan búsqueda por coincidencia exacta, no verificación tipo contraseña).
- JWT en **cookie**, no `localStorage` (debe estar disponible en el primer render SSR).
- Creación de reservas **pública**, sin cuenta de huésped (decisión de diseño explícita, documentada en el propio código de `bookings.py`).
- Modelo GDPR: los 6 propietarios como **responsables conjuntos del tratamiento** (Art. 26 RGPD), con el control técnico principal siendo el escopado por fila a nivel de propiedad (`authorize_owner_match`) ya implementado.
- **Hallazgo de esta auditoría, no una decisión explícita anterior:** la API no está versionada — existe `api_v1_str = "/api/v1"` en `Settings`, pero ningún router lo usa como prefijo; todas las rutas cuelgan de la raíz (`/owners`, `/bookings`, etc.). No es un problema funcional hoy, pero es una configuración muerta que conviene decidir explícitamente (usarla o quitarla) antes de que haya clientes externos consumiendo la API sin versión.

---

## 4. CAN WAIT

- Stripe Connect (reparto de pagos entre los 6 propietarios) — diferido explícitamente.
- Sincronización iCal con Booking.com/Airbnb.
- Asistente RAG/LLM.
- Hosting y despliegue a producción.
- Redacción final de Política de Privacidad y Cookies (el análisis legal de impacto técnico ya está hecho; falta el texto).
- Contenido de apartamento multi-idioma real (hoy `description` es un único campo, sin variantes ES/EN) — la UI ya tiene i18n de interfaz, pero el contenido de cada apartamento no. Puede esperar mientras el catálogo sea pequeño y los propietarios puedan escribir la descripción en el idioma que prefieran.

---

## 5. Mejoras futuras

- Limpieza de dependencias: retirar el bloque `@tiptap/*` no usado (ver "Atención urgente").
- Sincronizar `docs/architecture.md` con el estado real (Nuxt, alcance real de Stripe).
- Decidir y aplicar (o eliminar) el versionado `/api/v1` antes de tener consumidores externos.
- Página de disponibilidad (`/availability`) está construida con HTML plano sin Nuxt UI — sería consistente migrarla al mismo sistema de componentes que el panel, una vez se diseñe el flujo de reserva/checkout de huésped completo.
- Extraer una ficha pública de apartamento (fotos, descripción, ubicación) — hoy no existe ninguna ruta pública de detalle, solo el resultado tabular de `/availability/search`.

---

## 6. Funcionalidades pendientes del MVP

**Backend:**
- Schemas + servicio + API CRUD de `BlockedDate` (el modelo y la restricción de solapamiento ya existen; falta todo lo demás para que un propietario pueda gestionar bloqueos).
- Endpoint(s) públicos de detalle de apartamento (foto, descripción, ubicación) — hoy todo `apartments.py` exige autenticación, así que un huésped no puede ver ficha de un apartamento, solo el resultado agregado de disponibilidad.
- Endpoint para iniciar el flujo de checkout desde la búsqueda pública (hoy `POST /bookings/{id}/checkout-session` existe pero no hay nada en el frontend público que lo dispare — ver frontend).

**Frontend:**
- Pantalla de gestión de RateRules (temporadas/precios) para el propietario — no existe todavía, solo backend.
- Pantalla de gestión de BlockedDates para el propietario — bloqueada por el punto de backend anterior.
- Calendario de reservas y bloqueos (visual) — no existe.
- Flujo de reserva de huésped completo: desde `/availability` (que hoy solo muestra una tabla de resultados) hasta la ficha del apartamento, el formulario de datos del huésped y la redirección a Stripe Checkout. Actualmente el huésped puede *buscar* disponibilidad pero no *reservar* desde la interfaz.
- Página pública de aterrizaje: hoy la ruta `/` redirige directamente a `/login` (decisión temporal explícita en `nuxt.config.ts`) — antes de mostrar esto a los otros 5 propietarios como demo navegable, hace falta al menos una home mínima que no fuerce el login a un visitante cualquiera.

**Integraciones:**
- Stripe Connect (multi-propietario) — diferido, no es MVP.
- iCal sync — diferido, no es MVP.

**Legal/operativo:**
- Texto final de Política de Privacidad y Cookies (análisis técnico ya cerrado).
- Confirmar el mecanismo de consentimiento de marketing como opt-in separado en el formulario de huésped (diseñado, pendiente de construir en el formulario de reserva que todavía no existe en frontend).

---

## 7. Riesgos antes de producción

- **Sin ficha pública de apartamento ni flujo de reserva de huésped en frontend:** el backend soporta todo el ciclo (búsqueda → reserva → checkout → confirmación) pero la interfaz de huésped se detiene en la tabla de resultados de disponibilidad. Es el mayor hueco entre "lo que el backend puede hacer" y "lo que un propietario podría enseñar a un huésped real hoy".
- **API sin versionar** con clientes (frontend propio, y potencialmente integraciones futuras) ya consumiéndola en la raíz — cambiarla más adelante implicará coordinar a todos los consumidores a la vez, sin posibilidad de convivencia de versiones.
- **Extensión `vector` habilitada pero sin ningún modelo/columna que la use todavía** — no es un riesgo en sí, pero conviene no olvidar que RAG es la única pieza de la arquitectura pensada "para más adelante" que ya tiene una dependencia de infraestructura viva y sin uso.
- **Ausencia de ejecución de tests como parte de esta auditoría:** hay 216+6 tests que existen sobre el papel; no se ha confirmado en esta revisión que la suite completa pase en el estado actual del repo. Antes de producción conviene una corrida completa (y, si no está ya, integrarla en CI).
- **Fricción de `.git/index.lock` sin causa raíz resuelta:** riesgo operativo bajo pero real de perder tiempo o de commits a medias si se solapa con el flujo de trabajo con Claude Code en momentos críticos previos a un despliegue.
- **Bloque de dependencias `@tiptap/*` sin uso:** no es un riesgo de seguridad inmediato, pero es superficie extra que actualizar/auditar sin beneficio.

---

## 8. Orden recomendado de próximos sprints

1. **BlockedDates — backend (schemas + servicio + API CRUD).** Es el bloqueador directo de la siguiente pantalla de frontend y es un slice pequeño y ya patronizado (mismo esquema que RateRule).
2. **BlockedDates — frontend (gestión de bloqueos).** Sigue el mismo patrón ya validado en `panel/apartments.vue`.
3. **RateRules — frontend (gestión de temporadas/precios).** Backend ya existe; es puramente construir la pantalla, reutilizando componentes de Nuxt UI ya usados en apartments.
4. **Flujo de reserva de huésped en frontend** (ficha de apartamento pública → formulario → checkout Stripe): es el hueco más importante de cara a un demo navegable real para los otros 5 propietarios, y depende de tener ya BlockedDates y RateRules visibles para poder enseñar el ciclo completo con datos reales.
5. **Home pública mínima** (quitar el redirect forzado `/` → `/login`) — pequeño, pero necesario antes de enseñar el demo a alguien externo.
6. **Limpieza de deuda identificada en esta auditoría** (Tiptap, `docs/architecture.md`, decisión sobre `/api/v1`) — bajo coste, se puede intercalar en cualquier hueco entre sprints funcionales sin bloquear nada.
7. **Calendario visual de reservas/bloqueos** — mejora de UX sobre lo anterior, no bloquea el demo pero lo hace más presentable.
8. Todo lo demás (Stripe Connect, iCal, RAG) permanece en CAN WAIT, sin fecha asignada, hasta después de Hito 1.

---

*Confirmación: esta auditoría ha sido exclusivamente de lectura. No se ha modificado, creado ni eliminado ningún fichero del proyecto, ni se ha ejecutado la aplicación o los tests.*
