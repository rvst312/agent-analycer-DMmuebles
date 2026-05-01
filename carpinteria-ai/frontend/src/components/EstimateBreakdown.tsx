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
  className 
}: { 
  value: string, 
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void, 
  className?: string 
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
    }
  }, [value]);

  return (
    <textarea
      ref={textareaRef}
      value={value}
      onChange={onChange}
      className={`resize-none overflow-hidden ${className}`}
      rows={1}
    />
  );
};

export default function EstimateBreakdown({ lineas, subtotal, iva, total, onChange }: EstimateBreakdownProps) {
  const handleLineChange = (index: number, field: keyof LineaPresupuesto, value: number | string) => {
    const newLineas = [...lineas];
    const updatedLine = { ...newLineas[index], [field]: value };
    if (field !== 'descripcion') {
      updatedLine.subtotal = Number((updatedLine.cantidad * Number(updatedLine.precio_unitario)).toFixed(2));
    }
    if (field === 'precio_unitario' && updatedLine.precio_pendiente && (value as number) > 0) {
      updatedLine.precio_pendiente = false;
    }
    newLineas[index] = updatedLine;
    onChange(newLineas);
  };

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm flex flex-col h-full">
      <h2 className="text-xl font-semibold mb-4">Desglose del Presupuesto</h2>
      
      <div className="overflow-x-auto flex-1">
        <table className="w-full text-sm text-left">
          <thead className="bg-gray-50 text-gray-700">
            <tr>
              <th className="px-4 py-3">Descripción</th>
              <th className="px-4 py-3 w-24">Cantidad</th>
              <th className="px-4 py-3 w-32">Precio Un. (€)</th>
              <th className="px-4 py-3 text-right">Subtotal (€)</th>
            </tr>
          </thead>
          <tbody>
            {lineas.map((linea, idx) => (
              <tr 
                key={idx} 
                className={`border-b group transition-colors ${linea.precio_pendiente ? 'bg-yellow-50/50 hover:bg-yellow-50' : 'bg-white hover:bg-gray-50'}`}
              >
                <td className="px-4 py-3 align-top">
                  <AutoResizeTextarea
                    className="w-full border border-transparent hover:border-gray-200 rounded p-2 text-sm font-medium text-gray-900 focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 transition-colors bg-transparent leading-relaxed"
                    value={linea.descripcion}
                    onChange={(e) => handleLineChange(idx, 'descripcion', e.target.value)}
                  />
                  {linea.precio_pendiente && (
                    <div className="text-xs text-yellow-600 mt-1 px-2 font-semibold">
                      ⚠️ Precio pendiente
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 align-top">
                  <input 
                    type="number" 
                    min="1"
                    className="w-full border border-transparent hover:border-gray-200 rounded p-2 text-center text-sm focus:bg-white focus:ring-1 focus:ring-blue-400 focus:border-blue-400 bg-transparent transition-colors"
                    value={linea.cantidad}
                    onChange={(e) => handleLineChange(idx, 'cantidad', parseFloat(e.target.value) || 0)}
                  />
                </td>
                <td className="px-4 py-3 align-top">
                  <input 
                    type="number" 
                    step="0.01"
                    min="0"
                    className={`w-full border rounded p-2 text-right text-sm transition-colors focus:ring-1 focus:bg-white ${linea.precio_pendiente ? 'border-yellow-400 focus:ring-yellow-400 bg-yellow-50/50' : 'border-transparent hover:border-gray-200 focus:border-blue-400 focus:ring-blue-400 bg-transparent'}`}
                    value={linea.precio_unitario}
                    onChange={(e) => handleLineChange(idx, 'precio_unitario', parseFloat(e.target.value) || 0)}
                  />
                </td>
                <td className="px-4 py-3 text-right font-medium align-top">
                  <div className="py-2 text-gray-900">
                    {(linea.subtotal ?? 0).toFixed(2)}
                  </div>
                </td>
              </tr>
            ))}
            {lineas.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                  No hay líneas en este presupuesto.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-6 border-t pt-4">
        <div className="flex justify-end mb-2">
          <span className="text-gray-600 mr-4">Subtotal:</span>
          <span className="font-medium w-24 text-right">{(subtotal ?? 0).toFixed(2)} €</span>
        </div>
        <div className="flex justify-end mb-2">
          <span className="text-gray-600 mr-4">IVA (21%):</span>
          <span className="font-medium w-24 text-right">{(iva ?? 0).toFixed(2)} €</span>
        </div>
        <div className="flex justify-end text-lg font-bold">
          <span className="mr-4">Total:</span>
          <span className="w-24 text-right">{(total ?? 0).toFixed(2)} €</span>
        </div>
      </div>
    </div>
  );
}