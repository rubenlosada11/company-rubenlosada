import { PageSection } from "@/components/PageSection";
import { StatCard } from "@/components/StatCard";
import { ListaBarras } from "@/components/incidencias/ListaBarras";
import { RegistrosInvalidos } from "@/components/incidencias/RegistrosInvalidos";
import { TablaCruce } from "@/components/incidencias/TablaCruce";
import { TablaSatisfaccion } from "@/components/incidencias/TablaSatisfaccion";
import { ETIQUETAS_PUNTUACION, entero, etiquetaSemana, media, porcentaje } from "@/lib/formato";
import type { ResultadoAnalisis } from "@/types/incidencias";

interface ResultadosAnalisisProps {
  resultado: ResultadoAnalisis;
}

export function ResultadosAnalisis({ resultado }: ResultadosAnalisisProps) {
  const { totales, satisfaccion, por_fecha, cruces } = resultado;
  const validos = totales.validos;

  return (
    <div className="space-y-12">
      <PageSection id="resumen" title="Resumen general" description={`Fichero analizado: ${resultado.archivo}`}>
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Registros procesados" value={entero(totales.procesados)} />
          <StatCard label="Registros válidos" value={entero(validos)} detail={porcentaje(validos, totales.procesados)} />
          <StatCard
            label="Inválidos o incompletos"
            value={entero(totales.invalidos)}
            detail={`${porcentaje(totales.invalidos, totales.procesados)} · excluidos de las métricas`}
          />
          <StatCard
            label="Satisfacción media"
            value={media(satisfaccion.media)}
            detail={`sobre 5 · ${entero(satisfaccion.con_puntuacion)} de ${entero(satisfaccion.cerradas)} cerradas con puntuación`}
          />
        </dl>
      </PageSection>

      <PageSection id="categoria" title="Por categoría" description="Incidencias válidas por tipo de problema.">
        <ListaBarras titulo="Incidencias por categoría" datos={resultado.por_categoria} total={validos} />
      </PageSection>

      <PageSection id="estado" title="Por estado" description="Situación actual de las incidencias válidas.">
        <ListaBarras titulo="Incidencias por estado" datos={resultado.por_estado} total={validos} />
      </PageSection>

      <PageSection
        id="satisfaccion"
        title="Satisfacción"
        description="Solo incidencias cerradas con puntuación (escala 1–5)."
      >
        <div className="space-y-4">
          <ListaBarras
            titulo={`Distribución de puntuaciones · media ${media(satisfaccion.media)} / 5`}
            datos={satisfaccion.distribucion}
            total={satisfaccion.con_puntuacion}
            etiqueta={(p) => `${p} · ${ETIQUETAS_PUNTUACION[p] ?? ""}`}
          />
          <div className="grid gap-4 xl:grid-cols-2">
            <TablaSatisfaccion titulo="Por país" tituloFila="País" datos={satisfaccion.por_pais} />
            <TablaSatisfaccion titulo="Por categoría" tituloFila="Categoría" datos={satisfaccion.por_categoria} />
          </div>
          <TablaSatisfaccion titulo="Por transportista" tituloFila="Transportista" datos={satisfaccion.por_transportista} />
        </div>
      </PageSection>

      <PageSection id="invalidos" title="Registros inválidos" description="Registros que incumplen alguna regla de CONTEXT-incidencias.es.md.">
        <RegistrosInvalidos resultado={resultado} />
      </PageSection>

      <PageSection id="desgloses" title="Más desgloses" description="País, tipo de cliente y transportista (registros válidos).">
        <div className="grid gap-4 xl:grid-cols-2">
          <ListaBarras titulo="Por país" datos={resultado.por_pais} total={validos} />
          <ListaBarras titulo="Por tipo de cliente" datos={resultado.por_tipo_cliente} total={validos} />
          <div className="xl:col-span-2">
            <ListaBarras titulo="Por transportista" datos={resultado.por_transportista} total={validos} />
          </div>
        </div>
      </PageSection>

      <PageSection id="temporal" title="Evolución temporal" description="Registros válidos agrupados por fecha de la incidencia.">
        <div className="grid gap-4 xl:grid-cols-2">
          <ListaBarras titulo="Por semana (ISO)" datos={por_fecha.semana} total={validos} etiqueta={etiquetaSemana} />
          <ListaBarras titulo="Por día de la semana" datos={por_fecha.dia_semana} total={validos} />
          <ListaBarras titulo="Por mes" datos={por_fecha.mes} total={validos} />
          <ListaBarras titulo="Por trimestre" datos={por_fecha.trimestre} total={validos} />
        </div>
      </PageSection>

      <PageSection id="cruces" title="Cruces" description="Dónde se concentra cada tipo de incidencia (registros válidos).">
        <div className="space-y-4">
          <TablaCruce titulo="País × categoría" tituloFila="País" datos={cruces.pais_categoria} />
          <TablaCruce titulo="Transportista × categoría" tituloFila="Transportista" datos={cruces.transportista_categoria} />
          <TablaCruce titulo="Transportista × estado" tituloFila="Transportista" datos={cruces.transportista_estado} />
        </div>
      </PageSection>
    </div>
  );
}
