"use client";

import React, { useState } from 'react';
import { PrecioResponse } from '../types/knowledge';
import { Loader2, Edit2, Check, X, Trash2 } from 'lucide-react';

interface PriceTableProps {
  precios: PrecioResponse[];
  loading: boolean;
  onUpdatePrecio: (id: string, nuevoPrecio: number) => Promise<void>;
  onDeletePrecio: (id: string) => Promise<void>;
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
}

export default function PriceTable({
  precios,
  loading,
  onUpdatePrecio,
  onDeletePrecio,
  selectedIds,
  onSelectionChange,
}: PriceTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [isSaving, setIsSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const allSelected = precios.length > 0 && precios.every(p => selectedIds.has(p.id));
  const someSelected = precios.some(p => selectedIds.has(p.id)) && !allSelected;

  const toggleAll = () => {
    const next = new Set(selectedIds);
    if (allSelected) { precios.forEach(p => next.delete(p.id)); }
    else { precios.forEach(p => next.add(p.id)); }
    onSelectionChange(next);
  };

  const toggleOne = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    onSelectionChange(next);
  };

  const handleSaveEdit = async (id: string) => {
    const numValue = parseFloat(editValue);
    if (isNaN(numValue) || numValue <= 0) { alert('Ingresa un número válido'); return; }
    setIsSaving(true);
    try {
      await onUpdatePrecio(id, numValue);
      setEditingId(null);
    } catch { /* handled by parent */ }
    finally { setIsSaving(false); }
  };

  const handleDeleteClick = async (id: string) => {
    if (!confirm('¿Eliminar este precio?')) return;
    setDeletingId(id);
    try { await onDeletePrecio(id); }
    catch { /* handled by parent */ }
    finally { setDeletingId(null); }
  };

  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl flex justify-center py-16">
        <Loader2 className="w-5 h-5 animate-spin text-gray-300" />
      </div>
    );
  }

  if (precios.length === 0) return null;

  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left whitespace-nowrap">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="px-4 py-3 w-10">
                <input
                  type="checkbox"
                  className="rounded border-gray-300 cursor-pointer accent-gray-900"
                  checked={allSelected}
                  ref={el => { if (el) el.indeterminate = someSelected; }}
                  onChange={toggleAll}
                  title="Seleccionar todo"
                />
              </th>
              <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Material</th>
              <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Categoría</th>
              <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Cliente</th>
              <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Precio / ud.</th>
              <th className="px-4 py-3 text-xs font-medium text-gray-400 uppercase tracking-wider">Unidad</th>
              <th className="px-4 py-3 w-10" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {precios.map((precio) => {
              const isSelected = selectedIds.has(precio.id);
              return (
                <tr key={precio.id}
                  className={`group/row transition-colors ${isSelected ? 'bg-gray-50' : 'bg-white hover:bg-gray-50/60'}`}>

                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      className="rounded border-gray-300 cursor-pointer accent-gray-900"
                      checked={isSelected}
                      onChange={() => toggleOne(precio.id)}
                    />
                  </td>

                  <td className="px-4 py-3 text-sm font-medium text-gray-900 max-w-xs">
                    <span className="block truncate">{precio.metadatos.material}</span>
                  </td>

                  <td className="px-4 py-3">
                    <span className="inline-block text-xs font-medium bg-gray-100 text-gray-600 rounded px-2 py-0.5">
                      {precio.metadatos.categoria}
                    </span>
                  </td>

                  <td className="px-4 py-3 text-sm text-gray-500">{precio.metadatos.cliente}</td>

                  <td className="px-4 py-3 text-sm text-gray-900">
                    {editingId === precio.id ? (
                      <div className="flex items-center gap-1.5">
                        <input
                          type="number" step="0.01"
                          className="w-24 px-2 py-1 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-gray-200"
                          value={editValue}
                          onChange={e => setEditValue(e.target.value)}
                          disabled={isSaving}
                          autoFocus
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleSaveEdit(precio.id);
                            if (e.key === 'Escape') { setEditingId(null); setEditValue(''); }
                          }}
                        />
                        <button onClick={() => handleSaveEdit(precio.id)} disabled={isSaving}
                          className="p-1 rounded text-emerald-600 hover:bg-emerald-50 transition-colors">
                          {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                        </button>
                        <button onClick={() => { setEditingId(null); setEditValue(''); }} disabled={isSaving}
                          className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 cursor-pointer group/edit"
                        onClick={() => { setEditingId(precio.id); setEditValue(precio.metadatos.precio_unitario.toString()); }}>
                        <span className="tabular-nums font-medium">{precio.metadatos.precio_unitario.toFixed(2)} €</span>
                        <Edit2 className="w-3 h-3 text-gray-300 opacity-0 group-hover/edit:opacity-100 transition-opacity" />
                      </div>
                    )}
                  </td>

                  <td className="px-4 py-3 text-sm text-gray-400">{precio.metadatos.unidad}</td>

                  <td className="px-4 py-3">
                    <button onClick={() => handleDeleteClick(precio.id)} disabled={deletingId === precio.id}
                      className="opacity-0 group-hover/row:opacity-100 p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-all">
                      {deletingId === precio.id
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <Trash2 className="w-3.5 h-3.5" />}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
