"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { CandidateForm } from "@/components/CandidateForm";
import { ErrorBanner, LoadingBlock } from "@/components/StateBanner";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useCandidate } from "@/hooks/useCandidate";
import { recordsService } from "@/services/records";
import { toCreatePayload, type CandidateFormValues } from "@/lib/validation";
import type { Candidate } from "@/types/api";

function candidateToFormValues(candidate: Candidate): CandidateFormValues {
  return {
    full_name: candidate.full_name,
    email: candidate.email,
    phone: candidate.phone,
    position: candidate.position,
    experience_years: String(candidate.experience_years),
    linkedin_url: candidate.linkedin_url ?? "",
    cv_url: candidate.cv_url ?? "",
  };
}

export default function EditCandidatePage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [retryKey, setRetryKey] = useState(0);

  return <EditCandidateContent key={`${id}-${retryKey}`} id={id} onRetry={() => setRetryKey((k) => k + 1)} />;
}

function EditCandidateContent({ id, onRetry }: { id: string; onRetry: () => void }) {
  const router = useRouter();
  const { state } = useCandidate(id);

  const replaceAction = useAsyncAction((values: CandidateFormValues) =>
    recordsService.replace(id, toCreatePayload(values))
  );

  async function handleSubmit(values: CandidateFormValues) {
    const result = await replaceAction.run(values);
    if (result.ok) router.push(`/candidates/${id}`);
  }

  if (state.status === "loading") {
    return (
      <div className="mx-auto w-[min(760px,92vw)] py-10">
        <LoadingBlock label="Cargando candidatura…" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="mx-auto w-[min(760px,92vw)] py-10">
        <ErrorBanner message={state.message} onRetry={onRetry} />
      </div>
    );
  }

  return (
    <div className="mx-auto w-[min(760px,92vw)] py-10 space-y-6">
      <Link href={`/candidates/${id}`} className="text-sm font-semibold text-blue-700 hover:text-blue-800">
        ← Volver a la candidatura
      </Link>

      <div>
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.17em] text-blue-800">
          People &amp; Talent · TrackFlow
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Editar candidatura
        </h1>
        <p className="mt-3 text-slate-600">
          Actualiza los datos de {state.data.full_name}. El estado y la etapa se gestionan desde el
          detalle de la candidatura.
        </p>
      </div>

      <CandidateForm
        mode="edit"
        initialValues={candidateToFormValues(state.data)}
        submitLabel="Guardar cambios"
        pendingLabel="Guardando…"
        isSubmitting={replaceAction.isLoading}
        submitError={replaceAction.error}
        onSubmit={handleSubmit}
        onCancel={() => router.push(`/candidates/${id}`)}
      />
    </div>
  );
}
