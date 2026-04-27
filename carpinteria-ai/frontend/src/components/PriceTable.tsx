"use client";

import React, { useState } from 'react';
import { PrecioResponse } from '../types/knowledge';
import { Loader2, Edit2, Check, X } from 'lucide-react';

interface PriceTableProps {
  precios: PrecioResponse[];
  loading: boolean;
  onUpdatePrecio: (id: string, nuevoPrecio: number) => Promise<void>;
}

export default function PriceTable({ precios, loading, onUpdatePrecio }: PriceTableProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [isSaving, setIsSaving] = useState(false);

  const handleEditClick = (precio: PrecioResponse) => {
    setEditingId(precio.id);
    setEditValue(precio.metadatos.precio_unitario.toString());
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditValue('');
  };

  const handleSaveEdit = async (id: string) => {
    const numValue = parseFloat(editValue);
    if (isNaN(numValue) || numValue <= 0) {
      alert("Por favor ingresa un número válido");
      return;
    }
    
    setIsSaving(true);
    try {
      await onUpdatePrecio(id, numValue);
      setEditingId(null);
    } catch (err) {
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center p-8 border rounded-lg bg-white shadow-sm">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="border rounded-lg bg-white shadow-sm overflow-x-auto">
      <table className="w-full text-left whitespace-nowrap">
        <thead className="bg-gray-50 border-b">
          <tr>
            <th className="px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Material</th>
            <th className="px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Cliente</th>
            <th className="px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Precio Unitario</th>
            <th className="px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Unidad</th>
            <th className="px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Categoría</th>
            <th className="px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider">Versión</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {precios.length === 0 ? (
            <tr>
              <td className="px-6 py-4 text-center text-gray-500" colSpan={6}>
                No hay datos aún
              </td>
            </tr>
          ) : (
            precios.map((precio) => (
              <tr key={precio.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4 text-sm font-medium text-gray-900">
                  {precio.metadatos.material}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {precio.metadatos.cliente}
                </td>
                <td className="px-6 py-4 text-sm text-gray-900">
                  {editingId === precio.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.01"
                        className="w-24 px-2 py-1 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        disabled={isSaving}
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleSaveEdit(precio.id);
                          if (e.key === 'Escape') handleCancelEdit();
                        }}
                      />
                      <button
                        onClick={() => handleSaveEdit(precio.id)}
                        disabled={isSaving}
                        className="text-green-600 hover:text-green-800"
                      >
                        {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                      </button>
                      <button
                        onClick={handleCancelEdit}
                        disabled={isSaving}
                        className="text-red-600 hover:text-red-800"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <div 
                      className="flex items-center gap-2 cursor-pointer group"
                      onClick={() => handleEditClick(precio)}
                    >
                      <span>{precio.metadatos.precio_unitario.toFixed(2)} €</span>
                      <Edit2 className="w-3 h-3 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  )}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {precio.metadatos.unidad}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  {precio.metadatos.categoria}
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">
                  v{precio.metadatos.version}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
