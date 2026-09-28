"use client";

import { useId, useState } from "react";
import { tamanoFichero } from "@/lib/formato";

interface SelectorCsvProps {
  archivo: File | null;
  deshabilitado: boolean;
  onSeleccionar: (archivo: File | null) => void;
}

export function SelectorCsv({ archivo, deshabilitado, onSeleccionar }: SelectorCsvProps) {
  const idInput = useId();
  const [arrastrando, setArrastrando] = useState(false);

  function soltar(evento: React.DragEvent<HTMLLabelElement>) {
    evento.preventDefault();
    setArrastrando(false);
    if (deshabilitado) return;
    onSeleccionar(evento.dataTransfer.files[0] ?? null);
  }

  return (
    <label
      htmlFor={idInput}
      onDragOver={(evento) => {
        evento.preventDefault();
        if (!deshabilitado) setArrastrando(true);
      }}
      onDragLeave={() => setArrastrando(false)}
      onDrop={soltar}
      className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${
        arrastrando ? "border-blue-700 bg-blue-50" : "border-slate-300 bg-white hover:border-blue-400 hover:bg-slate-50"
      } ${deshabilitado ? "cursor-not-allowed opacity-60" : ""}`}
    >
      <svg aria-hidden="true" viewBox="0 0 24 24" className="h-9 w-9 text-blue-700" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
      </svg>
      {archivo ? (
        <>
          <span className="font-semibold text-slate-900">{archivo.name}</span>
          <span className="text-sm text-slate-500">{tamanoFichero(archivo.size)} · Haz clic o arrastra otro fichero para cambiarlo</span>
        </>
      ) : (
        <>
          <span className="font-semibold text-slate-900">Arrastra aquí el CSV de incidencias</span>
          <span className="text-sm text-slate-500">o haz clic para seleccionarlo · UTF-8, separado por comas</span>
        </>
      )}
      <input
        id={idInput}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        disabled={deshabilitado}
        onChange={(evento) => {
          onSeleccionar(evento.target.files?.[0] ?? null);
          evento.target.value = ""; // permite volver a elegir el mismo fichero
        }}
      />
    </label>
  );
}
