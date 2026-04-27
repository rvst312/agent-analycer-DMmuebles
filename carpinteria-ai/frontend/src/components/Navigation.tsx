"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { LayoutDashboard, FileUp, Database, Calculator } from "lucide-react";

export function Navigation() {
  const pathname = usePathname();

  const links = [
    {
      name: "Nuevo Presupuesto",
      href: "/",
      icon: FileUp,
    },
    {
      name: "Panel de Control",
      href: "/dashboard",
      icon: LayoutDashboard,
    },
    {
      name: "Base de Precios",
      href: "/knowledge",
      icon: Database,
    },
  ];

  return (
    <nav className="border-b bg-white shadow-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex w-full">
            {/* Logo */}
            <Link href="/" className="flex-shrink-0 flex items-center mr-8 hover:opacity-80 transition-opacity">
              <Calculator className="h-6 w-6 text-blue-600 mr-2" />
              <span className="font-bold text-xl text-gray-900 hidden sm:block">Carpintería AI</span>
            </Link>

            {/* Enlaces (Desktop) */}
            <div className="hidden sm:-my-px sm:flex sm:space-x-8">
              {links.map((link) => {
                const Icon = link.icon;
                const isActive = pathname === link.href || (link.href !== "/" && pathname.startsWith(link.href));
                return (
                  <Link
                    key={link.name}
                    href={link.href}
                    className={cn(
                      "inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium transition-colors",
                      isActive
                        ? "border-blue-500 text-gray-900"
                        : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                    )}
                  >
                    <Icon className="h-4 w-4 mr-2" />
                    {link.name}
                  </Link>
                );
              })}
            </div>

            {/* Enlaces (Mobile) */}
            <div className="flex sm:hidden space-x-4 w-full justify-around items-center">
              {links.map((link) => {
                const Icon = link.icon;
                const isActive = pathname === link.href || (link.href !== "/" && pathname.startsWith(link.href));
                return (
                  <Link
                    key={link.name}
                    href={link.href}
                    className={cn(
                      "flex flex-col items-center p-2 text-xs font-medium transition-colors",
                      isActive
                        ? "text-blue-600"
                        : "text-gray-500 hover:text-gray-700"
                    )}
                  >
                    <Icon className="h-5 w-5 mb-1" />
                    <span className="text-[10px]">{link.name}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
