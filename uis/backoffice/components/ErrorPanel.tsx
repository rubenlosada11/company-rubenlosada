const buttonBase =
  "rounded-full px-4 py-2 text-sm font-bold transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700";

interface ErrorPanelProps {
  title: string;
  description: string;
  /** Vuelve a intentar el render que falló (`reset` de los límites de error de Next.js). Sin él, solo hay vuelta al inicio. */
  onRetry?: () => void;
}

/** Aviso de las pantallas de error y de «página no encontrada»: qué ha pasado y cómo salir de ahí. */
export function ErrorPanel({ title, description, onRetry }: ErrorPanelProps) {
  return (
    <div className="mx-auto w-full max-w-md rounded-2xl border border-amber-200 bg-white p-6 text-center shadow-sm">
      <h1 className="font-heading text-lg text-slate-900">{title}</h1>
      <p className="mt-2 text-sm text-slate-600">{description}</p>
      <div className="mt-5 flex flex-wrap justify-center gap-2">
        {onRetry ? (
          <button type="button" onClick={onRetry} className={`${buttonBase} bg-blue-700 text-white hover:bg-blue-800`}>
            Reintentar
          </button>
        ) : null}
        {/* Enlace normal (y no <Link>): tras un fallo de render conviene recargar la aplicación entera. */}
        {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
        <a href="/" className={`${buttonBase} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`}>
          Volver al inicio
        </a>
      </div>
    </div>
  );
}
