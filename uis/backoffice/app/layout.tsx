import type { Metadata } from "next";
import { Archivo, Manrope } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import "./globals.css";

const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["500", "700", "900"],
});

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

export const metadata: Metadata = {
  title: "Backoffice | TrackFlow Tech",
  description:
    "Panel interno de TrackFlow Tech: áreas de negocio, iniciativas y estado de los hitos del proyecto.",
  // Herramienta interna: no debe indexarse.
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`${archivo.variable} ${manrope.variable} h-full`}>
      <body className="min-h-full bg-slate-100 font-body text-slate-900 antialiased selection:bg-blue-200">
        <a
          href="#contenido"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-blue-700 focus:px-4 focus:py-2 focus:text-sm focus:font-bold focus:text-white"
        >
          Saltar al contenido
        </a>
        <div className="lg:grid lg:min-h-screen lg:grid-cols-[264px_minmax(0,1fr)]">
          <Sidebar />
          <div className="flex min-w-0 flex-col">
            <Topbar />
            <main id="contenido" className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
