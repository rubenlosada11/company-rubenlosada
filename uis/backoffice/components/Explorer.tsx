"use client";

import { useMemo, useState } from "react";
import { AREAS } from "@/lib/data/areas";
import { INITIATIVES } from "@/lib/data/initiatives";
import {
  type AreaFilter,
  type StatusFilter,
  STATUS_LABELS,
  STATUS_ORDER,
  countByArea,
  filterInitiatives,
} from "@/lib/initiatives";
import { AreaCard } from "./AreaCard";
import { Badge } from "./Badge";
import { PageSection } from "./PageSection";

const selectClasses =
  "w-full rounded-xl border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 sm:w-auto";

export function Explorer() {
  const [areaId, setAreaId] = useState<AreaFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");

  const counts = useMemo(() => countByArea(INITIATIVES), []);
  const visible = useMemo(() => filterInitiatives(INITIATIVES, { areaId, status }), [areaId, status]);
  const visibleAreas = AREAS.filter((area) => visible.some((item) => item.areaId === area.id));

  return (
    <>
      <PageSection
        id="areas"
        title="Áreas de negocio"
        description="Las siete áreas de TrackFlow con su responsable, equipo y la situación que TrackFlow Tech debe resolver. Selecciona un área para filtrar sus iniciativas."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {AREAS.map((area) => (
            <AreaCard
              key={area.id}
              area={area}
              initiativeCount={counts[area.id] ?? 0}
              selected={areaId === area.id}
              onToggle={() => setAreaId(areaId === area.id ? "all" : area.id)}
            />
          ))}
        </div>
      </PageSection>

      <PageSection
        id="iniciativas"
        title="Iniciativas de TrackFlow Tech"
        description="Necesidades que cada área expresa en el briefing. Ninguna está terminada como producto; algunas ya cuentan con una base técnica de hitos anteriores."
      >
        <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:flex-wrap sm:items-end">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="filter-area" className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Área
            </label>
            <select
              id="filter-area"
              value={areaId}
              onChange={(event) => setAreaId(event.target.value as AreaFilter)}
              className={selectClasses}
            >
              <option value="all">Todas las áreas</option>
              {AREAS.map((area) => (
                <option key={area.id} value={area.id}>
                  {area.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="filter-status" className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Estado
            </label>
            <select
              id="filter-status"
              value={status}
              onChange={(event) => setStatus(event.target.value as StatusFilter)}
              className={selectClasses}
            >
              <option value="all">Todos los estados</option>
              {STATUS_ORDER.map((item) => (
                <option key={item} value={item}>
                  {STATUS_LABELS[item]}
                </option>
              ))}
            </select>
          </div>

          <p role="status" className="text-sm font-semibold text-slate-600 sm:ml-auto">
            Mostrando {visible.length} de {INITIATIVES.length} iniciativas
          </p>
        </div>

        {visible.length === 0 ? (
          <p className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-600">
            Ninguna iniciativa coincide con los filtros seleccionados.
          </p>
        ) : (
          <div className="mt-5 space-y-6">
            {visibleAreas.map((area) => (
              <div key={area.id}>
                <h3 className="mb-2 text-sm font-bold uppercase tracking-wide text-slate-500">{area.name}</h3>
                <ul className="space-y-2">
                  {visible
                    .filter((item) => item.areaId === area.id)
                    .map((item) => (
                      <li key={item.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <p className="font-semibold text-slate-900">{item.title}</p>
                          <div className="flex flex-wrap gap-1.5">
                            {item.optional ? <Badge tone="neutral">Opcional</Badge> : null}
                            <Badge tone={item.status === "foundation" ? "emerald" : "amber"}>
                              {STATUS_LABELS[item.status]}
                            </Badge>
                          </div>
                        </div>
                        <p className="mt-1 text-sm text-slate-600">{item.detail}</p>
                        {item.foundation ? (
                          <p className="mt-2 border-l-2 border-emerald-300 pl-3 text-xs text-slate-600">
                            {item.foundation}
                          </p>
                        ) : null}
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </PageSection>
    </>
  );
}
