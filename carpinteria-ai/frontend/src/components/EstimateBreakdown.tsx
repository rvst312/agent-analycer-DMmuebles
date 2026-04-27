"use client";

import React from 'react';
import { LineaPresupuesto } from '@/types/estimate';

interface EstimateBreakdownProps {
  lineas: LineaPresupuesto[];
  subtotal: number;
  iva: number;
  total: number;
  onChange: (newLineas: LineaPresupuesto[]) => void;
}

export default function EstimateBreakdown({ lineas, subtotal, iva, total, onChange }: EstimateBreakdownProps) {
  const handleLineChange = (index: number, field: keyof LineaPresupuesto, value: number) => {
    const newLineas = [...lineas];
    const updatedLine = { ...newLineas[index], [field]: value };
    // Recalculate subtotal for the line
    updatedLine.subtotal = updatedLine.cantidad * updatedLine.precio_unitario;
    
    // Si editamos el precio unitario y estaba pendiente, lo marcamos como resuelto
    if (field === 'precio_unitario' && updatedLine.precio_pendiente && value > 0) {
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
                className={`border-b ${linea.precio_pendiente ? 'bg-yellow-50' : 'bg-white'}`}
              >
                <td className="px-4 py-3 font-medium text-gray-900">
                  {linea.descripcion}
                  {linea.precio_pendiente && (
                    <div className="text-xs text-yellow-600 mt-1 font-semibold">
                      ⚠️ Precio pendiente
                    </div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <input 
                    type="number" 
                    min="1"
                    className="w-full border rounded p-1 text-center"
                    value={linea.cantidad}
                    onChange={(e) => handleLineChange(idx, 'cantidad', parseFloat(e.target.value) || 0)}
                  />
                </td>
                <td className="px-4 py-3">
                  <input 
                    type="number" 
                    step="0.01"
                    min="0"
                    className={`w-full border rounded p-1 text-right ${linea.precio_pendiente ? 'border-yellow-400 focus:ring-yellow-400' : ''}`}
                    value={linea.precio_unitario}
                    onChange={(e) => handleLineChange(idx, 'precio_unitario', parseFloat(e.target.value) || 0)}
                  />
                </td>
                <td className="px-4 py-3 text-right font-medium">
                  {linea.subtotal.toFixed(2)}
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
          <span className="font-medium w-24 text-right">{subtotal.toFixed(2)} €</span>
        </div>
        <div className="flex justify-end mb-2">
          <span className="text-gray-600 mr-4">IVA (21%):</span>
          <span className="font-medium w-24 text-right">{iva.toFixed(2)} €</span>
        </div>
        <div className="flex justify-end text-lg font-bold">
          <span className="mr-4">Total:</span>
          <span className="w-24 text-right">{total.toFixed(2)} €</span>
        </div>
      </div>
    </div>
  );
}