import apiClient from './api';
import { PrecioResponse, PrecioUpdate, ImportResponse } from '../types/knowledge';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function getAdminToken(): Promise<string> {
  const res = await fetch(`${API_URL}/workflow/token?role=admin`, { method: 'POST' });
  if (!res.ok) throw new Error('No se pudo obtener el token de administrador');
  const data = await res.json();
  return data.access_token;
}

export const knowledgeApi = {
  getPrecios: async (skip = 0, limit = 100, activosOnly = false): Promise<PrecioResponse[]> => {
    const token = await getAdminToken();
    const response = await apiClient.get('/knowledge', {
      params: { skip, limit, activos_only: activosOnly },
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  updatePrecio: async (id: string, updateData: PrecioUpdate): Promise<{ status: string; message: string }> => {
    const token = await getAdminToken();
    const response = await apiClient.patch(`/knowledge/${id}`, updateData, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  deletePrecio: async (id: string): Promise<{ status: string; message: string }> => {
    const token = await getAdminToken();
    const response = await apiClient.delete(`/knowledge/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return response.data;
  },

  importCsv: async (file: File): Promise<ImportResponse> => {
    const token = await getAdminToken();
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
