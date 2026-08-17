# TrackFlow — Utilidades de procesamiento de datos (demo)

Interfaz estática de prueba manual para las utilidades TypeScript de [`packages/shared`](../../packages/shared):
filtrado, ordenamiento, búsqueda lineal, búsqueda binaria, agregaciones/reportes y validaciones de negocio sobre
envíos, transportistas, devoluciones y clientes de TrackFlow.

No es una aplicación de producción — es un panel de pruebas manuales, sin build tooling ni framework, que consume
directamente el `dist/` compilado de `packages/shared`.

## Demo pública

- URL: https://scriptsautotrackflow.rubenlosada.com/

## Estructura

```text
uis/script-automatizacion/
├── index.html   # secciones: datos de ejemplo, filtrado, ordenamiento, búsquedas, agregaciones, validaciones
├── app.ts       # lógica de la UI, importa las utilidades desde packages/shared/dist
├── app.js       # compilado (committeado para poder servir sin paso de build)
└── tsconfig.json
```

## Ejecución local

1. Compila `packages/shared` si has tocado sus fuentes (`cd packages/shared && npm run build`).
2. Compila esta UI si has tocado `app.ts`: `npx tsc -p tsconfig.json` desde esta carpeta.
3. Sirve el repo como estático desde la raíz (necesita ver `packages/shared/dist/`):

```bash
npx http-server . -p 3000
```

4. Abre `http://localhost:3000/uis/script-automatizacion/`.

## Notas de diseño

- Usa Tailwind vía CDN (`<script src="https://cdn.tailwindcss.com">`), ya que no hay CLI de Tailwind disponible sin
  red en este entorno y la landing (`uis/landing`) purga sus clases contra su propio contenido, no contra esta página.
- Los datos de ejemplo incluyen registros inválidos a propósito (`ship-invalid`, `ret-invalid`, `cli-invalid-dates`)
  para poder probar la sección de Validaciones sin tener que rellenar el formulario manual.
