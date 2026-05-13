"use client";

import { SecondaryNavbar, SimpleNavbar } from "@/components/ui/core-header-navbar";
import { Database, FileUp, LayoutDashboard } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { clearToken } from "@/lib/auth";

export function Navigation() {
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === '/login') return null;

  const links = [
    { name: "Nuevo Presupuesto", href: "/", icon: FileUp },
    { name: "Panel de Control", href: "/dashboard", icon: LayoutDashboard },
    { name: "Base de Precios", href: "/knowledge", icon: Database },
  ];

  const handleLogout = () => {
    clearToken();
    router.push('/login');
  };

  return (
    <nav className="flex flex-col w-full relative z-50">
      <SimpleNavbar
        title="DN Muebles"
        userName="Admin"
        onLogout={handleLogout}
      />
      <SecondaryNavbar currentType={pathname} links={links} />
    </nav>
  );
}
