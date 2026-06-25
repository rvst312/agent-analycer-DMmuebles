"use client";

import React, { useEffect, useState, useRef, useCallback } from 'react';
import PriceTable from '@/components/PriceTable';
import AddPriceModal from '@/components/AddPriceModal';
import { knowledgeApi } from '@/lib/knowledge-api';
import { PrecioResponse } from '@/types/knowledge';
import { toast } from 'sonner';
import { Upload, Loader2, Search, Filter, Download, Plus, Trash2, FileDown, AlertTriangle, X } from 'lucide-react';

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

  // Categorías dinámicas
  const [categories, setCategories] = useState<string[]>([]);

  // Importación
  const [isImporting, setIsImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Selección masiva
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [selectAllInDb, setSelectAllInDb] = useState(false);

  // Paginación
  const [skip, setSkip] = useState(0);
  const limit = 50;

  const hasMore = precios.length > 0 && precios.length % limit === 0;
  const allVisibleSelected = precios.length > 0 && precios.every(p => selectedIds.has(p.id));

  // Cargar categorías al montar
  useEffect(() => {
    knowledgeApi.getCategories()
      .then(cats => setCategories(cats))
      .catch(() => {});
  }, []);

  // Debounce filtros
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchFilter);
      setDebouncedCategoria(categoriaFilter);
      setSkip(0);
    }, 400);
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
          const existingIds = new Set(prev.map(p => p.id));
          return [...prev, ...data.filter(p => !existingIds.has(p.id))];
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
    setSelectAllInDb(false);
  }, [debouncedSearch, debouncedCategoria]);

  const handleUpdatePrecio = async (id: string, nuevoPrecio: number) => {
    try {
      await knowledgeApi.updatePrecio(id, { precio_unitario: nuevoPrecio });
      toast.success('Precio actualizado correctamente');
      setPrecios(prev => prev.map(p =>
        p.id === id ? { ...p, metadatos: { ...p.metadatos, precio_unitario: nuevoPrecio } } : p
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
      // Recargar categorías por si se añadió una nueva
      knowledgeApi.getCategories().then(cats => setCategories(cats)).catch(() => {});
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al añadir el precio'));
      throw err;
    }
  };

  const handleBulkDelete = async () => {
    if (selectAllInDb) {
      const scope = debouncedCategoria
        ? `toda la categoría "${debouncedCategoria}"`
        : 'TODA la base de precios';
      if (!confirm(`¿Eliminar ${scope}? Esta acción no se puede deshacer.`)) return;
      setIsBulkDeleting(true);
      try {
        const result = await knowledgeApi.deleteAll(debouncedCategoria || undefined);
        toast.success(`${result.deleted} precio${result.deleted === 1 ? '' : 's'} eliminado${result.deleted === 1 ? '' : 's'}`);
        setSelectAllInDb(false);
        setSelectedIds(new Set());
        setSkip(0);
        await fetchPrecios(0, debouncedSearch, debouncedCategoria);
        knowledgeApi.getCategories().then(cats => setCategories(cats)).catch(() => {});
      } catch (err) {
        console.error(err);
        toast.error(extractErrorMessage(err, 'Error al eliminar'));
      } finally {
        setIsBulkDeleting(false);
      }
      return;
    }

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
        toast.warning(`Importación completada con errores: ${response.procesadas} procesadas, ${response.errores.length} errores.`);
        console.warn('Errores de importación:', response.errores);
      } else {
        toast.success(`Importación exitosa: ${response.procesadas} filas procesadas.`);
      }
      setSkip(0);
      await fetchPrecios(0, debouncedSearch, debouncedCategoria);
      knowledgeApi.getCategories().then(cats => setCategories(cats)).catch(() => {});
    } catch (err) {
      console.error(err);
      toast.error(extractErrorMessage(err, 'Error al importar el archivo CSV'));
    } finally {
      setIsImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleImportClick = () => fileInputRef.current?.click();

  const handleDownloadTemplate = () => {
    const headers = 'id,material,cliente,precio_unitario,unidad,categoria,texto,version';
    const example = ',Tablero melamina blanco 19mm,general,28.50,m2,materia_prima,tablero para módulo armario,1.0';
    const blob = new Blob([`${headers}\n${example}`], { type: 'text/csv;charset=utf-8;' });
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
    if (precios.length === 0) { toast.warning('No hay datos para exportar'); return; }
    const headers = ['ID', 'Material', 'Categoría', 'Cliente', 'Precio Unitario', 'Unidad'];
    const rows = precios.map(p => [
      p.id,
      `"${p.metadatos.material.replace(/"/g, '""')}"`,
      `"${p.metadatos.categoria.replace(/"/g, '""')}"`,
      `"${p.metadatos.cliente.replace(/"/g, '""')}"`,
      p.metadatos.precio_unitario.toString(),
      `"${p.metadatos.unidad.replace(/"/g, '""')}"`
    ]);
    const blob = new Blob([[headers.join(','), ...rows.map(r => r.join(','))].join('\n')], { type: 'text/csv;charset=utf-8;' });
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
    <div className="p-6 max-w-7xl mx-auto">

      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Base de precios</h1>
        <p className="text-sm text-gray-400 mt-0.5">Conocimiento RAG para materiales y precios de carpintería</p>
      </div>

      {/* Toolbar: filters + actions */}
      <div className="flex flex-col sm:flex-row gap-3 mb-5">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Buscar material, descripción…"
            className="w-full pl-9 pr-8 py-2 text-sm border border-gray-200 rounded-lg bg-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 transition-shadow"
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
          />
          {searchFilter && (
            <button onClick={() => setSearchFilter('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Category filter */}
        <div className="relative sm:w-52">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
          <select
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-gray-200 transition-shadow appearance-none cursor-pointer"
            value={categoriaFilter}
            onChange={(e) => setCategoriaFilter(e.target.value)}
          >
            <option value="">Todas las categorías</option>
            {categories.map(cat => <option key={cat} value={cat}>{cat}</option>)}
          </select>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={handleDownloadTemplate} title="Plantilla CSV"
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:border-gray-300 hover:text-gray-800 bg-white transition-colors">
            <FileDown className="w-3.5 h-3.5" /> Plantilla
          </button>
          <button onClick={handleExportCSV}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:border-gray-300 hover:text-gray-800 bg-white transition-colors">
            <Download className="w-3.5 h-3.5" /> Exportar
          </button>
          <input type="file" ref={fileInputRef} className="hidden" accept=".csv" onChange={handleFileChange} />
          <button onClick={handleImportClick} disabled={isImporting}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:border-gray-300 hover:text-gray-800 bg-white transition-colors disabled:opacity-50">
            {isImporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
            {isImporting ? 'Importando…' : 'Importar CSV'}
          </button>
          <button onClick={() => setIsAddModalOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm bg-gray-900 hover:bg-gray-700 text-white rounded-lg font-medium transition-colors">
            <Plus className="w-3.5 h-3.5" /> Añadir
          </button>
        </div>
      </div>

      {/* Import progress banner */}
      {isImporting && (
        <div className="mb-5 px-4 py-3 bg-gray-50 border border-gray-200 rounded-xl flex items-center gap-3 text-gray-700">
          <Loader2 className="w-4 h-4 animate-spin text-gray-400 shrink-0" />
          <div className="flex-1">
            <p className="text-sm font-medium">Procesando archivo CSV…</p>
            <div className="w-full bg-gray-200 rounded-full h-1 mt-1.5 overflow-hidden">
              <div className="bg-gray-500 h-1 rounded-full w-full animate-pulse" />
            </div>
          </div>
        </div>
      )}

      {/* Bulk selection banner */}
      {selectedIds.size > 0 && (
        <div className={`mb-4 px-4 py-3 rounded-xl flex flex-col gap-2 ${
          selectAllInDb
            ? 'bg-red-50 border border-red-200 text-red-700'
            : 'bg-gray-900 text-white'
        }`}>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium flex items-center gap-2">
              {selectAllInDb && <AlertTriangle className="w-4 h-4" />}
              {selectAllInDb
                ? debouncedCategoria
                  ? `Se eliminará toda la categoría "${debouncedCategoria}"`
                  : 'Se eliminará TODA la base de precios'
                : `${selectedIds.size} ${selectedIds.size === 1 ? 'elemento seleccionado' : 'elementos seleccionados'}`
              }
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => { setSelectedIds(new Set()); setSelectAllInDb(false); }}
                className={`text-sm px-3 py-1.5 rounded-lg transition-colors ${
                  selectAllInDb ? 'text-red-600 hover:bg-red-100' : 'text-white/70 hover:text-white hover:bg-white/10'
                }`}
              >
                Cancelar
              </button>
              <button
                onClick={handleBulkDelete}
                disabled={isBulkDeleting}
                className={`inline-flex items-center gap-1.5 text-sm font-medium px-3 py-1.5 rounded-lg transition-colors disabled:opacity-60 ${
                  selectAllInDb
                    ? 'bg-red-600 text-white hover:bg-red-700'
                    : 'bg-white text-gray-900 hover:bg-gray-100'
                }`}
              >
                {isBulkDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                {isBulkDeleting ? 'Eliminando…' : selectAllInDb ? 'Eliminar todo' : 'Eliminar seleccionados'}
              </button>
            </div>
          </div>

          {allVisibleSelected && hasMore && !selectAllInDb && (
            <div className="border-t border-white/20 pt-2 text-sm text-white/70 flex items-center gap-2 flex-wrap">
              <span>Solo se han cargado {precios.length} elementos.</span>
              <button onClick={() => setSelectAllInDb(true)} className="underline text-white font-medium">
                Seleccionar {debouncedCategoria ? `toda la categoría "${debouncedCategoria}"` : 'toda la base de datos'}
              </button>
            </div>
          )}
          {selectAllInDb && (
            <div className="border-t border-red-200 pt-2 text-sm text-red-600 flex items-center gap-2 flex-wrap">
              <span>Afectará a todos los registros{debouncedCategoria ? ` de "${debouncedCategoria}"` : ''}, no solo los visibles.</span>
              <button onClick={() => setSelectAllInDb(false)} className="underline font-medium">
                Volver a selección parcial
              </button>
            </div>
          )}
        </div>
      )}

      {/* Table */}
      <PriceTable
        precios={precios}
        loading={loading && skip === 0}
        onUpdatePrecio={handleUpdatePrecio}
        onDeletePrecio={handleDeletePrecio}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
      />

      {/* Load more */}
      {!loading && precios.length > 0 && hasMore && (
        <div className="flex justify-center mt-5">
          <button onClick={() => setSkip(prev => prev + limit)} disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm border border-gray-200 rounded-lg text-gray-600 hover:border-gray-300 hover:text-gray-800 bg-white transition-colors disabled:opacity-50">
            {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Cargar más
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && precios.length === 0 && (
        <div className="bg-white border border-gray-200 rounded-xl py-16 text-center">
          <p className="text-sm text-gray-400">No hay resultados para los filtros actuales.</p>
          {(searchFilter || categoriaFilter) && (
            <button onClick={() => { setSearchFilter(''); setCategoriaFilter(''); }}
              className="mt-2 text-sm text-gray-600 hover:text-gray-900 underline underline-offset-2">
              Limpiar filtros
            </button>
          )}
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
