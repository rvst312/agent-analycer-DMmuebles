import React, { useState } from 'react';
import { Loader2, Plus, X } from 'lucide-react';
import { Button } from './ui/button';
import { toast } from 'sonner';

import { PrecioResponse } from '@/types/knowledge';

interface AddPriceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (precio: Omit<PrecioResponse, 'id'>) => Promise<void>;
}

export default function AddPriceModal({ isOpen, onClose, onAdd }: AddPriceModalProps) {
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    material: '',
    cliente: '',
    precio_unitario: '',
    unidad: '',
    categoria: ''
  });

  if (!isOpen) return null;

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.material || !formData.cliente || !formData.precio_unitario || !formData.unidad || !formData.categoria) {
      toast.error('Por favor, rellena todos los campos obligatorios');
      return;
    }

    const numValue = parseFloat(formData.precio_unitario);
    if (isNaN(numValue) || numValue <= 0) {
      toast.error('El precio debe ser un número válido mayor que 0');
      return;
    }

    setLoading(true);
    try {
      const payload: Omit<PrecioResponse, 'id'> = {
        documento: `${formData.material} para ${formData.categoria}`,
        metadatos: {
          ...formData,
          precio_unitario: numValue,
          version: '1.0',
          activo: true
        }
      };
      
      await onAdd(payload);
      setFormData({
        material: '',
        cliente: '',
        precio_unitario: '',
        unidad: '',
        categoria: ''
      });
      onClose();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md overflow-hidden flex flex-col">
        <div className="px-6 py-4 border-b flex justify-between items-center bg-gray-50">
          <h3 className="text-lg font-semibold text-gray-900">Añadir Nuevo Precio</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <form onSubmit={handleSubmit} className="p-6 flex flex-col gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Nombre / Material *</label>
            <input 
              type="text" 
              name="material"
              value={formData.material}
              onChange={handleChange}
              className="w-full border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Ej. Madera de roble"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Categoría *</label>
            <select 
              name="categoria"
              value={formData.categoria}
              onChange={handleChange}
              className="w-full border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Selecciona una categoría...</option>
              <option value="materia_prima">Materia Prima</option>
              <option value="herrajes">Herrajes</option>
              <option value="acabados">Acabados</option>
              <option value="mano_obra">Mano de Obra</option>
              <option value="otros">Otros</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Cliente *</label>
            <input 
              type="text" 
              name="cliente"
              value={formData.cliente}
              onChange={handleChange}
              className="w-full border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Ej. general o cliente_123"
            />
          </div>
          
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Precio Unitario (€) *</label>
              <input 
                type="number" 
                name="precio_unitario"
                step="0.01"
                value={formData.precio_unitario}
                onChange={handleChange}
                className="w-full border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="0.00"
              />
            </div>
            
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Unidad *</label>
              <select 
                name="unidad"
                value={formData.unidad}
                onChange={handleChange}
                className="w-full border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Selecciona...</option>
                <option value="m2">Metro cuadrado (m²)</option>
                <option value="m">Metro lineal (m)</option>
                <option value="unidad">Unidad (ud)</option>
                <option value="litro">Litro (l)</option>
                <option value="hora">Hora (h)</option>
              </select>
            </div>
          </div>
          
          <div className="mt-6 flex justify-end gap-3">
            <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
              Cancelar
            </Button>
            <Button type="submit" disabled={loading} className="bg-blue-600 hover:bg-blue-700 text-white">
              {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Plus className="w-4 h-4 mr-2" />}
              Guardar Precio
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}