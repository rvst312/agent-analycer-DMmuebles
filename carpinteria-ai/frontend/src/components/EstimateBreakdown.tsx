"use client";

import { LineaPresupuesto, PriceCorrection } from '@/types/estimate';
import { ChevronDown, ChevronUp, BrainCircuit, CheckCircle2, Tag } from 'lucide-react';
import React, { useEffect, useMemo, useRef, useState } from 'react';

interface EstimateBreakdownProps {
  lineas: LineaPresupuesto[];
  subtotal: number;
  iva: number;
  total: number;
  onChange: (newLineas: LineaPresupuesto[]) => void;
  onDescriptionsChange?: (descriptions: Record<string, string>) => void;
  originalLineas?: LineaPresupuesto[];
  onSavePriceFeedback?: (corrections: PriceCorrection[]) => void;
  isSavingFeedback?: boolean;
  onDiscountsChange?: (totals: { subtotal: number; iva: number; total: number }) => void;
}

const PRESET_DISCOUNTS = [5, 10, 15, 20, 25];

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

export default function EstimateBreakdown({ lineas, subtotal, onChange, onDescriptionsChange, originalLineas, onSavePriceFeedback, isSavingFeedback, onDiscountsChange }: EstimateBreakdownProps) {
  const groups   = groupByRef(lineas);
  const refKeys  = Array.from(groups.keys());

  // ── descuentos por módulo ─────────────────────────────────────────────────
  // key = refKey, value = porcentaje (0-100); undefined = sin descuento activo
  const [groupDiscounts, setGroupDiscounts] = useState<Record<string, number>>({});

  const getEffectiveSubtotal = (refKey: string, raw: number): number => {
    const pct = groupDiscounts[refKey];
    return pct ? Number((raw * (1 - pct / 100)).toFixed(2)) : raw;
  };

  const effectiveSubtotal = useMemo(() => {
    const g = groupByRef(lineas);
    return Number(Array.from(g.entries()).reduce((sum, [ref, { lineas: gl }]) => {
      const raw = groupSubtotal(gl);
      const pct = groupDiscounts[ref];
      return sum + (pct ? raw * (1 - pct / 100) : raw);
    }, 0).toFixed(2));
  }, [lineas, groupDiscounts]);

  const effectiveIva = Number((effectiveSubtotal * 0.21).toFixed(2));
  const effectiveTotal = Number((effectiveSubtotal + effectiveIva).toFixed(2));

  useEffect(() => {
    onDiscountsChange?.({ subtotal: effectiveSubtotal, iva: effectiveIva, total: effectiveTotal });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveSubtotal]);

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

  // Build set of global indices whose precio_unitario was manually changed
  const changedIndices = React.useMemo<Set<number>>(() => {
    if (!originalLineas) return new Set();
    const s = new Set<number>();
    lineas.forEach((l, idx) => {
      const orig = originalLineas[idx];
      if (orig && Math.abs(l.precio_unitario - orig.precio_unitario) > 0.001) s.add(idx);
    });
    return s;
  }, [lineas, originalLineas]);

  const pendingCorrections = React.useMemo<PriceCorrection[]>(() => {
    if (!originalLineas) return [];
    const result: PriceCorrection[] = [];
    lineas.forEach((l, idx) => {
      const orig = originalLineas[idx];
      if (orig && Math.abs(l.precio_unitario - orig.precio_unitario) > 0.001) {
        result.push({
          codigo: l.codigo,
          descripcion: l.descripcion,
          precio_original: orig.precio_unitario,
          precio_corregido: l.precio_unitario,
        });
      }
    });
    return result;
  }, [lineas, originalLineas]);

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
                {groupDiscounts[refKey] !== undefined && (
                  <div className="flex items-center gap-1 text-white/80">
                    <Tag className="w-3 h-3" />
                    <span className="text-xs font-semibold">−{groupDiscounts[refKey]}%</span>
                  </div>
                )}
                <span className="text-white font-bold tabular-nums text-sm">
                  {getEffectiveSubtotal(refKey, grpSubtotal).toFixed(2)} €
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
                              <div className="flex items-center gap-1 justify-end">
                                {changedIndices.has(globalIdx) && (
                                  <span title="Precio corregido · se guardará como aprendizaje"
                                    className="flex items-center gap-0.5 text-emerald-600 text-xs font-semibold shrink-0">
                                    <CheckCircle2 className="w-3.5 h-3.5" />
                                    <span className="hidden sm:inline">Corregido</span>
                                  </span>
                                )}
                                <input type="number" step="0.01" min="0"
                                  className={`w-24 border rounded p-1.5 text-right text-sm transition-colors focus:ring-1 focus:bg-white ${
                                    changedIndices.has(globalIdx)
                                      ? 'border-emerald-400 focus:ring-emerald-400 bg-emerald-50/40'
                                      : linea.precio_pendiente
                                        ? 'border-yellow-400 focus:ring-yellow-400 bg-yellow-50/50'
                                        : 'border-transparent hover:border-gray-200 focus:border-blue-400 focus:ring-blue-400 bg-transparent'
                                  }`}
                                  value={linea.precio_unitario}
                                  onChange={e => handleLineChange(globalIdx, 'precio_unitario', parseFloat(e.target.value) || 0)} />
                              </div>
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

                {/* pie del grupo: descuento + total */}
                <div className="bg-gray-50 border-t border-gray-200 divide-y divide-dashed divide-gray-200">

                  {/* fila de control de descuento */}
                  <div className="px-4 py-2.5 flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-1.5 cursor-pointer select-none text-xs font-medium text-gray-600">
                      <input
                        type="checkbox"
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                        checked={groupDiscounts[refKey] !== undefined}
                        onChange={(e) => {
                          setGroupDiscounts(prev => {
                            const n = { ...prev };
                            if (e.target.checked) n[refKey] = 10;
                            else delete n[refKey];
                            return n;
                          });
                        }}
                      />
                      Aplicar descuento
                    </label>

                    {groupDiscounts[refKey] !== undefined && (
                      <>
                        <div className="flex items-center gap-1">
                          {PRESET_DISCOUNTS.map(pct => (
                            <button
                              key={pct}
                              type="button"
                              onClick={() => setGroupDiscounts(prev => ({ ...prev, [refKey]: pct }))}
                              className={`text-xs px-2 py-0.5 rounded border transition-colors ${
                                groupDiscounts[refKey] === pct
                                  ? 'bg-blue-600 text-white border-blue-600'
                                  : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600'
                              }`}
                            >
                              {pct}%
                            </button>
                          ))}
                        </div>
                        <div className="flex items-center gap-1">
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="0.5"
                            className="w-16 text-xs border border-gray-300 rounded px-1.5 py-0.5 text-center focus:outline-none focus:ring-1 focus:ring-blue-400"
                            value={groupDiscounts[refKey]}
                            onChange={(e) => {
                              const v = parseFloat(e.target.value);
                              if (!isNaN(v) && v >= 0 && v <= 100) {
                                setGroupDiscounts(prev => ({ ...prev, [refKey]: v }));
                              }
                            }}
                          />
                          <span className="text-xs text-gray-400">%</span>
                        </div>
                      </>
                    )}
                  </div>

                  {/* fila de totales */}
                  <div className="px-4 py-2 flex justify-between items-end text-sm">
                    <span className="text-gray-400 text-xs font-mono">{refKey}</span>
                    <div className="flex flex-col items-end gap-0.5">
                      {pendingCount > 0 && (
                        <span className="text-xs text-yellow-600">
                          (sin {pendingCount} pendiente{pendingCount > 1 ? 's' : ''})
                        </span>
                      )}
                      {groupDiscounts[refKey] !== undefined && (
                        <div className="flex items-center gap-4 text-xs">
                          <span className="text-gray-400 tabular-nums line-through">
                            {grpSubtotal.toFixed(2)} €
                          </span>
                          <span className="text-red-500 font-medium">
                            −{groupDiscounts[refKey]}% (−{(grpSubtotal * groupDiscounts[refKey] / 100).toFixed(2)} €)
                          </span>
                        </div>
                      )}
                      <div className="flex items-center gap-2">
                        <span className="text-gray-500">Total:</span>
                        <span className="font-bold text-gray-900 tabular-nums w-24 text-right">
                          {getEffectiveSubtotal(refKey, grpSubtotal).toFixed(2)} €
                        </span>
                      </div>
                    </div>
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
          {Object.keys(groupDiscounts).length > 0 && (
            <div className="flex justify-end text-sm text-gray-400">
              <span className="mr-4">Subtotal sin descuentos:</span>
              <span className="font-medium w-28 text-right tabular-nums line-through">{(subtotal ?? 0).toFixed(2)} €</span>
            </div>
          )}
          <div className="flex justify-end text-sm">
            <span className="text-gray-500 mr-4">Subtotal:</span>
            <span className="font-medium w-28 text-right tabular-nums">{effectiveSubtotal.toFixed(2)} €</span>
          </div>
          <div className="flex justify-end text-sm">
            <span className="text-gray-500 mr-4">IVA (21%):</span>
            <span className="font-medium w-28 text-right tabular-nums">{effectiveIva.toFixed(2)} €</span>
          </div>
          <div className="flex justify-end text-lg font-bold border-t pt-2 mt-1">
            <span className="mr-4">Total:</span>
            <span className="w-28 text-right tabular-nums">{effectiveTotal.toFixed(2)} €</span>
          </div>

          {/* Feedback de precios */}
          {pendingCorrections.length > 0 && onSavePriceFeedback && (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-emerald-800">
                  {pendingCorrections.length} precio{pendingCorrections.length > 1 ? 's' : ''} corregido{pendingCorrections.length > 1 ? 's' : ''}
                </p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  Guarda las correcciones para mejorar la precisión del modelo en futuros presupuestos.
                </p>
              </div>
              <button
                type="button"
                disabled={isSavingFeedback}
                onClick={() => onSavePriceFeedback(pendingCorrections)}
                className="flex items-center gap-1.5 shrink-0 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 transition-colors"
              >
                <BrainCircuit className="w-4 h-4" />
                {isSavingFeedback ? 'Guardando…' : 'Guardar y aprender'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
