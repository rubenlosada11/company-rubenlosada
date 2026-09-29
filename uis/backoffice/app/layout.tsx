import type { Metadata } from "next";
import { Archivo, Manrope } from "next/font/google";
import { AuthProvider } from "@/components/auth/AuthProvider";
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
        {/* El panel va en app/(panel)/layout.tsx y el login en app/login: ambos comparten la sesión. */}
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
