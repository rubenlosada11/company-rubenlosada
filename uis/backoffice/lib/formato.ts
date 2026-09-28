const ENTERO = new Intl.NumberFormat("es-ES");
const UN_DECIMAL = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const DOS_DECIMALES = new Intl.NumberFormat("es-ES", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const ETIQUETAS_PUNTUACION: Record<string, string> = {
  "1": "Muy insatisfecho",
  "2": "Insatisfecho",
  "3": "Neutral",
  "4": "Satisfecho",
  "5": "Muy satisfecho",
};

export const PUNTUACION_MAXIMA = 5;

export function entero(n: number): string {
  return ENTERO.format(n);
}

export function porcentaje(parte: number, total: number): string {
  return total ? `${UN_DECIMAL.format((parte * 100) / total)} %` : "—";
}

export function media(valor: number | null): string {
  return valor === null ? "—" : DOS_DECIMALES.format(valor);
}

export function tamanoFichero(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${UN_DECIMAL.format(bytes / 1024)} KB`;
}

/** "2024-S01" → "Semana 1 (01/01–07/01)", con las fechas de lunes a domingo (ISO 8601). */
export function etiquetaSemana(clave: string): string {
  const [anio, semana] = clave.split("-S").map(Number);
  const cuatroEnero = new Date(Date.UTC(anio, 0, 4));
  const lunesSemana1 = cuatroEnero.getTime() - ((cuatroEnero.getUTCDay() + 6) % 7) * 86_400_000;
  const lunes = new Date(lunesSemana1 + (semana - 1) * 7 * 86_400_000);
  const domingo = new Date(lunes.getTime() + 6 * 86_400_000);
  const dia = (d: Date) =>
    `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
  return `Semana ${semana} (${dia(lunes)}–${dia(domingo)})`;
}
