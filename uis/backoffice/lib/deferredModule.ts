/**
 * Carga diferida de un módulo (normalmente un componente) con `import()`, precargable y legible con `use()` de React.
 *
 * Por qué no `next/dynamic` ni `React.lazy` (medido en `CACHING_REPORT.md`): los dos suspenden al menos una vez aunque
 * el chunk ya esté descargado, y React 19 retrasa hasta 300 ms la sustitución de un fallback de `Suspense` por su
 * contenido. El formulario tardaba así ~300 ms más en aparecer que sin carga diferida. Con esta función:
 *
 * - `import()` separa el módulo en su propio chunk, igual que `next/dynamic` y `React.lazy`;
 * - la promesa se guarda y se marca con `status`/`value` al resolverse (el formato que entiende `use()`), así que si el
 *   módulo ya se ha precargado `use()` lo devuelve sin suspender y no aparece ningún fallback;
 * - si la descarga falla, se olvida la promesa: el siguiente intento (p. ej. «Reintentar» del límite de error) la
 *   vuelve a pedir.
 *
 * Uso: `const loadForm = deferredModule(() => import("./Form").then((m) => m.Form));` y, dentro de un `Suspense`,
 * `const Form = use(loadForm());`. Para precargar: `loadForm().catch(() => undefined)`.
 */

type TrackedPromise<T> = Promise<T> & {
  status?: "pending" | "fulfilled" | "rejected";
  value?: T;
  reason?: unknown;
};

export function deferredModule<T>(load: () => Promise<T>): () => Promise<T> {
  let current: TrackedPromise<T> | null = null;

  return function get(): Promise<T> {
    if (current === null) {
      const promise: TrackedPromise<T> = load();
      promise.status = "pending";
      promise.then(
        (value) => {
          promise.status = "fulfilled";
          promise.value = value;
        },
        (reason: unknown) => {
          promise.status = "rejected";
          promise.reason = reason;
          if (current === promise) current = null;
        }
      );
      current = promise;
    }
    return current;
  };
}
