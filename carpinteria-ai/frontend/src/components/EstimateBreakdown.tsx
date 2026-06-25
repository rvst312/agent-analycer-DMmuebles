"use client";

import { LineaPresupuesto, PriceCorrection } from '@/types/estimate';
import { ChevronDown, ChevronUp, BrainCircuit, CheckCircle2, Tag, Trash2, Plus, PenLine, Search, Sparkles, Loader2 } from 'lucide-react';
import KbSearchModal from '@/components/KbSearchModal';
import React, { useEffect, useMemo, useRef, useState } from 'react';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface EstimateBreakdownProps {
  estimateId?: string;
  lineas: LineaPresupuesto[];
  subtotal: number;
  iva: number;
  total: number;
  onChange: (newLineas: LineaPresupuesto[]) => void;
  onDescriptionsChange?: (descriptions: Record<string, string>) => void;
  onTitleChange?: (titulo: string) => void;
  originalLineas?: LineaPresupuesto[];
  onSavePriceFeedback?: (corrections: PriceCorrection[]) => void;
  isSavingFeedback?: boolean;
  onDiscountsChange?: (totals: { subtotal: number; iva: number; total: number }) => void;
  clienteId?: string;
}

const PRESET_DISCOUNTS = [5, 10, 15, 20, 25];

const AutoResizeTextarea = ({ value, onChange, className }: {
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
  return <textarea ref={ref} value={value} onChange={onChange} rows={1} className={`resize-none overflow-hidden ${className}`} />;
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

function buildAutoDescription(ref: string, lineas: LineaPresupuesto[]): string {
  const typeCount: Record<string, number> = {};
  const materials = new Set<string>();
  let maxArea = 0, maxW = 0, maxH = 0;
  for (const l of lineas) {
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
    .map(([t, n]) => `${n} ${typeLabels[t] || t}${n > 1 ? 's' : ''}`)
    .join(', ');
  const matList = Array.from(materials).slice(0, 3).join(', ');
  const dim = maxW > 0 ? `${Math.round(maxW)}x${Math.round(maxH)} cm` : '';
  return [
    `Suministro e instalación de módulo ${ref} según plano.`,
    componentes ? `Incluye: ${componentes}.` : '',
    dim ? `Medidas aprox: ${dim}` : '',
    matList ? `Materiales y acabados: ${matList}` : '',
  ].filter(Boolean).join('\n');
}

const GROUP_ACCENT = [
  { header: 'bg-slate-700',   badge: 'bg-slate-100  text-slate-700  border-slate-300'   },
  { header: 'bg-blue-700',    badge: 'bg-blue-50    text-blue-700   border-blue-300'    },
  { header: 'bg-violet-700',  badge: 'bg-violet-50  text-violet-700 border-violet-300'  },
  { header: 'bg-emerald-700', badge: 'bg-emerald-50 text-emerald-700 border-emerald-300' },
  { header: 'bg-amber-700',   badge: 'bg-amber-50   text-amber-700  border-amber-300'   },
  { header: 'bg-rose-700',    badge: 'bg-rose-50    text-rose-700   border-rose-300'    },
];

function newBlankLine(refKey: string): LineaPresupuesto {
  return { codigo: undefined, ref: refKey, descripcion: '', cantidad: 1, precio_unitario: 0, subtotal: 0, precio_pendiente: true };
}

export default function EstimateBreakdown({
  estimateId, lineas, subtotal, onChange, onDescriptionsChange, onTitleChange, originalLineas,
  onSavePriceFeedback, isSavingFeedback, onDiscountsChange, clienteId,
}: EstimateBreakdownProps) {
  const groups  = groupByRef(lineas);
  const refKeys = Array.from(groups.keys());

  const [newGroupInput, setNewGroupInput] = useState<string | null>(null);
  const [editingRef, setEditingRef]       = useState<Record<string, string>>({});
  const [kbSearchRefKey, setKbSearchRefKey] = useState<string | null>(null);
  const [groupDiscounts, setGroupDiscounts] = useState<Record<string, number>>({});
  const [generatingDesc, setGeneratingDesc] = useState<Record<string, boolean>>({});
  const [generatingTitle, setGeneratingTitle] = useState(false);
  const [titulo, setTitulo] = useState('');

  useEffect(() => { onTitleChange?.(titulo); }, [titulo, onTitleChange]);

  const generateTitle = async () => {
    if (!estimateId || lineas.length === 0) return;
    setGeneratingTitle(true);
    try {
      const res = await fetch(`${BASE_URL}/estimates/${estimateId}/generate-title`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lineas }),
      });
      if (res.ok) {
        const data = await res.json() as { titulo: string };
        setTitulo(data.titulo);
      }
    } catch { /* silently fail */ }
    finally { setGeneratingTitle(false); }
  };

  const generateDescription = async (refKey: string, groupLineas: LineaPresupuesto[]) => {
    if (!estimateId) return;
    setGeneratingDesc(prev => ({ ...prev, [refKey]: true }));
    try {
      const res = await fetch(`${BASE_URL}/estimates/${estimateId}/generate-description`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ref: refKey, lineas: groupLineas }),
      });
      if (res.ok) {
        const data = await res.json() as { description: string };
        setDescriptions(prev => ({ ...prev, [refKey]: data.description }));
      }
    } catch { /* silently fail */ }
    finally { setGeneratingDesc(prev => ({ ...prev, [refKey]: false })); }
  };

  const getEffectiveSubtotal = (refKey: string, raw: number) => {
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

  const effectiveIva   = Number((effectiveSubtotal * 0.21).toFixed(2));
  const effectiveTotal = Number((effectiveSubtotal + effectiveIva).toFixed(2));

  useEffect(() => {
    onDiscountsChange?.({ subtotal: effectiveSubtotal, iva: effectiveIva, total: effectiveTotal });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveSubtotal]);

  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set(refKeys));
  const [descriptions, setDescriptions] = useState<Record<string, string>>(() => {
    const d: Record<string, string> = {};
    for (const k of refKeys) d[k] = buildAutoDescription(k, groups.get(k)!.lineas);
    return d;
  });

  useEffect(() => { onDescriptionsChange?.(descriptions); }, [descriptions, onDescriptionsChange]);

  useEffect(() => {
    const g = groupByRef(lineas);
    setDescriptions(prev => {
      const next = { ...prev };
      let changed = false;
      Array.from(g.entries()).forEach(([k, { lineas: gl }]) => {
        if (next[k] === undefined) { next[k] = buildAutoDescription(k, gl); changed = true; }
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
    return lineas.reduce<PriceCorrection[]>((acc, l, idx) => {
      const orig = originalLineas[idx];
      if (orig && Math.abs(l.precio_unitario - orig.precio_unitario) > 0.001) {
        acc.push({ codigo: l.codigo, descripcion: l.descripcion, precio_original: orig.precio_unitario, precio_corregido: l.precio_unitario });
      }
      return acc;
    }, []);
  }, [lineas, originalLineas]);

  const toggleGroup = (ref: string) => {
    setOpenGroups(prev => { const n = new Set(prev); n.has(ref) ? n.delete(ref) : n.add(ref); return n; });
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

  const handleDeleteLine  = (idx: number) => onChange(lineas.filter((_, i) => i !== idx));
  const handleDeleteGroup = (refKey: string) => onChange(lineas.filter(l => (l.ref?.trim() || 'SIN-REF') !== refKey));

  const handleAddLineToGroup = (refKey: string) => {
    onChange([...lineas, newBlankLine(refKey)]);
    setOpenGroups(p => { const n = new Set(p); n.add(refKey); return n; });
  };

  const handleAddGroup = () => {
    const ref = (newGroupInput ?? '').trim().toUpperCase();
    if (!ref) { setNewGroupInput(null); return; }
    if (refKeys.includes(ref)) { setNewGroupInput(null); setOpenGroups(p => { const n = new Set(p); n.add(ref); return n; }); return; }
    onChange([...lineas, newBlankLine(ref)]);
    setNewGroupInput(null);
    setOpenGroups(p => { const n = new Set(p); n.add(ref); return n; });
  };

  const handleRenameGroupStart  = (refKey: string) => setEditingRef(prev => ({ ...prev, [refKey]: refKey }));
  const handleRenameGroupCommit = (oldRef: string) => {
    const newRef = (editingRef[oldRef] ?? '').trim().toUpperCase();
    if (!newRef || newRef === oldRef) { setEditingRef(prev => { const n = { ...prev }; delete n[oldRef]; return n; }); return; }
    onChange(lineas.map(l => (l.ref?.trim() || 'SIN-REF') === oldRef ? { ...l, ref: newRef } : l));
    setDescriptions(prev => { const n = { ...prev }; if (n[oldRef] !== undefined) { n[newRef] = n[oldRef]; delete n[oldRef]; } return n; });
    setGroupDiscounts(prev => { const n = { ...prev }; if (n[oldRef] !== undefined) { n[newRef] = n[oldRef]; delete n[oldRef]; } return n; });
    setOpenGroups(prev => { const n = new Set(prev); if (n.has(oldRef)) { n.delete(oldRef); n.add(newRef); } return n; });
    setEditingRef(prev => { const n = { ...prev }; delete n[oldRef]; return n; });
  };

  return (
    <div className="p-3 space-y-2">

      {/* Project title — sent to Holded as a single header item at 0 €, editable */}
      <div className="mb-2">
        <label className="block text-[11px] font-medium text-gray-400 mb-1">
          Título del proyecto (ítem a 0 € en Holded, editable)
        </label>
        <div className="relative">
          <input
            type="text"
            className="w-full text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-lg px-3 py-2 pr-9 focus:outline-none focus:ring-1 focus:ring-gray-300"
            placeholder="Ej: Puertas y rodapié, Zurbano 93"
            value={titulo}
            onChange={e => setTitulo(e.target.value)}
          />
          {estimateId && (
            <button
              type="button"
              title="Generar título con IA"
              disabled={generatingTitle}
              onClick={generateTitle}
              className="absolute top-1.5 right-1.5 p-1 rounded-md text-gray-300 hover:text-violet-600 hover:bg-violet-50 transition-all disabled:opacity-40"
            >
              {generatingTitle ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </div>

      {refKeys.length === 0 && (
        <p className="py-10 text-center text-sm text-gray-400">No hay líneas en este presupuesto.</p>
      )}

      {refKeys.map((refKey, groupIdx) => {
        const groupData = groups.get(refKey);
        if (!groupData) return null;
        const { lineas: groupLineas, indices } = groupData;
        const grpSubtotal  = groupSubtotal(groupLineas);
        const pendingCount = groupLineas.filter(l => l.precio_pendiente).length;
        const accent       = GROUP_ACCENT[groupIdx % GROUP_ACCENT.length];
        const isOpen       = openGroups.has(refKey);
        const desc         = descriptions[refKey] ?? '';
        const hasDiscount  = groupDiscounts[refKey] !== undefined;

        return (
          <div key={refKey} className="rounded-lg overflow-hidden border border-gray-200 shadow-sm">

            {/* ── Group header ── */}
            <div className={`${accent.header} px-3 py-2 flex items-center gap-2`}>
              {editingRef[refKey] !== undefined ? (
                <input
                  autoFocus
                  className="font-mono font-bold text-sm tracking-widest bg-white/20 text-white border border-white/40 rounded px-1.5 py-0.5 w-28 focus:outline-none"
                  value={editingRef[refKey]}
                  onChange={e => setEditingRef(prev => ({ ...prev, [refKey]: e.target.value.toUpperCase() }))}
                  onBlur={() => handleRenameGroupCommit(refKey)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') handleRenameGroupCommit(refKey);
                    if (e.key === 'Escape') setEditingRef(prev => { const n = { ...prev }; delete n[refKey]; return n; });
                  }}
                />
              ) : (
                <button type="button" onClick={() => toggleGroup(refKey)} className="flex items-center gap-2 flex-1 min-w-0 text-left">
                  <span className="font-mono font-bold text-white text-sm tracking-widest shrink-0">{refKey}</span>
                  <span className="text-white/60 text-xs truncate hidden sm:block">{desc.split('\n')[0]}</span>
                  <span className="text-white/50 text-xs shrink-0">{groupLineas.length} {groupLineas.length === 1 ? 'pieza' : 'piezas'}</span>
                  {pendingCount > 0 && (
                    <span className="shrink-0 bg-amber-400 text-amber-900 text-xs font-semibold px-2 py-0.5 rounded-full">
                      {pendingCount} pendiente{pendingCount > 1 ? 's' : ''}
                    </span>
                  )}
                </button>
              )}

              <div className="flex items-center gap-1 shrink-0 ml-auto">
                {hasDiscount && (
                  <span className="text-white/70 text-xs flex items-center gap-0.5 mr-1">
                    <Tag className="w-3 h-3" />−{groupDiscounts[refKey]}%
                  </span>
                )}
                <span className="text-white font-bold tabular-nums text-sm mr-1">
                  {getEffectiveSubtotal(refKey, grpSubtotal).toFixed(2)} €
                </span>
                <button type="button" title="Renombrar" onClick={() => handleRenameGroupStart(refKey)}
                  className="p-1 rounded text-white/50 hover:text-white hover:bg-white/20 transition-colors">
                  <PenLine className="w-3.5 h-3.5" />
                </button>
                <button type="button" title="Añadir pieza" onClick={() => handleAddLineToGroup(refKey)}
                  className="p-1 rounded text-white/50 hover:text-white hover:bg-white/20 transition-colors">
                  <Plus className="w-3.5 h-3.5" />
                </button>
                <button type="button" title="Eliminar grupo"
                  onClick={() => { if (confirm(`¿Eliminar el grupo "${refKey}"?`)) handleDeleteGroup(refKey); }}
                  className="p-1 rounded text-white/50 hover:text-red-300 hover:bg-white/20 transition-colors">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
                <button type="button" onClick={() => toggleGroup(refKey)}
                  className="p-1 rounded text-white/50 hover:text-white transition-colors">
                  {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* ── Expanded content ── */}
            {isOpen && (
              <>
                {/* Description with AI generation button */}
                <div className="px-3 pt-2.5 pb-2 bg-gray-50 border-t border-gray-100">
                  <div className="relative">
                    <textarea
                      className="w-full text-xs text-gray-600 bg-white border border-gray-200 rounded-lg px-3 py-2.5 pr-9 focus:outline-none focus:ring-1 focus:ring-gray-300 resize-none leading-relaxed placeholder:text-gray-300"
                      rows={desc ? Math.max(4, desc.split('\n').length) : 4}
                      placeholder={"Descripción del módulo para el presupuesto…\n\nEj: Suministro e instalación de armario empotrado\nsegún plano, 3 puertas batientes, 300×240×60 cm.\nMelamina blanco mate 18mm, bisagras Blum."}
                      value={desc}
                      onChange={e => setDescriptions(prev => ({ ...prev, [refKey]: e.target.value }))}
                    />
                    {estimateId && (
                      <button
                        type="button"
                        title="Generar descripción con IA"
                        disabled={generatingDesc[refKey]}
                        onClick={() => generateDescription(refKey, groupLineas)}
                        className="absolute top-2 right-2 p-1 rounded-md text-gray-300 hover:text-violet-600 hover:bg-violet-50 transition-all disabled:opacity-40"
                      >
                        {generatingDesc[refKey]
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Sparkles className="w-3.5 h-3.5" />}
                      </button>
                    )}
                  </div>
                </div>

                {/* Line items table */}
                <div className="overflow-x-auto border-t border-gray-100">
                  <table className="w-full text-sm text-left">
                    <thead className="bg-gray-50 text-gray-400 text-xs border-b border-gray-100">
                      <tr>
                        <th className="px-2.5 py-1.5 w-20 font-medium">Código</th>
                        <th className="px-2.5 py-1.5 font-medium">Descripción</th>
                        <th className="px-2.5 py-1.5 w-16 text-center font-medium">Cant.</th>
                        <th className="px-2.5 py-1.5 w-28 text-right font-medium">P. Unit. €</th>
                        <th className="px-2.5 py-1.5 w-24 text-right font-medium">Subtotal €</th>
                        <th className="px-1 py-1.5 w-7" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {groupLineas.map((linea, localIdx) => {
                        const globalIdx = indices[localIdx];
                        return (
                          <tr key={globalIdx}
                            className={`group/row transition-colors ${linea.precio_pendiente ? 'bg-amber-50/30' : 'bg-white hover:bg-gray-50'}`}>

                            <td className="px-2.5 py-1.5 align-top">
                              <span className={`inline-block font-mono text-xs px-1.5 py-0.5 rounded border ${accent.badge}`}>
                                {linea.codigo || '—'}
                              </span>
                            </td>

                            <td className="px-2.5 py-1.5 align-top">
                              <AutoResizeTextarea
                                className="w-full border border-transparent hover:border-gray-200 rounded px-1 py-1 text-sm text-gray-900 focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 transition-colors bg-transparent leading-snug"
                                value={linea.descripcion}
                                onChange={e => handleLineChange(globalIdx, 'descripcion', e.target.value)}
                              />
                              {linea.precio_pendiente && (
                                <span className="inline-block mt-0.5 text-xs font-medium text-amber-600 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                                  Sin precio
                                </span>
                              )}
                            </td>

                            <td className="px-2.5 py-1.5 align-top">
                              <input type="number" min="1"
                                className="w-full border border-transparent hover:border-gray-200 rounded px-1 py-1 text-center text-sm focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 bg-transparent transition-colors"
                                value={linea.cantidad}
                                onChange={e => handleLineChange(globalIdx, 'cantidad', parseFloat(e.target.value) || 0)} />
                            </td>

                            <td className="px-2.5 py-1.5 align-top">
                              <div className="flex items-center gap-1 justify-end">
                                {changedIndices.has(globalIdx) && (
                                  <span title="Precio corregido" className="flex items-center gap-0.5 text-emerald-600 text-xs shrink-0">
                                    <CheckCircle2 className="w-3.5 h-3.5" />
                                  </span>
                                )}
                                <input type="number" step="0.01" min="0"
                                  className={`w-24 border rounded px-1.5 py-1 text-right text-sm transition-colors focus:ring-1 focus:bg-white ${
                                    changedIndices.has(globalIdx)
                                      ? 'border-emerald-300 focus:ring-emerald-400 bg-emerald-50/40'
                                      : linea.precio_pendiente
                                        ? 'border-amber-300 focus:ring-amber-400 bg-amber-50/40'
                                        : 'border-transparent hover:border-gray-200 focus:border-blue-400 focus:ring-blue-400 bg-transparent'
                                  }`}
                                  value={linea.precio_unitario}
                                  onChange={e => handleLineChange(globalIdx, 'precio_unitario', parseFloat(e.target.value) || 0)} />
                              </div>
                            </td>

                            <td className="px-2.5 py-1.5 text-right align-top">
                              <span className="inline-block py-1 tabular-nums text-gray-900 font-medium">
                                {(linea.subtotal ?? 0).toFixed(2)}
                              </span>
                            </td>

                            <td className="px-1 py-1.5 align-top">
                              <button type="button" title="Eliminar" onClick={() => handleDeleteLine(globalIdx)}
                                className="opacity-0 group-hover/row:opacity-100 p-0.5 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-all">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Group footer: actions + discount + total */}
                <div className="border-t border-gray-100 bg-gray-50">

                  {/* Action row */}
                  <div className="px-3 py-2 flex items-center gap-3 border-b border-gray-100">
                    <button type="button" onClick={() => handleAddLineToGroup(refKey)}
                      className="flex items-center gap-1 text-xs text-gray-400 hover:text-blue-600 transition-colors font-medium">
                      <Plus className="w-3.5 h-3.5" /> Añadir pieza
                    </button>
                    {clienteId && (
                      <button type="button" onClick={() => setKbSearchRefKey(refKey)}
                        className="flex items-center gap-1 text-xs text-gray-400 hover:text-violet-600 transition-colors font-medium">
                        <Search className="w-3.5 h-3.5" /> Buscar en KB
                      </button>
                    )}

                    {/* Discount toggle */}
                    <div className="ml-auto flex items-center gap-2">
                      {!hasDiscount ? (
                        <button type="button"
                          onClick={() => setGroupDiscounts(prev => ({ ...prev, [refKey]: 10 }))}
                          className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors">
                          <Tag className="w-3.5 h-3.5" /> Descuento
                        </button>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <Tag className="w-3.5 h-3.5 text-gray-400" />
                          {PRESET_DISCOUNTS.map(pct => (
                            <button key={pct} type="button"
                              onClick={() => setGroupDiscounts(prev => ({ ...prev, [refKey]: pct }))}
                              className={`text-xs px-1.5 py-0.5 rounded border transition-colors ${
                                groupDiscounts[refKey] === pct
                                  ? 'bg-gray-900 text-white border-gray-900'
                                  : 'bg-white text-gray-500 border-gray-200 hover:border-gray-400'
                              }`}
                            >
                              {pct}%
                            </button>
                          ))}
                          <input type="number" min="0" max="100" step="0.5"
                            className="w-12 text-xs border border-gray-200 rounded px-1.5 py-0.5 text-center focus:outline-none focus:ring-1 focus:ring-blue-400"
                            value={groupDiscounts[refKey]}
                            onChange={e => {
                              const v = parseFloat(e.target.value);
                              if (!isNaN(v) && v >= 0 && v <= 100) setGroupDiscounts(prev => ({ ...prev, [refKey]: v }));
                            }}
                          />
                          <span className="text-xs text-gray-400">%</span>
                          <button type="button" onClick={() => setGroupDiscounts(prev => { const n = { ...prev }; delete n[refKey]; return n; })}
                            className="text-xs text-gray-400 hover:text-red-500 ml-0.5">×</button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Subtotal row */}
                  <div className="px-3 py-2 flex items-center justify-between text-xs">
                    <span className="text-gray-400 font-mono">{refKey}</span>
                    <div className="flex items-center gap-3">
                      {pendingCount > 0 && (
                        <span className="text-amber-500">{pendingCount} sin precio</span>
                      )}
                      {hasDiscount && (
                        <span className="text-gray-400 line-through tabular-nums">{grpSubtotal.toFixed(2)} €</span>
                      )}
                      <span className="font-bold text-gray-900 tabular-nums">
                        {getEffectiveSubtotal(refKey, grpSubtotal).toFixed(2)} €
                      </span>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        );
      })}

      {/* Add new group */}
      <div className="pt-1">
        {newGroupInput === null ? (
          <button type="button" onClick={() => setNewGroupInput('')}
            className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-600 border border-dashed border-gray-200 hover:border-gray-400 rounded-lg px-4 py-2 w-full justify-center transition-colors">
            <Plus className="w-4 h-4" /> Nuevo grupo
          </button>
        ) : (
          <div className="flex items-center gap-2 border border-blue-300 rounded-lg px-3 py-2 bg-blue-50">
            <Plus className="w-4 h-4 text-blue-500 shrink-0" />
            <input autoFocus type="text"
              className="flex-1 bg-transparent text-sm font-mono font-bold uppercase tracking-widest text-gray-800 focus:outline-none placeholder:font-normal placeholder:tracking-normal placeholder:text-gray-400"
              placeholder="Código del grupo (ej: A07)"
              value={newGroupInput}
              onChange={e => setNewGroupInput(e.target.value.toUpperCase())}
              onKeyDown={e => { if (e.key === 'Enter') handleAddGroup(); if (e.key === 'Escape') setNewGroupInput(null); }}
            />
            <button type="button" onClick={handleAddGroup} className="text-xs font-semibold text-blue-600 hover:text-blue-800 shrink-0">Crear</button>
            <button type="button" onClick={() => setNewGroupInput(null)} className="text-xs text-gray-400 hover:text-gray-600 shrink-0">Cancelar</button>
          </div>
        )}
      </div>

      {/* Global totals */}
      {refKeys.length > 0 && (
        <div className="border-t border-gray-200 pt-3 mt-2">
          <div className="flex flex-col gap-1 items-end text-sm">
            {Object.keys(groupDiscounts).length > 0 && (
              <div className="flex gap-6 text-gray-400 text-xs">
                <span>Subtotal sin descuentos</span>
                <span className="tabular-nums line-through w-24 text-right">{(subtotal ?? 0).toFixed(2)} €</span>
              </div>
            )}
            <div className="flex gap-6 text-gray-500">
              <span>Subtotal</span>
              <span className="tabular-nums w-24 text-right">{effectiveSubtotal.toFixed(2)} €</span>
            </div>
            <div className="flex gap-6 text-gray-500">
              <span>IVA (21%)</span>
              <span className="tabular-nums w-24 text-right">{effectiveIva.toFixed(2)} €</span>
            </div>
            <div className="flex gap-6 font-bold text-gray-900 text-base border-t border-gray-200 pt-2 mt-1">
              <span>Total</span>
              <span className="tabular-nums w-24 text-right">{effectiveTotal.toFixed(2)} €</span>
            </div>
          </div>

          {pendingCorrections.length > 0 && onSavePriceFeedback && (
            <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-emerald-800">
                  {pendingCorrections.length} precio{pendingCorrections.length > 1 ? 's' : ''} corregido{pendingCorrections.length > 1 ? 's' : ''}
                </p>
                <p className="text-xs text-emerald-600 mt-0.5">
                  Guarda las correcciones para mejorar futuros presupuestos.
                </p>
              </div>
              <button type="button" disabled={isSavingFeedback}
                onClick={() => onSavePriceFeedback(pendingCorrections)}
                className="flex items-center gap-1.5 shrink-0 rounded bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-60 transition-colors">
                <BrainCircuit className="w-4 h-4" />
                {isSavingFeedback ? 'Guardando…' : 'Guardar y aprender'}
              </button>
            </div>
          )}
        </div>
      )}

      {kbSearchRefKey !== null && clienteId && (
        <KbSearchModal
          clienteId={clienteId}
          onAdd={(linea) => onChange([...lineas, { ...linea, ref: kbSearchRefKey }])}
          onClose={() => setKbSearchRefKey(null)}
        />
      )}
    </div>
  );
}
