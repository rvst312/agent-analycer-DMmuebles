"use client";

import React, { useEffect, useState, useRef, useCallback } from 'react';
import PriceTable from '@/components/PriceTable';
import AddPriceModal from '@/components/AddPriceModal';
import { knowledgeApi } from '@/lib/knowledge-api';
import { PrecioResponse } from '@/types/knowledge';
import { toast } from 'sonner';
import { Upload, Loader2, Search, Filter, Download, Plus, Trash2, FileDown } from 'lucide-react';
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
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  
  // Filtros
  const [searchFilter, setSearchFilter] = useState('');
  const [categoriaFilter, setCategoriaFilter] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debouncedCategoria, setDebouncedCategoria] = useState('');
  
  // Importación
  const [isImporting, setIsImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Selección masiva
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);

  // Paginación
  const [skip, setSkip] = useState(0);
  const limit = 50;

  // Debounce filtros
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchFilter);
      setDebouncedCategoria(categoriaFilter);
      setSkip(0); // resetear paginación al filtrar
    }, 500);
    return () => clearTimeout(timer);
  }, [searchFilter, categoriaFilter]);

  const fetchPrecios = useCallback(async (currentSkip: number, search: string, categoria: string) => {
    try {
      setLoading(true);
      const data = await knowledgeApi.getPrecios(currentSkip, limit, true, search, categoria);
      if (currentSkip === 0) {
        setPrecios(data);
      } else {
        setPrecios(prev => {
          // Avoid duplicates when quickly double clicking "load more"
          const existingIds = new Set(prev.map(p => p.id));
          const newData = data.filter(p => !existingIds.has(p.id));
          return [...prev, ...newData];
        });
      }
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al cargar la base de precios'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPrecios(skip, debouncedSearch, debouncedCategoria);
  }, [skip, debouncedSearch, debouncedCategoria, fetchPrecios]);

  // Limpiar selección al cambiar filtros
  useEffect(() => {
    setSelectedIds(new Set());
  }, [debouncedSearch, debouncedCategoria]);

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

  const handleAddPrecio = async (nuevoPrecio: Omit<PrecioResponse, 'id'>) => {
    try {
      await knowledgeApi.createPrecio(nuevoPrecio);
      toast.success('Precio añadido correctamente');
      setSkip(0);
      await fetchPrecios(0, debouncedSearch, debouncedCategoria);
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al añadir el precio'));
      throw err;
    }
  };

  const handleBulkDelete = async () => {
    const count = selectedIds.size;
    if (count === 0) return;
    if (!confirm(`¿Eliminar ${count} precio${count === 1 ? '' : 's'} seleccionado${count === 1 ? '' : 's'}? Esta acción no se puede deshacer.`)) return;
    setIsBulkDeleting(true);
    try {
      await knowledgeApi.bulkDelete(Array.from(selectedIds));
      toast.success(`${count} precio${count === 1 ? '' : 's'} eliminado${count === 1 ? '' : 's'} correctamente`);
      setSelectedIds(new Set());
      setSkip(0);
      await fetchPrecios(0, debouncedSearch, debouncedCategoria);
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al eliminar los precios seleccionados'));
    } finally {
      setIsBulkDeleting(false);
    }
  };

  const handleDeletePrecio = async (id: string) => {
    try {
      await knowledgeApi.deletePrecio(id);
      toast.success('Precio eliminado correctamente');
      setPrecios(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al eliminar el precio'));
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
      await fetchPrecios(0, debouncedSearch, debouncedCategoria);
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

  const handleDownloadTemplate = () => {
    const headers = 'id,material,cliente,precio_unitario,unidad,categoria,texto,version';
    const example = ',Tablero melamina blanco 19mm,general,28.50,m2,materia_prima,tablero para módulo armario,1.0';
    const csvContent = `${headers}\n${example}`;
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'plantilla_precios.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success('Plantilla descargada');
  };

  const handleExportCSV = () => {
    if (precios.length === 0) {
      toast.warning('No hay datos para exportar');
      return;
    }

    const headers = ['ID', 'Material', 'Categoría', 'Cliente', 'Precio Unitario', 'Unidad'];
    
    const rows = precios.map(p => [
      p.id,
      `"${p.metadatos.material.replace(/"/g, '""')}"`,
      `"${p.metadatos.categoria.replace(/"/g, '""')}"`,
      `"${p.metadatos.cliente.replace(/"/g, '""')}"`,
      p.metadatos.precio_unitario.toString(),
      `"${p.metadatos.unidad.replace(/"/g, '""')}"`
    ]);

    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `base_de_precios_${new Date().toISOString().split('T')[0]}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    toast.success('Archivo CSV exportado correctamente');
  };

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Base de Precios</h1>
          <p className="text-gray-500 mt-1">Gestión del conocimiento RAG para materiales y precios</p>
        </div>
        
        <div className="flex items-center gap-3">
          <Button 
            variant="outline"
            onClick={() => setIsAddModalOpen(true)} 
            className="flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            Añadir Manual
          </Button>
          <Button 
            variant="outline"
            onClick={handleExportCSV} 
            className="flex items-center gap-2"
          >
            <Download className="w-4 h-4" />
            Exportar CSV
          </Button>
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            accept=".csv" 
            onChange={handleFileChange} 
          />
          <Button
            variant="outline"
            onClick={handleDownloadTemplate}
            className="flex items-center gap-2"
            title="Descargar plantilla CSV para importar"
          >
            <FileDown className="w-4 h-4" />
            Plantilla CSV
          </Button>
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
            placeholder="Buscar por nombre / material..." 
            className="flex-1 outline-none text-sm"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
          />
        </div>
        <div className="flex-1 flex items-center gap-2 border rounded-md px-3 py-2 focus-within:ring-2 focus-within:ring-blue-500">
          <Filter className="w-4 h-4 text-gray-400" />
          <select 
            className="flex-1 outline-none text-sm bg-transparent"
            value={categoriaFilter}
            onChange={(e) => setCategoriaFilter(e.target.value)}
          >
            <option value="">Todas las categorías</option>
            <option value="materia_prima">Materia Prima</option>
            <option value="herrajes">Herrajes</option>
            <option value="acabados">Acabados</option>
            <option value="mano_obra">Mano de Obra</option>
            <option value="otros">Otros</option>
          </select>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <div className="mb-4 px-4 py-3 bg-blue-600 text-white rounded-lg flex items-center justify-between shadow-md">
          <span className="text-sm font-medium">
            {selectedIds.size} {selectedIds.size === 1 ? 'elemento seleccionado' : 'elementos seleccionados'}
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-blue-200 hover:text-white underline"
            >
              Deseleccionar todo
            </button>
            <Button
              onClick={handleBulkDelete}
              disabled={isBulkDeleting}
              className="flex items-center gap-2 bg-red-600 hover:bg-red-700 text-white border-0"
            >
              {isBulkDeleting ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4" />
              )}
              {isBulkDeleting ? 'Eliminando...' : 'Eliminar seleccionados'}
            </Button>
          </div>
        </div>
      )}

      <PriceTable
        precios={precios}
        loading={loading && skip === 0}
        onUpdatePrecio={handleUpdatePrecio}
        onDeletePrecio={handleDeletePrecio}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
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

      {!loading && precios.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No hay resultados que coincidan con los filtros actuales.
        </div>
      )}

      <AddPriceModal 
        isOpen={isAddModalOpen} 
        onClose={() => setIsAddModalOpen(false)} 
        onAdd={handleAddPrecio} 
      />
    </div>
  );
}
