import { useCallback, useEffect, useEffectEvent, useState } from "react";

interface Settled<T> {
  /** Petición (clave + recarga) a la que corresponde el resultado: si no coincide con la actual, se está cargando. */
  key: string;
  data: T | null;
  error: string | null;
}

export interface ApiRequestState<T> {
  /**
   * Últimos datos recibidos. Se conservan mientras se carga la petición siguiente (la vista los atenúa en lugar de
   * vaciarse). `null` antes de la primera respuesta y tras un error, salvo con `keepDataOnError`.
   */
  data: T | null;
  /** Mensaje (en español, listo para mostrar) del último error, o `null`. */
  error: string | null;
  /** La petición actual (clave + recarga) todavía no ha terminado. */
  loading: boolean;
  /** Ya ha terminado alguna petición, con datos o con error (`false` solo en la primera carga). */
  settled: boolean;
  /** Repite la petición con la misma clave. */
  reload: () => void;
  /** Cambia los datos ya recibidos sin volver a pedirlos (p. ej. una fila tras un cambio optimista). */
  update: (change: (data: T) => T) => void;
}

interface ApiRequestOptions<T> {
  /** Si la petición falla, se siguen mostrando los últimos datos (p. ej. el stock ya pintado al pulsar «Actualizar»). */
  keepDataOnError?: boolean;
  /** Se llama con cada respuesta correcta de la petición actual. */
  onSuccess?: (data: T) => void;
}

/**
 * Petición a la API ligada a una clave (normalmente, los filtros): se repite cuando cambia la clave o se llama a
 * `reload`, y la anterior se cancela (`AbortController`) para que una respuesta vieja nunca pise a la nueva.
 *
 * Contrato común de los listados del backoffice (gestor de incidencias, proveedores, inventario): antes estaba
 * copiado en cada componente.
 */
export function useApiRequest<T>(
  key: string,
  request: (signal: AbortSignal) => Promise<T>,
  errorMessage: (error: unknown) => string,
  { keepDataOnError = false, onSuccess }: ApiRequestOptions<T> = {}
): ApiRequestState<T> {
  const [reloadToken, setReloadToken] = useState(0);
  const [result, setResult] = useState<Settled<T> | null>(null);
  const requestKey = `${key}#${reloadToken}`;

  // La petición la describe `key`: las funciones pueden ser nuevas en cada render sin repetirla.
  const run = useEffectEvent(request);
  const describeError = useEffectEvent(errorMessage);
  const succeeded = useEffectEvent((data: T) => onSuccess?.(data));

  useEffect(() => {
    const controller = new AbortController();
    run(controller.signal)
      .then((data) => {
        succeeded(data);
        setResult({ key: requestKey, data, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = describeError(error);
        setResult((current) => ({
          key: requestKey,
          data: keepDataOnError ? (current?.data ?? null) : null,
          error: message,
        }));
      });
    return () => controller.abort();
  }, [requestKey, keepDataOnError]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);
  const update = useCallback((change: (data: T) => T) => {
    setResult((current) => (current && current.data !== null ? { ...current, data: change(current.data) } : current));
  }, []);

  return {
    data: result?.data ?? null,
    error: result?.error ?? null,
    loading: result?.key !== requestKey,
    settled: result !== null,
    reload,
    update,
  };
}
