import type { Metadata } from "next";
import { InventoryHeader } from "@/components/inventory/InventoryHeader";
import { MovementHistory } from "@/components/inventory/MovementHistory";

export const metadata: Metadata = {
  title: "Historial de movimientos de stock | TrackFlow Tech",
  description: "Entradas y salidas de stock de los almacenes de Los Ángeles y Zaragoza.",
};

export default function InventoryOrdersPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <InventoryHeader
        title="Historial de movimientos"
        description="Todas las entradas (recepciones de mercancía) y salidas (despachos y pérdidas) registradas, con el producto, la cantidad, la fecha y el usuario que las registró. Es una vista de consulta: los movimientos no se editan ni se borran."
      />
      <MovementHistory />
    </div>
  );
}
