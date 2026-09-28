// Respuesta de POST /api/incidents/analyze (services/api). Es el mismo resultado
// que calcula `analizar()` en packages/analisis-incidencias, más las etiquetas de las reglas.

export type Conteo = Record<string, number>;

export interface Satisfaccion {
  cerradas: number;
  con_puntuacion: number;
  media: number | null;
  distribucion: Conteo;
}

export interface RegistroInvalido {
  linea: number;
  incident_id: string;
  reglas: string[];
}

export interface Regla {
  etiqueta: string;
  complementaria: boolean;
}

export interface ResultadoAnalisis {
  archivo: string;
  totales: { procesados: number; validos: number; invalidos: number };
  invalidos_por_regla: Conteo;
  registros_invalidos: RegistroInvalido[];
  por_categoria: Conteo;
  por_estado: Conteo;
  por_pais: Conteo;
  por_tipo_cliente: Conteo;
  por_transportista: Conteo;
  por_fecha: { mes: Conteo; trimestre: Conteo; semana: Conteo; dia_semana: Conteo };
  cruces: {
    pais_categoria: Record<string, Conteo>;
    transportista_categoria: Record<string, Conteo>;
    transportista_estado: Record<string, Conteo>;
  };
  satisfaccion: Satisfaccion & {
    por_pais: Record<string, Satisfaccion>;
    por_categoria: Record<string, Satisfaccion>;
    por_transportista: Record<string, Satisfaccion>;
  };
  reglas: Record<string, Regla>;
}
