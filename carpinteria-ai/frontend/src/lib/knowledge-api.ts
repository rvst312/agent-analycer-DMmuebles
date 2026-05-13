import apiClient from './api';
import { PrecioResponse, PrecioUpdate, ImportResponse } from '../types/knowledge';
import { getToken } from './auth';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getAdminToken(): string {
  const token = getToken();
  if (!token) throw new Error('No autenticado');
  return token;
}

export const knowledgeApi = {
  getPrecios: async (skip = 0, limit = 100, activosOnly = false, search?: string, categoria?: string): Promise<PrecioResponse[]> => {
    const token = getAdminToken();
    const params: Record<string, string | number | boolean> = { skip, limit, activos_only: activosOnly };
    if (search) params.search = search;
    if (categoria) params.categoria = categoria;
    const response = await apiClient.get('/knowledge', {
      params,
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  createPrecio: async (precio: Omit<PrecioResponse, 'id'>): Promise<{ status: string; message: string }> => {
    const token = getAdminToken();
    const response = await apiClient.post('/knowledge', precio, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  updatePrecio: async (id: string, updateData: PrecioUpdate): Promise<{ status: string; message: string }> => {
    const token = getAdminToken();
    const response = await apiClient.patch(`/knowledge/${id}`, updateData, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  deletePrecio: async (id: string): Promise<{ status: string; message: string }> => {
    const token = getAdminToken();
    const response = await apiClient.delete(`/knowledge/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  bulkDelete: async (ids: string[]): Promise<{ status: string; deleted: number }> => {
    const token = getAdminToken();
    const response = await apiClient.delete('/knowledge/bulk', {
      headers: { Authorization: `Bearer ${token}` },
      data: { ids },
    });
    return response.data;
  },

  importCsv: async (file: File): Promise<ImportResponse> => {
    const token = getAdminToken();
    const formData = new FormData();
    formData.append('file', file);
    // Usar fetch directamente: el apiClient tiene Content-Type: application/json por defecto
    // y eso interfiere con el boundary de multipart/form-data que necesita FastAPI
    const res = await fetch(`${API_URL}/knowledge/import`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw { response: { data } };
    }
    return res.json();
  },
};
