"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import Link from "next/link";
import React from "react";

export function SimpleNavbar({ title, userName }: { title: string; userName?: string }) {
  return (
    <div className="bg-white border-b border-gray-100">
      <div className="flex items-center justify-between px-4 sm:px-6 py-3 max-w-7xl mx-auto w-full">
        <Link href="/" className="flex items-center gap-2 hover:opacity-90 transition-opacity">
          <div className="flex items-center justify-center w-8 h-8 rounded-xl bg-blue-50 text-blue-600 font-bold text-sm">
            DN
          </div>
          <span className="font-semibold text-gray-900 tracking-tight">{title}</span>
        </Link>
        
        {userName && (
          <div className="flex items-center gap-3">
            <div className="text-sm font-medium text-gray-600 hidden sm:block">{userName}</div>
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white shadow-sm ring-2 ring-white">
              {userName.charAt(0).toUpperCase()}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export interface NavLink {
  name: string;
  href: string;
  icon?: React.ElementType;
}

export function SecondaryNavbar({
  currentType,
  links,
  onTypeChange
}: {
  currentType: string;
  links: NavLink[];
  onTypeChange?: (href: string) => void;
}) {
  return (
    <div className="bg-white/80 backdrop-blur-md border-b border-gray-200/80 sticky top-0 z-40">
      <div className="flex overflow-x-auto no-scrollbar space-x-2 sm:space-x-4 px-4 sm:px-6 max-w-7xl mx-auto w-full">
        {links.map((link) => {
          const isActive = currentType === link.href || (link.href !== "/" && currentType.startsWith(link.href));
          const Icon = link.icon;

          const inner = (
            <>
              <span className="flex items-center gap-2 relative z-10">
                {Icon && <Icon className="w-4 h-4" />}
                {link.name}
              </span>
              {isActive && (
                <motion.div
                  layoutId="secondary-nav-indicator"
                  className="absolute bottom-0 left-0 right-0 h-[2px] bg-blue-600"
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
              {isActive && (
                <motion.div
                  layoutId="secondary-nav-bg"
                  className="absolute inset-0 bg-gray-50/50 rounded-t-md"
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
            </>
          );

          if (onTypeChange) {
            return (
              <button
                key={link.name}
                onClick={() => onTypeChange(link.href)}
                className={cn(
                  "relative px-3 py-3 text-sm font-medium transition-colors hover:text-gray-900 whitespace-nowrap",
                  isActive ? "text-blue-700" : "text-gray-500"
                )}
              >
                {inner}
              </button>
            );
          }

          return (
            <Link
              key={link.name}
              href={link.href}
              className={cn(
                "relative px-3 py-3 text-sm font-medium transition-colors hover:text-gray-900 whitespace-nowrap",
                isActive ? "text-blue-700" : "text-gray-500"
              )}
            >
              {inner}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
