"use client";

import React, { useEffect, useState, useRef } from 'react';
import PriceTable from '@/components/PriceTable';
import { knowledgeApi } from '@/lib/knowledge-api';
import { PrecioResponse } from '@/types/knowledge';
import { toast } from 'sonner';
import { Upload, Loader2, Search, Filter } from 'lucide-react';
import { Button } from '@/components/ui/button';

type ApiError = { response?: { data?: { detail?: unknown } } };

function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as ApiError).response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join('; ');
  }
  if (typeof detail === 'string') return detail;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function KnowledgePage() {
  const [precios, setPrecios] = useState<PrecioResponse[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Filtros
  const [clienteFilter, setClienteFilter] = useState('');
  const [categoriaFilter, setCategoriaFilter] = useState('');
  
  // Importación
  const [isImporting, setIsImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Paginación
  const [skip, setSkip] = useState(0);
  const limit = 50;

  const fetchPrecios = async (currentSkip: number) => {
    try {
      setLoading(true);
      const data = await knowledgeApi.getPrecios(currentSkip, limit, true);
      if (currentSkip === 0) {
        setPrecios(data);
      } else {
        setPrecios(prev => [...prev, ...data]);
      }
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al cargar la base de precios'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPrecios(skip);
  }, [skip]);

  const handleUpdatePrecio = async (id: string, nuevoPrecio: number) => {
    try {
      await knowledgeApi.updatePrecio(id, { precio_unitario: nuevoPrecio });
      toast.success('Precio actualizado correctamente');
      setPrecios(prev => prev.map(p => 
        p.id === id 
          ? { ...p, metadatos: { ...p.metadatos, precio_unitario: nuevoPrecio } } 
          : p
      ));
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al actualizar el precio'));
      throw err;
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsImporting(true);
      const response = await knowledgeApi.importCsv(file);
      
      if (response.errores && response.errores.length > 0) {
        toast.warning(`Importación completada con errores: ${response.procesadas} procesadas, ${response.errores.length} errores. Revisa la consola para más detalles.`);
        console.warn('Errores de importación:', response.errores);
      } else {
        toast.success(`Importación exitosa: ${response.procesadas} filas procesadas.`);
      }
      
      // Recargar datos
      setSkip(0);
      await fetchPrecios(0);
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al importar el archivo CSV'));
    } finally {
      setIsImporting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  // Aplicar filtros en el cliente (ya que el endpoint no tiene parámetros de filtro actualmente,
  // y solo trae los primeros 100 por defecto. Para un caso real, deberíamos implementar filtros en backend)
  const preciosFiltrados = precios.filter(p => {
    const matchCliente = p.metadatos.cliente.toLowerCase().includes(clienteFilter.toLowerCase());
    const matchCategoria = p.metadatos.categoria.toLowerCase().includes(categoriaFilter.toLowerCase());
    return matchCliente && matchCategoria;
  });

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Base de Precios</h1>
          <p className="text-gray-500 mt-1">Gestión del conocimiento RAG para materiales y precios</p>
        </div>
        
        <div className="flex items-center gap-3">
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            accept=".csv" 
            onChange={handleFileChange} 
          />
          <Button 
            onClick={handleImportClick} 
            disabled={isImporting}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700"
          >
            {isImporting ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Upload className="w-4 h-4" />
            )}
            {isImporting ? 'Importando...' : 'Importar CSV'}
          </Button>
        </div>
      </div>

      {isImporting && (
        <div className="mb-6 p-4 border rounded-lg bg-blue-50 border-blue-100 flex items-center gap-3 text-blue-800">
          <Loader2 className="w-5 h-5 animate-spin" />
          <div className="flex-1">
            <p className="font-medium text-sm">Procesando archivo CSV...</p>
            <div className="w-full bg-blue-200 rounded-full h-1.5 mt-2 overflow-hidden">
              <div className="bg-blue-600 h-1.5 rounded-full w-full animate-pulse"></div>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white p-4 border rounded-lg shadow-sm mb-6 flex flex-col sm:flex-row gap-4">
        <div className="flex-1 flex items-center gap-2 border rounded-md px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500">
          <Search className="w-4 h-4 text-gray-400" />
          <input 
            type="text" 
            placeholder="Filtrar por cliente..." 
            className="flex-1 outline-none text-sm"
            value={clienteFilter}
            onChange={(e) => setClienteFilter(e.target.value)}
          />
        </div>
        <div className="flex-1 flex items-center gap-2 border rounded-md px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500">
          <Filter className="w-4 h-4 text-gray-400" />
          <input 
            type="text" 
            placeholder="Filtrar por categoría..." 
            className="flex-1 outline-none text-sm"
            value={categoriaFilter}
            onChange={(e) => setCategoriaFilter(e.target.value)}
          />
        </div>
      </div>

      <PriceTable 
        precios={preciosFiltrados} 
        loading={loading && skip === 0} 
        onUpdatePrecio={handleUpdatePrecio} 
      />
      
      {!loading && precios.length > 0 && precios.length % limit === 0 && (
        <div className="flex justify-center mt-6">
          <Button 
            variant="outline" 
            onClick={() => setSkip(prev => prev + limit)}
            disabled={loading}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
            Cargar más
          </Button>
        </div>
      )}

      {!loading && precios.length > 0 && preciosFiltrados.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No hay resultados que coincidan con los filtros actuales.
        </div>
      )}
    </div>
  );
}
