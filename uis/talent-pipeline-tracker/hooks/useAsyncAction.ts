import { useState } from "react";
import { ApiError } from "@/lib/http";

type AsyncStatus = "idle" | "loading" | "success" | "error";

const FALLBACK_MESSAGE = "Ha ocurrido un error inesperado. Inténtalo de nuevo.";

/** Estandariza loading/success/error para una acción de mutación (POST/PUT/PATCH/DELETE). */
export function useAsyncAction<Args extends unknown[], R>(fn: (...args: Args) => Promise<R>) {
  const [status, setStatus] = useState<AsyncStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  async function run(...args: Args): Promise<{ ok: true; data: R } | { ok: false; error: string }> {
    setStatus("loading");
    setError(null);
    try {
      const data = await fn(...args);
      setStatus("success");
      return { ok: true, data };
    } catch (err) {
      const message = err instanceof ApiError ? err.message : FALLBACK_MESSAGE;
      setError(message);
      setStatus("error");
      return { ok: false, error: message };
    }
  }

  function reset() {
    setStatus("idle");
    setError(null);
  }

  return { status, error, isLoading: status === "loading", isError: status === "error", run, reset };
}
