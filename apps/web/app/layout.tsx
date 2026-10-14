import "./globals.css";
import type { ReactNode } from "react";
import { Nav } from "./_components/nav";

export const metadata = { title: "ReconcileAI", description: "Conciliación bancaria asistida por IA, auditable y con revisión humana" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-20 focus:rounded focus:bg-white focus:p-2">Saltar al contenido</a>
        <Nav />
        <main id="main" className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
