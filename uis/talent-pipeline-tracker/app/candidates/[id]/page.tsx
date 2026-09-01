"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { NotesPanel } from "@/components/NotesPanel";
import { StageBadge } from "@/components/StageBadge";
import { StatusBadge } from "@/components/StatusBadge";
import { ErrorBanner, InlineError, InlineSuccess, LoadingBlock } from "@/components/StateBanner";
import { formatDateTime, formatExperience, STAGE_LABELS, STAGE_ORDER, STATUS_LABELS, STATUS_ORDER } from "@/lib/domain";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useCandidate } from "@/hooks/useCandidate";
import { recordsService } from "@/services/records";
import type { Candidate, CandidateStage, CandidateStatus } from "@/types/api";

const selectClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto";

export default function CandidateDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [retryKey, setRetryKey] = useState(0);

  return (
    <CandidateDetailContent key={`${id}-${retryKey}`} id={id} onRetry={() => setRetryKey((k) => k + 1)} />
  );
}

function CandidateDetailContent({ id, onRetry }: { id: string; onRetry: () => void }) {
  const { state, setCandidate } = useCandidate(id);

  if (state.status === "loading") {
    return (
      <div className="mx-auto w-[min(1000px,92vw)] py-10">
        <LoadingBlock label="Cargando candidatura…" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="mx-auto w-[min(1000px,92vw)] py-10">
        <ErrorBanner message={state.message} onRetry={onRetry} />
      </div>
    );
  }

  return <CandidateDetailView candidate={state.data} setCandidate={setCandidate} />;
}

function CandidateDetailView({
  candidate,
  setCandidate,
}: {
  candidate: Candidate;
  setCandidate: (data: Candidate) => void;
}) {
  const statusAction = useAsyncAction((status: CandidateStatus) =>
    recordsService.patch(candidate.id, { status })
  );
  const stageAction = useAsyncAction((stage: CandidateStage) =>
    recordsService.patch(candidate.id, { stage })
  );

  const [statusFeedback, setStatusFeedback] = useState(false);
  const [stageFeedback, setStageFeedback] = useState(false);

  useEffect(() => {
    if (!statusFeedback) return;
    const timeout = setTimeout(() => setStatusFeedback(false), 2500);
    return () => clearTimeout(timeout);
  }, [statusFeedback]);

  useEffect(() => {
    if (!stageFeedback) return;
    const timeout = setTimeout(() => setStageFeedback(false), 2500);
    return () => clearTimeout(timeout);
  }, [stageFeedback]);

  async function handleStatusChange(status: CandidateStatus) {
    const result = await statusAction.run(status);
    if (result.ok) {
      setCandidate(result.data);
      setStatusFeedback(true);
    }
  }

  async function handleStageChange(stage: CandidateStage) {
    const result = await stageAction.run(stage);
    if (result.ok) {
      setCandidate(result.data);
      setStageFeedback(true);
    }
  }

  return (
    <div className="mx-auto w-[min(1000px,92vw)] py-10 space-y-6">
      <Link href="/" className="text-sm font-semibold text-blue-700 hover:text-blue-800">
        ← Volver al pipeline
      </Link>

      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-900/5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-heading text-3xl font-bold text-slate-900">{candidate.full_name}</h1>
            <p className="mt-1 text-slate-600">{candidate.position}</p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href={`/candidates/${candidate.id}/edit`}
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
            >
              Editar candidatura
            </Link>
          </div>
        </div>

        <dl className="mt-6 grid gap-x-6 gap-y-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-bold uppercase tracking-wide text-slate-500">Email</dt>
            <dd className="mt-1 text-sm text-slate-800">
              <a className="text-blue-700 hover:underline" href={`mailto:${candidate.email}`}>
                {candidate.email}
              </a>
            </dd>
          </div>
          <div>
            <dt className="text-xs font-bold uppercase tracking-wide text-slate-500">Teléfono</dt>
            <dd className="mt-1 text-sm text-slate-800">
              <a className="text-blue-700 hover:underline" href={`tel:${candidate.phone}`}>
                {candidate.phone}
              </a>
            </dd>
          </div>
          <div>
            <dt className="text-xs font-bold uppercase tracking-wide text-slate-500">LinkedIn</dt>
            <dd className="mt-1 text-sm text-slate-800">
              {candidate.linkedin_url ? (
                <a
                  className="text-blue-700 hover:underline"
                  href={candidate.linkedin_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Ver perfil
                </a>
              ) : (
                <span className="text-slate-400">No indicado</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-bold uppercase tracking-wide text-slate-500">CV</dt>
            <dd className="mt-1 text-sm text-slate-800">
              {candidate.cv_url ? (
                <a
                  className="text-blue-700 hover:underline"
                  href={candidate.cv_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Ver CV
                </a>
              ) : (
                <span className="text-slate-400">No indicado</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-bold uppercase tracking-wide text-slate-500">Experiencia</dt>
            <dd className="mt-1 text-sm text-slate-800">{formatExperience(candidate.experience_years)}</dd>
          </div>
          <div>
            <dt className="text-xs font-bold uppercase tracking-wide text-slate-500">Fecha de aplicación</dt>
            <dd className="mt-1 text-sm text-slate-800">{formatDateTime(candidate.applied_at)}</dd>
          </div>
          <div>
            <dt className="text-xs font-bold uppercase tracking-wide text-slate-500">Última actualización</dt>
            <dd className="mt-1 text-sm text-slate-800">{formatDateTime(candidate.updated_at)}</dd>
          </div>
        </dl>
      </div>

      <div className="grid gap-6 sm:grid-cols-2">
        <section className="space-y-3 rounded-3xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-900/5">
          <div className="flex items-center justify-between">
            <h2 className="font-heading text-lg font-bold text-slate-900">Estado</h2>
            <StatusBadge status={candidate.status} />
          </div>
          <label htmlFor="status-select" className="sr-only">
            Cambiar estado
          </label>
          <select
            id="status-select"
            value={candidate.status}
            disabled={statusAction.isLoading}
            onChange={(e) => handleStatusChange(e.target.value as CandidateStatus)}
            className={selectClasses}
          >
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
          {statusAction.isLoading && <p className="text-sm text-slate-500">Actualizando estado…</p>}
          {statusAction.error && <InlineError message={statusAction.error} />}
          {statusFeedback && !statusAction.error && <InlineSuccess message="Estado actualizado." />}
        </section>

        <section className="space-y-3 rounded-3xl border border-slate-200 bg-white p-6 shadow-lg shadow-slate-900/5">
          <div className="flex items-center justify-between">
            <h2 className="font-heading text-lg font-bold text-slate-900">Etapa</h2>
            <StageBadge stage={candidate.stage} />
          </div>
          <label htmlFor="stage-select" className="sr-only">
            Cambiar etapa
          </label>
          <select
            id="stage-select"
            value={candidate.stage}
            disabled={stageAction.isLoading}
            onChange={(e) => handleStageChange(e.target.value as CandidateStage)}
            className={selectClasses}
          >
            {STAGE_ORDER.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABELS[s]}
              </option>
            ))}
          </select>
          {stageAction.isLoading && <p className="text-sm text-slate-500">Actualizando etapa…</p>}
          {stageAction.error && <InlineError message={stageAction.error} />}
          {stageFeedback && !stageAction.error && <InlineSuccess message="Etapa actualizada." />}
        </section>
      </div>

      <NotesPanel
        recordId={candidate.id}
        onNotesCountChange={(count) => setCandidate({ ...candidate, notes_count: count })}
      />
    </div>
  );
}
