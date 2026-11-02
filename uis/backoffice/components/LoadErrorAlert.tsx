interface LoadErrorAlertProps {
  /** Qué no se ha podido cargar («No se pudieron cargar las incidencias.»). */
  title: string;
  /** Motivo, en español (normalmente el mensaje traducido del error de la API). */
  message: string;
  /** Vuelve a pedir los datos. */
  onRetry: () => void;
  /** Aclaraciones opcionales bajo el motivo (p. ej. qué sigue disponible). */
  children?: React.ReactNode;
}

/** Aviso de los listados del backoffice cuando la API falla al cargar sus datos, con el botón «Reintentar». */
export function LoadErrorAlert({ title, message, onRetry, children }: LoadErrorAlertProps) {
  return (
    <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
      <p className="font-bold">{title}</p>
      <p className="mt-1">{message}</p>
      {children}
      <button
        type="button"
        onClick={onRetry}
        className="mt-3 min-h-11 rounded-full border border-red-300 bg-white px-5 text-sm font-bold text-red-800 transition hover:bg-red-100"
      >
        Reintentar
      </button>
    </div>
  );
}
