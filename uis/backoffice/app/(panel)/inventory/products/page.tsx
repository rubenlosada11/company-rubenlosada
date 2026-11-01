import type { Metadata } from "next";
import { InventoryHeader } from "@/components/inventory/InventoryHeader";
import { ProductList } from "@/components/inventory/ProductList";

export const metadata: Metadata = {
  title: "Inventario | TrackFlow Tech",
  description: "SKUs de los almacenes de Los Ángeles y Zaragoza con su stock actual.",
};

export default function InventoryProductsPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <InventoryHeader
        title="Productos y stock"
        description="SKUs de las marcas cliente en los almacenes de Los Ángeles y Zaragoza. El stock lo calcula la API (entradas menos salidas) y es siempre el del almacén de cada SKU: las cifras de los dos almacenes nunca se suman."
      />
      <ProductList />
    </div>
  );
}
