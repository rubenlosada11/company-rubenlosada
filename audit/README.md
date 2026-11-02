# Evidencias de la auditoría de rendimiento

Informes de Lighthouse de la auditoría de rendimiento de `uis/website` y `uis/backoffice`. Diagnóstico en
[`../AUDIT.md`](../AUDIT.md); resultados y comparativa en [`../REPORT.md`](../REPORT.md).

```text
audit/
├── before/                 # línea base (código de main @ 714441a)
│   ├── runs.json           # las 5 ejecuciones de cada página y dispositivo (puntuaciones y métricas)
│   ├── corporate/          # uis/website  → home-desktop · home-mobile
│   └── backoffice/         # uis/backoffice → dashboard-desktop · dashboard-mobile · gestor-incidencias-desktop
├── after/                  # misma estructura, tras las correcciones
└── scripts/                # scripts de medición (no forman parte de ninguna app)
```

Por cada página y dispositivo hay tres ficheros: el informe **HTML** y el **JSON** originales de Lighthouse de la
ejecución mediana, y un **PNG** con la captura de la cabecera de ese mismo informe HTML (puntuaciones y métricas).
Las otras cuatro ejecuciones no se versionan (≈ 1 MB cada una): sus valores están en `runs.json`.

## Cómo se mide

Siempre con los builds de producción (`npm run build` + `npm run start`), nunca con `next dev`.

| Pieza | Valor |
| --- | --- |
| Lighthouse | 12.8.2 (API de Node), configuración por defecto (móvil) y `desktop-config` (escritorio) |
| Navegador | Google Chrome 156 en modo `--headless=new`, perfil nuevo en cada ejecución |
| Throttling | Simulado (Lantern). Móvil: 412×823 a DPR 1,75, RTT 150 ms, 1,6 Mbps, CPU ×4. Escritorio: 1350×940, RTT 40 ms, 10 Mbps, CPU ×1 |
| Repeticiones | 5 por página y dispositivo; se versiona la ejecución mediana según el algoritmo de Lighthouse (`computeMedianRun`) y las tablas usan la mediana de cada métrica |
| Website | `http://localhost:3001/` |
| Backoffice | `http://localhost:3002/` y `http://localhost:3002/gestor-incidencias`, con sesión iniciada |
| API | `services/api` en `:8000` con **copias** de las bases (`SUPPLIERS_DB_PATH`, `AUTH_DB_PATH`, `INCIDENTS_DB_PATH`, `DATABASE_URL` a un SQLite copiado) y un usuario propio de la auditoría: no se tocan los datos reales ni Supabase |

**Sesión del backoffice.** El token vive en `localStorage` (`trackflow.backoffice.token`). Antes de cada ejecución,
`run-lh.mjs` abre `/icon.png` del backoffice (no carga la app), guarda el token, vacía la caché HTTP y lanza
Lighthouse con `disableStorageReset` para que no borre la sesión. Si una ejecución acaba en `/login`, el script se
detiene.

## Repetir la medición

Las herramientas se instalan fuera del repo (no hay `package.json` en la raíz). En PowerShell, un comando por línea:

```powershell
mkdir $env:TEMP\lh-audit
cd $env:TEMP\lh-audit
npm init -y
npm install lighthouse@12.8.2 playwright-core@1.64.1
Copy-Item <repo>\audit\scripts\*.mjs .
```

Con website (`:3001`), backoffice (`:3002`) y la API (`:8000`) arrancados en producción y un token del usuario de
auditoría guardado en `token.txt`:

```powershell
node run-lh.mjs after <repo>\audit $env:TEMP\lh-audit\runs token.txt 5
node shot-reports.mjs <repo>\audit\after
node summarize.mjs <repo>\audit compare
```

`run-lh.mjs` usa la ruta de Chrome de Windows (`C:\Program Files\Google\Chrome\Application\chrome.exe`); cámbiala si
hace falta. `diag.mjs <informe.json>` resume los diagnósticos (elemento LCP, fases, CLS, JS sin usar, fallos de
accesibilidad y SEO).
