import { Suspense } from "react";
import { CandidatesList } from "@/components/CandidatesList";
import { LoadingBlock } from "@/components/StateBanner";

export default function HomePage() {
  return (
    <div className="mx-auto w-[min(1120px,92vw)] py-10 space-y-6">
      <div>
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.17em] text-blue-800">
          People &amp; Talent · TrackFlow
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Pipeline de candidaturas
        </h1>
        <p className="mt-3 max-w-2xl text-slate-600">
          Consulta, filtra y busca todas las candidaturas recibidas por TrackFlow. Abre una candidatura
          para gestionar su estado, etapa y notas.
        </p>
      </div>

      <Suspense fallback={<LoadingBlock label="Cargando candidaturas…" />}>
        <CandidatesList />
      </Suspense>
    </div>
  );
}
