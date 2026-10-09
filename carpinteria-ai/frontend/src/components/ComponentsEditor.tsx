"use client";

import React, { useState } from "react";
import { ComponenteArmario } from "@/types/estimate";
import { Button } from "@/components/ui/button";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { authHeaders } from "@/lib/auth";

const TIPOS = ["tablero", "puerta", "cajon", "herraje", "barra", "estante", "armario", "otro"];

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Props {
  estimateId: string;
  originalComponents: ComponenteArmario[];
  onClose: () => void;
}

function emptyComponent(): ComponenteArmario {
  return { tipo: "tablero", material: "", acabado: "", ancho_cm: 0, largo_cm: 0, cantidad: 1 };
}

export default function ComponentsEditor({ estimateId, originalComponents, onClose }: Props) {
  const [components, setComponents] = useState<ComponenteArmario[]>(
    originalComponents.map(c => ({ ...c }))
  );
  const [isSaving, setIsSaving] = useState(false);

  const handleChange = (idx: number, field: keyof ComponenteArmario, value: string | number) => {
    setComponents(prev => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const addRow = () => setComponents(prev => [...prev, emptyComponent()]);

  const removeRow = (idx: number) => setComponents(prev => prev.filter((_, i) => i !== idx));

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const res = await fetch(`${BASE_URL}/estimates/${estimateId}/learn-components`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          componentes_originales: originalComponents,
          componentes_corregidos: components,
        }),
      });
      if (!res.ok) throw new Error(`Error ${res.status}`);
      toast.success("Correcciones guardadas. El agente aprenderá de este ejemplo.");
      onClose();
    } catch (err) {
      toast.error("Error al guardar las correcciones.");
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-gray-500">
        Corrige los componentes detectados. Los cambios se usarán como ejemplos para mejorar futuros análisis de planos similares.
      </p>

      <div className="overflow-x-auto rounded border border-gray-200">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 text-gray-600">
              <th className="px-2 py-2 text-left font-medium border-b">Tipo</th>
              <th className="px-2 py-2 text-left font-medium border-b">Material</th>
              <th className="px-2 py-2 text-left font-medium border-b">Acabado</th>
              <th className="px-2 py-2 text-right font-medium border-b w-20">Ancho cm</th>
              <th className="px-2 py-2 text-right font-medium border-b w-20">Largo cm</th>
              <th className="px-2 py-2 text-right font-medium border-b w-14">Cant.</th>
              <th className="px-2 py-2 text-left font-medium border-b">Notas</th>
              <th className="px-2 py-2 border-b w-8" />
            </tr>
          </thead>
          <tbody>
            {components.map((comp, idx) => (
              <tr key={idx} className="border-b last:border-0 hover:bg-gray-50">
                <td className="px-1 py-1">
                  <select
                    className="w-full text-xs border rounded px-1 py-1 bg-white"
                    value={comp.tipo}
                    onChange={e => handleChange(idx, "tipo", e.target.value)}
                  >
                    {TIPOS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </td>
                <td className="px-1 py-1">
                  <input
                    className="w-full text-xs border rounded px-1 py-1"
                    value={comp.material}
                    onChange={e => handleChange(idx, "material", e.target.value)}
                  />
                </td>
                <td className="px-1 py-1">
                  <input
                    className="w-full text-xs border rounded px-1 py-1"
                    value={comp.acabado}
                    onChange={e => handleChange(idx, "acabado", e.target.value)}
                  />
                </td>
                <td className="px-1 py-1">
                  <input
                    type="number"
                    min="0"
                    step="0.5"
                    className="w-full text-xs border rounded px-1 py-1 text-right"
                    value={comp.ancho_cm}
                    onChange={e => handleChange(idx, "ancho_cm", parseFloat(e.target.value) || 0)}
                  />
                </td>
                <td className="px-1 py-1">
                  <input
                    type="number"
                    min="0"
                    step="0.5"
                    className="w-full text-xs border rounded px-1 py-1 text-right"
                    value={comp.largo_cm}
                    onChange={e => handleChange(idx, "largo_cm", parseFloat(e.target.value) || 0)}
                  />
                </td>
                <td className="px-1 py-1">
                  <input
                    type="number"
                    min="1"
                    className="w-full text-xs border rounded px-1 py-1 text-right"
                    value={comp.cantidad}
                    onChange={e => handleChange(idx, "cantidad", parseInt(e.target.value) || 1)}
                  />
                </td>
                <td className="px-1 py-1">
                  <input
                    className="w-full text-xs border rounded px-1 py-1"
                    value={comp.notas || ""}
                    placeholder="—"
                    onChange={e => handleChange(idx, "notas", e.target.value)}
                  />
                </td>
                <td className="px-1 py-1 text-center">
                  <button
                    onClick={() => removeRow(idx)}
                    className="text-gray-400 hover:text-red-500 transition-colors"
                    title="Eliminar fila"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        onClick={addRow}
        className="flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-800 self-start"
      >
        <Plus className="w-3.5 h-3.5" /> Añadir componente
      </button>

      <div className="flex justify-end gap-3 pt-2 border-t">
        <Button variant="outline" onClick={onClose} disabled={isSaving}>
          Cancelar
        </Button>
        <Button onClick={handleSave} disabled={isSaving || components.length === 0}>
          {isSaving ? (
            <><Loader2 className="w-4 h-4 animate-spin mr-2" />Guardando...</>
          ) : (
            "Guardar correcciones"
          )}
        </Button>
      </div>
    </div>
  );
}
