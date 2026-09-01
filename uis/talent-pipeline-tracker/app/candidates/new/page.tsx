"use client";

import { useRouter } from "next/navigation";
import { CandidateForm } from "@/components/CandidateForm";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { recordsService } from "@/services/records";
import { toCreatePayload, type CandidateFormValues } from "@/lib/validation";

export default function NewCandidatePage() {
  const router = useRouter();
  const createAction = useAsyncAction((values: CandidateFormValues) =>
    recordsService.create(toCreatePayload(values))
  );

  async function handleSubmit(values: CandidateFormValues) {
    const result = await createAction.run(values);
    if (result.ok) router.push(`/candidates/${result.data.id}`);
  }

  return (
    <div className="mx-auto w-[min(760px,92vw)] py-10 space-y-6">
      <div>
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.17em] text-blue-800">
          People &amp; Talent · TrackFlow
        </p>
        <h1 className="font-heading text-3xl leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Nueva candidatura
        </h1>
        <p className="mt-3 text-slate-600">
          Registra una candidatura para añadirla al pipeline. El estado y la etapa se inician
          automáticamente como &quot;Recibida&quot; / &quot;Pendiente&quot;.
        </p>
      </div>

      <CandidateForm
        mode="create"
        submitLabel="Crear candidatura"
        pendingLabel="Creando…"
        isSubmitting={createAction.isLoading}
        submitError={createAction.error}
        onSubmit={handleSubmit}
        onCancel={() => router.push("/")}
      />
    </div>
  );
}
