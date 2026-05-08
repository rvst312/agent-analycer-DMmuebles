"use client";

import { LineaPresupuesto } from '@/types/estimate';
import { ChevronDown, ChevronUp } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';

interface EstimateBreakdownProps {
  lineas: LineaPresupuesto[];
  subtotal: number;
  iva: number;
  total: number;
  onChange: (newLineas: LineaPresupuesto[]) => void;
  onDescriptionsChange?: (descriptions: Record<string, string>) => void;
}

// ── helpers ──────────────────────────────────────────────────────────────────

const AutoResizeTextarea = ({
  value, onChange, className,
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
    <textarea ref={ref} value={value} onChange={onChange} rows={1}
      className={`resize-none overflow-hidden ${className}`} />
  );
};

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
  return lineas.reduce((s, l) => s + (l.precio_pendiente ? 0 : (l.subtotal ?? 0)), 0);
}

/** Genera una descripción comercial concisa a partir de las líneas del grupo */
function buildAutoDescription(ref: string, lineas: LineaPresupuesto[]): string {
  const typeCount: Record<string, number> = {};
  const materials = new Set<string>();
  let maxArea = 0, maxW = 0, maxH = 0;

  for (const l of lineas) {
    // Formato: "Tipo de material acabado (WxHcm)"
    const m = l.descripcion.match(/^(\w+)\s+de\s+(.+?)\s+\((\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)cm\)/i);
    if (m) {
      const tipo = m[1].toLowerCase();
      typeCount[tipo] = (typeCount[tipo] || 0) + (l.cantidad || 1);
      const mat = m[2].trim().split(/\s+/)[0];
      if (mat.length > 2) materials.add(mat.toLowerCase());
      const w = parseFloat(m[3]), h = parseFloat(m[4]);
      if (w * h > maxArea) { maxArea = w * h; maxW = w; maxH = h; }
    }
  }

  const typeLabels: Record<string, string> = {
    puerta: 'puerta', tablero: 'tablero', cajon: 'cajón', cajón: 'cajón',
    estante: 'estante', barra: 'barra', herraje: 'herraje', armario: 'armario',
  };
  const componentes = Object.entries(typeCount)
    .filter(([t]) => t !== 'herraje')
    .map(([t, n]) => `${n} ${typeLabels[t] || t}${n > 1 ? 's' : ''}`)
    .join(', ');

  const matList = Array.from(materials).slice(0, 3).join(', ');
  const dim = maxW > 0 ? `${Math.round(maxW)}x${Math.round(maxH)} cm` : '';

  return [
    `Suministro e instalación de módulo ${ref} según plano.`,
    componentes ? `Incluye: ${componentes}.` : '',
    dim ? `Medidas aprox: ${dim}` : '',
    matList ? `Materiales y acabados: ${matList}` : '',
  ].filter(Boolean).join('\n');
}

const REF_COLORS = [
  { header: 'bg-slate-700',   badge: 'bg-slate-100  text-slate-700  border-slate-300'  },
  { header: 'bg-blue-700',    badge: 'bg-blue-50    text-blue-700   border-blue-300'   },
  { header: 'bg-violet-700',  badge: 'bg-violet-50  text-violet-700 border-violet-300' },
  { header: 'bg-emerald-700', badge: 'bg-emerald-50 text-emerald-700 border-emerald-300' },
  { header: 'bg-amber-700',   badge: 'bg-amber-50   text-amber-700  border-amber-300'  },
  { header: 'bg-rose-700',    badge: 'bg-rose-50    text-rose-700   border-rose-300'   },
];

// ── component ─────────────────────────────────────────────────────────────────

export default function EstimateBreakdown({ lineas, subtotal, iva, total, onChange, onDescriptionsChange }: EstimateBreakdownProps) {
  const groups   = groupByRef(lineas);
  const refKeys  = Array.from(groups.keys());

  const [openGroups, setOpenGroups]   = useState<Set<string>>(() => new Set(refKeys));
  const [descriptions, setDescriptions] = useState<Record<string, string>>(() => {
    const d: Record<string, string> = {};
    for (const k of refKeys) d[k] = buildAutoDescription(k, groups.get(k)!.lineas);
    return d;
  });

  // Notify parent whenever group descriptions change so they can be sent on approval
  useEffect(() => {
    onDescriptionsChange?.(descriptions);
  }, [descriptions, onDescriptionsChange]);

  // Add auto-description for new ref keys that appear (e.g. during SSE streaming)
  useEffect(() => {
    const g = groupByRef(lineas);
    setDescriptions(prev => {
      const next = { ...prev };
      let changed = false;
      Array.from(g.entries()).forEach(([k, { lineas: gl }]) => {
        if (next[k] === undefined) {
          next[k] = buildAutoDescription(k, gl);
          changed = true;
        }
      });
      return changed ? next : prev;
    });
    setOpenGroups(prev => {
      const next = new Set(prev);
      let changed = false;
      Array.from(g.keys()).forEach(k => { if (!next.has(k)) { next.add(k); changed = true; } });
      return changed ? next : prev;
    });
  }, [lineas]);

  const toggleGroup = (ref: string) => {
    setOpenGroups(prev => {
      const next = new Set(prev);
      if (next.has(ref)) {
        next.delete(ref);
      } else {
        next.add(ref);
      }
      return next;
    });
  };

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

  return (
    <div className="p-4 space-y-3">

      {/* ── grupos en acordeón ─────────────────────────────────────────── */}
      {refKeys.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-400">No hay líneas en este presupuesto.</p>
      )}

      {refKeys.map((refKey, groupIdx) => {
        const groupData = groups.get(refKey);
        if (!groupData) return null;
        const { lineas: groupLineas, indices } = groupData;
        const grpSubtotal  = groupSubtotal(groupLineas);
        const pendingCount = groupLineas.filter(l => l.precio_pendiente).length;
        const color        = REF_COLORS[groupIdx % REF_COLORS.length];
        const isOpen       = openGroups.has(refKey);
        const desc         = descriptions[refKey] ?? '';

        return (
          <div key={refKey} className="rounded-xl border border-gray-200 overflow-hidden shadow-sm">

            {/* ── cabecera / botón acordeón ── */}
            <button
              type="button"
              onClick={() => toggleGroup(refKey)}
              className={`w-full ${color.header} px-4 py-3 flex items-center justify-between gap-3 text-left transition-opacity hover:opacity-90`}
            >
              <div className="flex items-center gap-3 min-w-0">
                {/* código ref */}
                <span className="font-mono font-bold text-white text-sm tracking-widest shrink-0">
                  {refKey}
                </span>

                {/* descripción resumida (primera línea) */}
                <span className="text-white/75 text-xs truncate hidden sm:block">
                  {desc.split('\n')[0]}
                </span>

                {/* badges */}
                <span className="text-white/60 text-xs shrink-0">
                  {groupLineas.length} {groupLineas.length === 1 ? 'pieza' : 'piezas'}
                </span>
                {pendingCount > 0 && (
                  <span className="shrink-0 bg-yellow-400 text-yellow-900 text-xs font-semibold px-2 py-0.5 rounded-full">
                    {pendingCount} pendiente{pendingCount > 1 ? 's' : ''}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-3 shrink-0">
                <span className="text-white font-bold tabular-nums text-sm">
                  {grpSubtotal.toFixed(2)} €
                </span>
                {isOpen
                  ? <ChevronUp  className="w-4 h-4 text-white/80" />
                  : <ChevronDown className="w-4 h-4 text-white/80" />}
              </div>
            </button>

            {/* ── contenido desplegable ── */}
            {isOpen && (
              <>
                {/* descripción editable */}
                <div className="px-4 pt-3 pb-2 bg-gray-50 border-b border-gray-200">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">
                    Descripción del módulo
                  </p>
                  <textarea
                    className="w-full text-sm text-gray-700 bg-white border border-gray-200 rounded-lg p-2.5 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none leading-relaxed"
                    rows={4}
                    value={desc}
                    onChange={e => {
                      const val = e.target.value;
                      setDescriptions(prev => ({ ...prev, [refKey]: val }));
                    }}
                  />
                </div>

                {/* tabla de piezas */}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-gray-50 text-gray-500 text-xs uppercase border-b border-gray-200">
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
                          <tr key={globalIdx}
                            className={`border-t transition-colors ${linea.precio_pendiente ? 'bg-yellow-50/50 hover:bg-yellow-50' : 'bg-white hover:bg-gray-50'}`}>

                            {/* código interno */}
                            <td className="px-3 py-2 align-top">
                              <span className={`inline-block font-mono text-xs px-2 py-1 rounded border ${color.badge}`}>
                                {linea.codigo || '—'}
                              </span>
                            </td>

                            {/* descripción */}
                            <td className="px-3 py-2 align-top">
                              <AutoResizeTextarea
                                className="w-full border border-transparent hover:border-gray-200 rounded p-1.5 text-sm font-medium text-gray-900 focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 transition-colors bg-transparent leading-relaxed"
                                value={linea.descripcion}
                                onChange={e => handleLineChange(globalIdx, 'descripcion', e.target.value)}
                              />
                              {linea.precio_pendiente && (
                                <div className="text-xs text-yellow-600 mt-1 px-1.5 font-semibold">
                                  ⚠️ Precio pendiente
                                </div>
                              )}
                            </td>

                            {/* cantidad */}
                            <td className="px-3 py-2 align-top">
                              <input type="number" min="1"
                                className="w-full border border-transparent hover:border-gray-200 rounded p-1.5 text-center text-sm focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 bg-transparent transition-colors"
                                value={linea.cantidad}
                                onChange={e => handleLineChange(globalIdx, 'cantidad', parseFloat(e.target.value) || 0)} />
                            </td>

                            {/* precio unitario */}
                            <td className="px-3 py-2 align-top">
                              <input type="number" step="0.01" min="0"
                                className={`w-full border rounded p-1.5 text-right text-sm transition-colors focus:ring-1 focus:bg-white ${linea.precio_pendiente ? 'border-yellow-400 focus:ring-yellow-400 bg-yellow-50/50' : 'border-transparent hover:border-gray-200 focus:border-blue-400 focus:ring-blue-400 bg-transparent'}`}
                                value={linea.precio_unitario}
                                onChange={e => handleLineChange(globalIdx, 'precio_unitario', parseFloat(e.target.value) || 0)} />
                            </td>

                            {/* subtotal */}
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
                </div>

                {/* pie del grupo */}
                <div className="bg-gray-50 border-t border-gray-200 px-4 py-2 flex justify-between items-center text-sm">
                  <span className="text-gray-400 text-xs font-mono">{refKey}</span>
                  <div className="flex items-center gap-2">
                    {pendingCount > 0 && (
                      <span className="text-xs text-yellow-600">
                        (sin {pendingCount} pendiente{pendingCount > 1 ? 's' : ''})
                      </span>
                    )}
                    <span className="text-gray-500">Total:</span>
                    <span className="font-bold text-gray-900 tabular-nums w-24 text-right">
                      {grpSubtotal.toFixed(2)} €
                    </span>
                  </div>
                </div>
              </>
            )}
          </div>
        );
      })}

      {/* ── totales globales ── */}
      {refKeys.length > 0 && (
        <div className="border-t pt-4 mt-2 space-y-1.5">
          <div className="flex justify-end text-sm">
            <span className="text-gray-500 mr-4">Subtotal:</span>
            <span className="font-medium w-28 text-right tabular-nums">{(subtotal ?? 0).toFixed(2)} €</span>
          </div>
          <div className="flex justify-end text-sm">
            <span className="text-gray-500 mr-4">IVA (21%):</span>
            <span className="font-medium w-28 text-right tabular-nums">{(iva ?? 0).toFixed(2)} €</span>
          </div>
          <div className="flex justify-end text-lg font-bold border-t pt-2 mt-1">
            <span className="mr-4">Total:</span>
            <span className="w-28 text-right tabular-nums">{(total ?? 0).toFixed(2)} €</span>
          </div>
        </div>
      )}
    </div>
  );
}
