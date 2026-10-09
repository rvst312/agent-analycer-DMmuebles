"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FileUp, LayoutDashboard, Database, Calculator, LogOut } from "lucide-react";
import { clearToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const LINKS = [
  { name: "Nuevo Presupuesto", href: "/",          icon: FileUp },
  { name: "Panel de Control",  href: "/dashboard", icon: LayoutDashboard },
  { name: "Base de Precios",   href: "/knowledge", icon: Database },
  { name: "Tarifa",            href: "/tarifa",    icon: Calculator },
];

export function Navigation() {
  const pathname = usePathname();
  const router   = useRouter();

  if (pathname === "/login") return null;

  const handleLogout = () => { clearToken(); router.push("/login"); };

  return (
    <header className="sticky top-0 z-50 bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center h-12 gap-6">

        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 shrink-0 mr-2">
          <div className="w-7 h-7 rounded bg-gray-900 flex items-center justify-center text-white text-xs font-bold tracking-tight">
            DN
          </div>
          <span className="font-semibold text-gray-900 text-sm hidden sm:block">DN Muebles</span>
        </Link>

        {/* Divider */}
        <div className="h-5 w-px bg-gray-200 shrink-0" />

        {/* Nav links */}
        <nav className="flex items-center gap-0.5 flex-1 overflow-x-auto no-scrollbar">
          {LINKS.map(({ name, href, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors whitespace-nowrap",
                  active
                    ? "bg-gray-100 text-gray-900"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-50"
                )}
              >
                <Icon className="w-3.5 h-3.5 shrink-0" />
                {name}
              </Link>
            );
          })}
        </nav>

        {/* User + logout */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-sm text-gray-500 hidden sm:block">Admin</span>
          <button
            onClick={handleLogout}
            title="Cerrar sesión"
            className="flex items-center justify-center w-7 h-7 rounded text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
