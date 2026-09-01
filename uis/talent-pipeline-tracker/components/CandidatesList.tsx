"use client";

import { useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CandidateCard } from "@/components/CandidateCard";
import { FiltersBar } from "@/components/FiltersBar";
import { EmptyState, ErrorBanner, LoadingBlock } from "@/components/StateBanner";
import { useCandidates } from "@/hooks/useCandidates";
import type { CandidateStage, CandidateStatus } from "@/types/api";

function isStatus(value: string | null): value is CandidateStatus {
  return value === "received" || value === "in_progress" || value === "selected" || value === "discarded";
}

function isStage(value: string | null): value is CandidateStage {
  return (
    value === "pending" ||
    value === "review" ||
    value === "personal_interview" ||
    value === "technical_interview" ||
    value === "offer_presented"
  );
}

export function CandidatesList() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [search, setSearch] = useState("");
  const [retryKey, setRetryKey] = useState(0);

  const statusParam = searchParams.get("status");
  const stageParam = searchParams.get("stage");
  const status = isStatus(statusParam) ? statusParam : "";
  const stage = isStage(stageParam) ? stageParam : "";

  function updateQuery(next: { status?: CandidateStatus | ""; stage?: CandidateStage | "" }) {
    // Lee la URL real del navegador (no el `searchParams` del hook, que solo se
    // actualiza tras el siguiente render): así dos cambios de filtro disparados
    // en rápida sucesión no se pisan entre sí, ya que `history.replaceState` es
    // síncrono y cada llamada parte del resultado de la anterior.
    const params = new URLSearchParams(window.location.search);

    if ("status" in next) {
      if (next.status) params.set("status", next.status);
      else params.delete("status");
    }

    if ("stage" in next) {
      if (next.stage) params.set("stage", next.stage);
      else params.delete("stage");
    }

    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  return (
    <div className="space-y-6">
      <FiltersBar
        status={status}
        stage={stage}
        search={search}
        onStatusChange={(value) => updateQuery({ status: value })}
        onStageChange={(value) => updateQuery({ stage: value })}
        onSearchChange={setSearch}
      />

      <CandidatesListData
        key={`${status}|${stage}|${retryKey}`}
        status={status || undefined}
        stage={stage || undefined}
        search={search}
        onRetry={() => setRetryKey((k) => k + 1)}
      />
    </div>
  );
}

function CandidatesListData({
  status,
  stage,
  search,
  onRetry,
}: {
  status?: CandidateStatus;
  stage?: CandidateStage;
  search: string;
  onRetry: () => void;
}) {
  const listState = useCandidates({ status, stage });

  const filteredData = useMemo(() => {
    if (listState.status !== "success") return [];
    const term = search.trim().toLowerCase();
    if (!term) return listState.data;
    return listState.data.filter(
      (candidate) =>
        candidate.full_name.toLowerCase().includes(term) || candidate.email.toLowerCase().includes(term)
    );
  }, [listState, search]);

  if (listState.status === "loading") return <LoadingBlock label="Cargando candidaturas…" />;

  if (listState.status === "error") return <ErrorBanner message={listState.message} onRetry={onRetry} />;

  if (listState.data.length === 0) {
    return (
      <EmptyState
        title="Todavía no hay candidaturas"
        description="Cuando se registren candidaturas, aparecerán aquí."
      />
    );
  }

  if (filteredData.length === 0) {
    return (
      <EmptyState
        title="No hay resultados"
        description="Ninguna candidatura coincide con los filtros o la búsqueda actuales."
      />
    );
  }

  return (
    <>
      <p className="text-sm font-semibold text-slate-500">
        {filteredData.length} de {listState.total} candidatura{listState.total === 1 ? "" : "s"}
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {filteredData.map((candidate) => (
          <CandidateCard key={candidate.id} candidate={candidate} />
        ))}
      </div>
    </>
  );
}
