export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-3 rounded-2xl border border-rose-300 bg-rose-50 p-5 text-rose-800 sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="text-sm font-semibold">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="self-start rounded-full border border-rose-400 bg-white px-3 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-100 sm:self-auto"
        >
          Reintentar
        </button>
      )}
    </div>
  );
}

export function InlineError({ message }: { message: string }) {
  return (
    <p role="alert" className="text-sm font-semibold text-rose-700">
      {message}
    </p>
  );
}

export function InlineSuccess({ message }: { message: string }) {
  return (
    <p role="status" className="text-sm font-semibold text-emerald-700">
      {message}
    </p>
  );
}

export function LoadingBlock({ label = "Cargando…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white/80 p-6 text-slate-600">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-700"
        aria-hidden="true"
      />
      <span className="text-sm font-semibold">{label}</span>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-8 text-center">
      <p className="font-heading text-lg font-bold text-slate-800">{title}</p>
      {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
    </div>
  );
}
