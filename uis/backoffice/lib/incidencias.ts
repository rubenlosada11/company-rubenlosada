import { fetchApi } from "@/lib/http";
import type { ResultadoAnalisis } from "@/types/incidencias";

/** Endpoints del analizador de incidencias en `services/api` (ver CONTEXT-incidencias.es.md). */
export async function analizarCsv(archivo: File): Promise<ResultadoAnalisis> {
  const formulario = new FormData();
  formulario.append("file", archivo);
  // Sin `Content-Type`: el navegador pone `multipart/form-data` con su `boundary`.
  const res = await fetchApi("/api/incidents/analyze", {
    method: "POST",
    headers: { Accept: "application/json" },
    body: formulario,
  });
  return (await res.json()) as ResultadoAnalisis;
}

/** Descarga el último análisis con el nombre de `Content-Disposition` (la API lo expone por CORS). */
export async function descargarResultados(): Promise<void> {
  const res = await fetchApi("/api/incidents/results/export");
  const disposicion = res.headers.get("Content-Disposition") ?? "";
  const nombre = /filename="?([^";]+)"?/.exec(disposicion)?.[1] ?? "results.csv";

  const url = URL.createObjectURL(await res.blob());
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.append(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(url);
}
