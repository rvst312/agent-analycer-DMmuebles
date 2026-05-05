"use client";

import { LineaPresupuesto } from '@/types/estimate';
import React, { useEffect, useRef } from 'react';

interface EstimateBreakdownProps {
  lineas: LineaPresupuesto[];
  subtotal: number;
  iva: number;
  total: number;
  onChange: (newLineas: LineaPresupuesto[]) => void;
}

const AutoResizeTextarea = ({
  value,
  onChange,
  className,
}: {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  className?: string;
}) => {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = 'auto';
      ref.current.style.height = ref.current.scrollHeight + 'px';
    }
  }, [value]);
  return (
    <textarea
      ref={ref}
      value={value}
      onChange={onChange}
      className={`resize-none overflow-hidden ${className}`}
      rows={1}
    />
  );
};

// Groups lines preserving insertion order of ref keys.
function groupByRef(lineas: LineaPresupuesto[]): Map<string, { lineas: LineaPresupuesto[]; indices: number[] }> {
  const groups = new Map<string, { lineas: LineaPresupuesto[]; indices: number[] }>();
  lineas.forEach((linea, idx) => {
    const key = linea.ref?.trim() || 'SIN-REF';
    if (!groups.has(key)) groups.set(key, { lineas: [], indices: [] });
    groups.get(key)!.lineas.push(linea);
    groups.get(key)!.indices.push(idx);
  });
  return groups;
}

function groupSubtotal(lineas: LineaPresupuesto[]): number {
  return lineas.reduce((sum, l) => sum + (l.precio_pendiente ? 0 : (l.subtotal ?? 0)), 0);
}

const REF_COLORS = [
  { header: 'bg-slate-700', badge: 'bg-slate-100 text-slate-700 border-slate-300' },
  { header: 'bg-blue-700',  badge: 'bg-blue-50  text-blue-700  border-blue-300'  },
  { header: 'bg-violet-700',badge: 'bg-violet-50 text-violet-700 border-violet-300'},
  { header: 'bg-emerald-700',badge:'bg-emerald-50 text-emerald-700 border-emerald-300'},
  { header: 'bg-amber-700', badge: 'bg-amber-50  text-amber-700  border-amber-300' },
  { header: 'bg-rose-700',  badge: 'bg-rose-50   text-rose-700   border-rose-300'  },
];

export default function EstimateBreakdown({ lineas, subtotal, iva, total, onChange }: EstimateBreakdownProps) {
  const handleLineChange = (index: number, field: keyof LineaPresupuesto, value: number | string) => {
    const newLineas = [...lineas];
    const updated = { ...newLineas[index], [field]: value };
    if (field !== 'descripcion' && field !== 'codigo' && field !== 'ref') {
      updated.subtotal = Number((updated.cantidad * Number(updated.precio_unitario)).toFixed(2));
    }
    if (field === 'precio_unitario' && updated.precio_pendiente && (value as number) > 0) {
      updated.precio_pendiente = false;
    }
    newLineas[index] = updated;
    onChange(newLineas);
  };

  const groups = groupByRef(lineas);
  const refKeys = Array.from(groups.keys());

  return (
    <div className="p-4">
      <div className="space-y-6 overflow-x-auto">
        {refKeys.length === 0 && (
          <p className="px-4 py-8 text-center text-gray-500">No hay líneas en este presupuesto.</p>
        )}

        {refKeys.map((refKey, groupIdx) => {
          const { lineas: groupLineas, indices } = groups.get(refKey)!;
          const grpSubtotal = groupSubtotal(groupLineas);
          const pendingCount = groupLineas.filter(l => l.precio_pendiente).length;
          const color = REF_COLORS[groupIdx % REF_COLORS.length];

          return (
            <div key={refKey} className="rounded-lg border border-gray-200 overflow-hidden">

              {/* ── Cabecera del grupo (código de referencia del plano) ── */}
              <div className={`${color.header} px-4 py-2.5 flex items-center justify-between`}>
                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-white tracking-widest text-sm">
                    {refKey}
                  </span>
                  <span className="text-white/60 text-xs">
                    {groupLineas.length} {groupLineas.length === 1 ? 'pieza' : 'piezas'}
                  </span>
                  {pendingCount > 0 && (
                    <span className="bg-yellow-400 text-yellow-900 text-xs font-semibold px-2 py-0.5 rounded-full">
                      {pendingCount} precio{pendingCount > 1 ? 's' : ''} pendiente{pendingCount > 1 ? 's' : ''}
                    </span>
                  )}
                </div>
                <span className="text-white font-bold text-sm tabular-nums">
                  {grpSubtotal.toFixed(2)} €
                </span>
              </div>

              {/* ── Tabla de piezas del grupo ── */}
              <table className="w-full text-sm text-left">
                <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
                  <tr>
                    <th className="px-3 py-2 w-24">Código</th>
                    <th className="px-3 py-2">Descripción</th>
                    <th className="px-3 py-2 w-20 text-center">Cant.</th>
                    <th className="px-3 py-2 w-28 text-right">Precio Un. (€)</th>
                    <th className="px-3 py-2 w-28 text-right">Subtotal (€)</th>
                  </tr>
                </thead>
                <tbody>
                  {groupLineas.map((linea, localIdx) => {
                    const globalIdx = indices[localIdx];
                    return (
                      <tr
                        key={globalIdx}
                        className={`border-t transition-colors ${
                          linea.precio_pendiente
                            ? 'bg-yellow-50/50 hover:bg-yellow-50'
                            : 'bg-white hover:bg-gray-50'
                        }`}
                      >
                        {/* Código interno */}
                        <td className="px-3 py-2 align-top">
                          <span className={`inline-block font-mono text-xs px-2 py-1 rounded border ${color.badge}`}>
                            {linea.codigo || '—'}
                          </span>
                        </td>

                        {/* Descripción */}
                        <td className="px-3 py-2 align-top">
                          <AutoResizeTextarea
                            className="w-full border border-transparent hover:border-gray-200 rounded p-1.5 text-sm font-medium text-gray-900 focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 transition-colors bg-transparent leading-relaxed"
                            value={linea.descripcion}
                            onChange={(e) => handleLineChange(globalIdx, 'descripcion', e.target.value)}
                          />
                          {linea.precio_pendiente && (
                            <div className="text-xs text-yellow-600 mt-1 px-1.5 font-semibold">
                              ⚠️ Precio pendiente
                            </div>
                          )}
                        </td>

                        {/* Cantidad */}
                        <td className="px-3 py-2 align-top">
                          <input
                            type="number"
                            min="1"
                            className="w-full border border-transparent hover:border-gray-200 rounded p-1.5 text-center text-sm focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 bg-transparent transition-colors"
                            value={linea.cantidad}
                            onChange={(e) => handleLineChange(globalIdx, 'cantidad', parseFloat(e.target.value) || 0)}
                          />
                        </td>

                        {/* Precio unitario */}
                        <td className="px-3 py-2 align-top">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            className={`w-full border rounded p-1.5 text-right text-sm transition-colors focus:ring-1 focus:bg-white ${
                              linea.precio_pendiente
                                ? 'border-yellow-400 focus:ring-yellow-400 bg-yellow-50/50'
                                : 'border-transparent hover:border-gray-200 focus:border-blue-400 focus:ring-blue-400 bg-transparent'
                            }`}
                            value={linea.precio_unitario}
                            onChange={(e) => handleLineChange(globalIdx, 'precio_unitario', parseFloat(e.target.value) || 0)}
                          />
                        </td>

                        {/* Subtotal */}
                        <td className="px-3 py-2 text-right font-medium align-top">
                          <div className="py-1.5 tabular-nums text-gray-900">
                            {(linea.subtotal ?? 0).toFixed(2)}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {/* ── Resumen del grupo ── */}
              <div className="bg-gray-50 border-t border-gray-200 px-4 py-2 flex justify-between items-center text-sm">
                <span className="text-gray-400 text-xs font-mono">{refKey}</span>
                <div className="flex items-center gap-2">
                  {pendingCount > 0 && (
                    <span className="text-xs text-yellow-600">(sin {pendingCount} pendiente{pendingCount > 1 ? 's' : ''})</span>
                  )}
                  <span className="text-gray-500">Total ref.:</span>
                  <span className="font-bold text-gray-900 tabular-nums w-24 text-right">
                    {grpSubtotal.toFixed(2)} €
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Totales globales ── */}
      <div className="mt-4 border-t pt-4 space-y-1.5">
        <div className="flex justify-end text-sm">
          <span className="text-gray-600 mr-4">Subtotal:</span>
          <span className="font-medium w-28 text-right tabular-nums">{(subtotal ?? 0).toFixed(2)} €</span>
        </div>
        <div className="flex justify-end text-sm">
          <span className="text-gray-600 mr-4">IVA (21%):</span>
          <span className="font-medium w-28 text-right tabular-nums">{(iva ?? 0).toFixed(2)} €</span>
        </div>
        <div className="flex justify-end text-lg font-bold border-t pt-2 mt-1">
          <span className="mr-4">Total:</span>
          <span className="w-28 text-right tabular-nums">{(total ?? 0).toFixed(2)} €</span>
        </div>
      </div>
    </div>
  );
}
