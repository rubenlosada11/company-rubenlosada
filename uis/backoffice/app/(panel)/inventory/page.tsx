import { redirect } from "next/navigation";

/** `/inventory` no tiene contenido propio: la entrada al inventario es el listado de productos. */
export default function InventoryPage() {
  redirect("/inventory/products");
}
