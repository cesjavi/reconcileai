"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getActor, setActor } from "@/lib/api";

const LINKS = [
  ["/", "Dashboard"],
  ["/import", "Importar"],
  ["/run", "Conciliar"],
  ["/transactions", "Movimientos"],
  ["/review", "Revisión"],
  ["/inference", "AMD Inference"],
  ["/audit", "Auditoría"],
] as const;

export function Nav() {
  const path = usePathname();
  const [actor, setA] = useState("");
  useEffect(() => { setA(getActor()); }, []);
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-slate-900 text-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
        <Link href="/" className="text-lg font-bold tracking-tight">Reconcile<span className="text-teal-400">AI</span></Link>
        <nav aria-label="Principal" className="flex flex-1 flex-wrap gap-1">
          {LINKS.map(([href, label]) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link key={href} href={href} aria-current={active ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-400 ${active ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-800"}`}>
                {label}
              </Link>
            );
          })}
        </nav>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          Revisor
          <input value={actor} onChange={(e) => { setA(e.target.value); setActor(e.target.value); }} placeholder="tu nombre"
            maxLength={64} className="w-36 rounded-md border border-slate-600 bg-slate-800 px-2 py-1 text-white placeholder:text-slate-500" />
        </label>
      </div>
    </header>
  );
}
