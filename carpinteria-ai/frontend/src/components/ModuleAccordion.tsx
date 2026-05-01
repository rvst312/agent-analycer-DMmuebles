"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { ModuloProyecto, LineaPresupuesto } from "@/types/estimate";
import EstimateBreakdown from "@/components/EstimateBreakdown";

interface ModuleAccordionProps {
  modulo: ModuloProyecto;
  onLinesChange?: (estimateId: string, newLineas: LineaPresupuesto[]) => void;
}

const STATUS_LABELS: Record<string, string> = {
  processing: "Procesando",
  pending_review: "Pendiente revisión",
  approved: "Aprobado",
  rejected: "Rechazado",
  error: "Error",
};

const STATUS_COLORS: Record<string, string> = {
  processing: "bg-blue-100 text-blue-700",
  pending_review: "bg-yellow-100 text-yellow-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
  error: "bg-red-100 text-red-700",
};

export default function ModuleAccordion({ modulo, onLinesChange }: ModuleAccordionProps) {
  const [open, setOpen] = useState(false);
  const [lineas, setLineas] = useState<LineaPresupuesto[]>(modulo.lineas);

  const subtotal = lineas.reduce((s, l) => s + (l.precio_pendiente ? 0 : l.subtotal), 0);
  const iva = subtotal * 0.21;
  const total = subtotal + iva;

  const handleChange = (newLineas: LineaPresupuesto[]) => {
    setLineas(newLineas);
    onLinesChange?.(modulo.estimate_id, newLineas);
  };

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* Header */}
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="font-semibold text-gray-900 truncate">{modulo.nombre_modulo}</span>
          <span
            className={`text-xs px-2 py-0.5 rounded-full font-medium flex-shrink-0 ${
              STATUS_COLORS[modulo.status] ?? "bg-gray-100 text-gray-600"
            }`}
          >
            {STATUS_LABELS[modulo.status] ?? modulo.status}
          </span>
          {modulo.status === "processing" && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500 flex-shrink-0" />
          )}
        </div>
        <div className="flex items-center gap-4 flex-shrink-0 ml-4">
          <span className="text-sm font-medium text-gray-700">
            {total.toFixed(2)} € <span className="text-xs text-gray-400">(IVA inc.)</span>
          </span>
          {open ? <ChevronUp className="h-4 w-4 text-gray-500" /> : <ChevronDown className="h-4 w-4 text-gray-500" />}
        </div>
      </button>

      {/* Resumen badge */}
      {modulo.resumen && (
        <div className="px-4 py-2 bg-white border-t text-xs text-gray-500 truncate">
          {modulo.resumen.descripcion}
        </div>
      )}

      {/* Breakdown body */}
      {open && (
        <div className="p-4 bg-white border-t">
          {modulo.status === "processing" ? (
            <div className="flex items-center justify-center py-8 text-gray-400 gap-2">
              <Loader2 className="h-5 w-5 animate-spin" />
              <span className="text-sm">Analizando plano...</span>
            </div>
          ) : lineas.length === 0 ? (
            <p className="text-sm text-gray-500 py-4 text-center">No hay líneas todavía.</p>
          ) : (
            <EstimateBreakdown
              lineas={lineas}
              subtotal={subtotal}
              iva={iva}
              total={total}
              onChange={handleChange}
            />
          )}
        </div>
      )}
    </div>
  );
}
