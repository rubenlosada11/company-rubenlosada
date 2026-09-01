import type { Metadata } from "next";
import { Archivo, Manrope } from "next/font/google";
import Image from "next/image";
import Link from "next/link";
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
  title: "TrackFlow People | Talent Pipeline Tracker",
  description:
    "Panel interno de People & Talent de TrackFlow para gestionar el pipeline de candidaturas.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${archivo.variable} ${manrope.variable} h-full`}>
      <body className="min-h-full flex flex-col font-body text-slate-900 antialiased bg-slate-50 selection:bg-blue-200">
        <div
          className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_15%_10%,rgba(59,130,246,0.16),transparent_35%),radial-gradient(circle_at_86%_18%,rgba(14,165,233,0.18),transparent_32%),linear-gradient(to_bottom_right,#f8fafc,#e2e8f0)]"
          aria-hidden="true"
        />
        <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/80 backdrop-blur-md">
          <div className="mx-auto flex min-h-[74px] w-[min(1120px,92vw)] items-center justify-between gap-4">
            <Link href="/" className="inline-flex items-center gap-3" aria-label="TrackFlow People inicio">
              <Image
                src="/logo/TrackFlow_Logo1_Full.png"
                alt="Logo de TrackFlow"
                width={1190}
                height={264}
                priority
                className="h-8 w-auto max-w-[180px] object-contain sm:h-9 sm:max-w-[210px] md:h-10 md:max-w-[250px]"
              />
              <span className="rounded-full bg-blue-700 px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-white">
                People
              </span>
            </Link>
            <p className="hidden text-sm font-semibold text-slate-500 sm:block">
              Panel interno · TrackFlow Tech
            </p>
            <Link
              href="/candidates/new"
              className="rounded-full bg-blue-700 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-blue-900/20 transition hover:-translate-y-0.5 hover:bg-blue-800"
            >
              Nueva candidatura
            </Link>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-blue-900/60 bg-blue-950 py-6 text-blue-100">
          <div className="mx-auto w-[min(1120px,92vw)] text-sm">
            TrackFlow People · Talent Pipeline Tracker — uso interno de People &amp; Talent.
          </div>
        </footer>
      </body>
    </html>
  );
}
