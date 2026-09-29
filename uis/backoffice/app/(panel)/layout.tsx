import { AuthGate } from "@/components/auth/AuthGate";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";

/** Panel interno (`/`, `/proveedores`, `/incidencias`): solo con sesión iniciada. */
export default function PanelLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <div className="lg:grid lg:min-h-screen lg:grid-cols-[264px_minmax(0,1fr)]">
        <Sidebar />
        <div className="flex min-w-0 flex-col">
          <Topbar />
          <main id="contenido" className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
            {children}
          </main>
        </div>
      </div>
    </AuthGate>
  );
}
