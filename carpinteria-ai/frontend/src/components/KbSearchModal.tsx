"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { knowledgeApi } from "@/lib/knowledge-api";
import { PrecioResponse } from "@/types/knowledge";
import { LineaPresupuesto } from "@/types/estimate";
import { Search, Plus, X, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface KbSearchModalProps {
  clienteId: string;
  onAdd: (linea: LineaPresupuesto) => void;
  onClose: () => void;
}

let _lineCounter = 0;
function nextKbCode() {
  _lineCounter += 1;
  return `KB-${String(_lineCounter).padStart(3, "0")}`;
}

export default function KbSearchModal({ clienteId: _clienteId, onAdd, onClose }: KbSearchModalProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PrecioResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return; }
    setLoading(true);
    try {
      const data = await knowledgeApi.getPrecios(0, 30, true, q, undefined);
      setResults(data);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const q = e.target.value;
    setQuery(q);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => search(q), 350);
  };

  const handleAdd = (item: PrecioResponse) => {
    const qty = quantities[item.id] || 1;
    const precio = parseFloat(String(item.metadatos.precio_unitario)) || 0;
    const linea: LineaPresupuesto = {
      codigo: nextKbCode(),
      ref: "KB",
      descripcion: item.metadatos.material || item.documento,
      cantidad: qty,
      precio_unitario: precio,
      subtotal: parseFloat((precio * qty).toFixed(2)),
      precio_pendiente: false,
    };
    onAdd(linea);
    // keep modal open for adding more items
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-2xl flex flex-col max-h-[80vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b">
          <h3 className="font-semibold text-gray-800">Añadir de base de precios</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search */}
        <div className="px-5 py-3 border-b">
          <div className="flex items-center gap-2 border rounded-lg px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500">
            <Search className="w-4 h-4 text-gray-400 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Buscar material, descripción…"
              className="flex-1 outline-none text-sm"
              value={query}
              onChange={handleQueryChange}
            />
            {loading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
          </div>
        </div>

        {/* Results */}
        <div className="overflow-y-auto flex-1">
          {!query.trim() && (
            <p className="text-center text-sm text-gray-400 py-10">Escribe para buscar en la base de precios</p>
          )}
          {query.trim() && !loading && results.length === 0 && (
            <p className="text-center text-sm text-gray-400 py-10">Sin resultados</p>
          )}
          {results.map((item) => {
            const precio = parseFloat(String(item.metadatos.precio_unitario)) || 0;
            const qty = quantities[item.id] || 1;
            return (
              <div
                key={item.id}
                className="flex items-center gap-3 px-5 py-3 border-b last:border-0 hover:bg-gray-50"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {item.metadatos.material || item.documento}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {item.metadatos.categoria} · {item.metadatos.cliente}
                  </p>
                </div>
                <span className="text-sm font-semibold text-gray-700 shrink-0">
                  {precio.toFixed(2)} € / {item.metadatos.unidad}
                </span>
                <input
                  type="number"
                  min={1}
                  value={qty}
                  onChange={(e) => setQuantities((q) => ({ ...q, [item.id]: Math.max(1, parseInt(e.target.value) || 1) }))}
                  className="w-14 border rounded px-2 py-1 text-sm text-center focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
                <Button
                  size="sm"
                  onClick={() => handleAdd(item)}
                  className="gap-1 bg-blue-600 hover:bg-blue-700 text-white shrink-0"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Añadir
                </Button>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
