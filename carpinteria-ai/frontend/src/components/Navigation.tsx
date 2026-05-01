"use client";

import { SecondaryNavbar, SimpleNavbar } from "@/components/ui/core-header-navbar";
import { Database, FileUp, LayoutDashboard } from "lucide-react";
import { usePathname } from "next/navigation";

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
    <nav className="flex flex-col w-full relative z-50">
      <SimpleNavbar
        title="DN Muebles"
        userName="Admin"
      />

      <SecondaryNavbar
        currentType={pathname}
        links={links}
      />
    </nav>
  );
}
