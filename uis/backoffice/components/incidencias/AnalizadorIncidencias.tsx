"use client";

import { useState } from "react";
import { ResultadosAnalisis } from "@/components/incidencias/ResultadosAnalisis";
import { SelectorCsv } from "@/components/incidencias/SelectorCsv";
import { ApiError, apiErrorMessage } from "@/lib/http";
import { analizarCsv, descargarResultados } from "@/lib/incidencias";
import type { ResultadoAnalisis } from "@/types/incidencias";

const SIN_ANALISIS = "Todavía no hay ningún análisis que descargar. Analiza primero un fichero CSV.";

/** Los 4xx del analizador (sin fichero, formato, tamaño, CSV no procesable) ya llegan redactados en español. */
function mensaje(error: unknown, accion: string): string {
  // El 404 de la descarga nombra el endpoint de la API: se sustituye por un texto para el usuario.
  if (error instanceof ApiError && error.status === 404) return SIN_ANALISIS;
  return apiErrorMessage(error, accion);
}

function Spinner() {
  return <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />;
}

function Aviso({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
      <span aria-hidden="true" className="font-bold">✕</span>
      <span>{children}</span>
    </p>
  );
}

export function AnalizadorIncidencias() {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultado, setResultado] = useState<ResultadoAnalisis | null>(null);
  const [descargando, setDescargando] = useState(false);
  const [errorDescarga, setErrorDescarga] = useState<string | null>(null);

  function seleccionar(nuevo: File | null) {
    setArchivo(nuevo);
    setError(nuevo && !nuevo.name.toLowerCase().endsWith(".csv") ? "El fichero debe tener extensión .csv." : null);
  }

  async function analizar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!archivo) {
      setError("Selecciona un fichero CSV antes de analizar.");
      return;
    }
    if (!archivo.name.toLowerCase().endsWith(".csv")) {
      setError("El fichero debe tener extensión .csv.");
      return;
    }
    setCargando(true);
    setError(null);
    setErrorDescarga(null);
    try {
      setResultado(await analizarCsv(archivo));
    } catch (e) {
      setResultado(null);
      setError(mensaje(e, "analizar el fichero"));
    } finally {
      setCargando(false);
    }
  }

  async function descargar() {
    setDescargando(true);
    setErrorDescarga(null);
    try {
      await descargarResultados();
    } catch (e) {
      setErrorDescarga(mensaje(e, "descargar los resultados"));
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="space-y-10">
      <form onSubmit={analizar} className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-5 sm:p-6">
        <SelectorCsv archivo={archivo} deshabilitado={cargando} onSeleccionar={seleccionar} />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={cargando}
            className="inline-flex items-center gap-2 rounded-full bg-blue-700 px-5 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-blue-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait disabled:opacity-70"
          >
            {cargando ? <Spinner /> : null}
            {cargando ? "Analizando…" : "Analizar CSV"}
          </button>
          <p aria-live="polite" className="text-sm text-slate-600">
            {cargando ? "Validando registros y calculando métricas…" : "El fichero se procesa en la API interna de TrackFlow."}
          </p>
        </div>
        {error ? <Aviso>{error}</Aviso> : null}
      </form>

      {resultado ? (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-blue-200 bg-blue-50 px-5 py-4">
            <p className="text-sm text-blue-950">
              <strong>Análisis completado.</strong> Puedes descargar las métricas en CSV (una fila por métrica).
            </p>
            <button
              type="button"
              onClick={descargar}
              disabled={descargando}
              className="inline-flex items-center gap-2 rounded-full border border-blue-700 bg-white px-5 py-2 text-sm font-bold text-blue-800 transition hover:bg-blue-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 disabled:cursor-wait disabled:opacity-70"
            >
              {descargando ? <Spinner /> : null}
              {descargando ? "Descargando…" : "Descargar resultados CSV"}
            </button>
          </div>
          {errorDescarga ? <Aviso>{errorDescarga}</Aviso> : null}
          <ResultadosAnalisis resultado={resultado} />
        </div>
      ) : null}
    </div>
  );
}
