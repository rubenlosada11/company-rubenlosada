# TrackFlow People — Talent Pipeline Tracker

Herramienta interna de People & Talent de TrackFlow para gestionar el pipeline de candidaturas: consultar,
filtrar, buscar, ver el detalle, cambiar estado/etapa y gestionar notas de cada candidatura, además de crear y
editar candidaturas.

Next.js (App Router) + React + TypeScript + Tailwind CSS. Sin librerías de gestión de estado externas — solo
hooks de React (`useState`/`useEffect`) y estado local.

## Demo pública

- URL: https://talent-pipeline-tracker.rubenlosada.com/

## API

Consume directamente, desde el cliente, la API pública de [Talent Tracker](https://playground.4geeks.com/tracker/api/v1/docs):

| Acción | Endpoint |
| --- | --- |
| Listar / filtrar / buscar candidaturas | `GET /records` (`status`, `stage`, `search`, `page`, `limit`) |
| Detalle de candidatura | `GET /records/:id` |
| Crear candidatura | `POST /records` |
| Editar candidatura (reemplazo completo) | `PUT /records/:id` |
| Cambiar estado o etapa | `PATCH /records/:id` |
| Eliminar candidatura | `DELETE /records/:id` |
| Notas: listar / añadir / eliminar | `GET`/`POST /records/:id/notes`, `DELETE /records/:id/notes/:note_id` |

Valores de dominio de la API (traducidos en la UI a la nomenclatura de People & Talent, ver
[`lib/domain.ts`](./lib/domain.ts)):

- **Estado** (`status`): `received` (Recibida), `in_progress` (En proceso), `selected` (Seleccionada),
  `discarded` (Descartada).
- **Etapa** (`stage`): `pending` (Pendiente), `review` (En revisión), `personal_interview` (Entrevista
  personal), `technical_interview` (Entrevista técnica), `offer_presented` (Oferta presentada).

## Estructura

```text
talent-pipeline-tracker/
├── app/
│   ├── page.tsx                    # listado, filtros y búsqueda
│   └── candidates/
│       ├── new/page.tsx            # crear candidatura
│       └── [id]/
│           ├── page.tsx            # detalle: estado, etapa, notas
│           └── edit/page.tsx       # editar candidatura
├── components/                     # UI (formulario, badges, filtros, notas, estados de carga/error)
├── hooks/                          # useCandidates, useCandidate, useNotes, useAsyncAction
├── lib/                            # http.ts (cliente fetch + parseo de errores), domain.ts, validation.ts
├── services/records.ts             # capa de acceso a la API (todos los endpoints)
└── types/api.ts                    # tipos TypeScript del esquema real de la API
```

## Ejecución local

```bash
cd uis/talent-pipeline-tracker
npm install
cp .env.example .env.local   # ya incluido con la URL pública de la API
npm run dev
```

Abre <http://localhost:3000>.

## Validación

```bash
npm run lint
npm run build
```

Probado manualmente en navegador (listado, filtros por query params, búsqueda en cliente, detalle, cambio de
estado/etapa, notas, creación y edición) contra la API real.
