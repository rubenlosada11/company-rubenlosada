"use client";

import { useState } from "react";
import { PageSection } from "@/components/PageSection";
import { IncidentList } from "./IncidentList";
import { IncidentSummary } from "./IncidentSummary";

/** Resumen y listado de `/gestor-incidencias`. Son independientes: solo comparten el aviso de que los datos cambian. */
export function IncidentDashboard() {
  const [version, setVersion] = useState(0);

  return (
    <>
      <PageSection
        id="resumen"
        title="Resumen"
        description="Totales de todas las incidencias registradas, por estado, categoría, sede y origen."
      >
        <IncidentSummary version={version} />
      </PageSection>

      <PageSection
        id="listado"
        title="Listado"
        description="De la más reciente a la más antigua. Filtra por estado, origen, sede o categoría y cambia el estado desde cada fila."
      >
        <IncidentList onChanged={() => setVersion((current) => current + 1)} />
      </PageSection>
    </>
  );
}
