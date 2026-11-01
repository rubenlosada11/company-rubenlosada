import type { Metadata } from "next";
import { InboundForm } from "@/components/inventory/InboundForm";
import { InventoryHeader } from "@/components/inventory/InventoryHeader";
import { parseSkuId } from "@/lib/inventory";

export const metadata: Metadata = {
  title: "Registrar entrada de stock | TrackFlow Tech",
  description: "Registro de recepciones de mercancía de las marcas cliente en Los Ángeles y Zaragoza.",
};

interface InboundPageProps {
  /** `?sku_id=` llega desde «Registrar entrada» del listado de productos. */
  searchParams: Promise<{ sku_id?: string | string[] }>;
}

export default async function InboundPage({ searchParams }: InboundPageProps) {
  const { sku_id } = await searchParams;
  const initialSkuId = parseSkuId(typeof sku_id === "string" ? sku_id : null);
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <InventoryHeader
        title="Registrar entrada de stock"
        description="Una entrada es una recepción de mercancía: un envío de una marca cliente que llega a un almacén de TrackFlow. Suma unidades al stock del producto en su almacén."
      />
      {/* La clave reinicia el formulario si se llega con otro producto en el enlace sin salir de la página. */}
      <InboundForm key={initialSkuId ?? "none"} initialSkuId={initialSkuId} />
    </div>
  );
}
