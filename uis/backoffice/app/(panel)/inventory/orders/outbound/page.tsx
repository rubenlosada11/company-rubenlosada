import type { Metadata } from "next";
import { InventoryHeader } from "@/components/inventory/InventoryHeader";
import { OutboundForm } from "@/components/inventory/OutboundForm";
import { parseSkuId } from "@/lib/inventory";

export const metadata: Metadata = {
  title: "Registrar salida de stock | TrackFlow Tech",
  description: "Registro de despachos a clientes y pérdidas confirmadas en Los Ángeles y Zaragoza.",
};

interface OutboundPageProps {
  /** `?sku_id=` llega desde «Registrar salida» del listado de productos. */
  searchParams: Promise<{ sku_id?: string | string[] }>;
}

export default async function OutboundPage({ searchParams }: OutboundPageProps) {
  const { sku_id } = await searchParams;
  const initialSkuId = parseSkuId(typeof sku_id === "string" ? sku_id : null);
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <InventoryHeader
        title="Registrar salida de stock"
        description="Una salida es un despacho para un envío a cliente o una pérdida confirmada (discrepancia o daño). Resta unidades del stock del producto en su almacén, que nunca puede quedar por debajo de cero."
      />
      {/* La clave reinicia el formulario si se llega con otro producto en el enlace sin salir de la página. */}
      <OutboundForm key={initialSkuId ?? "none"} initialSkuId={initialSkuId} />
    </div>
  );
}
