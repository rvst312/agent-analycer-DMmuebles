import apiClient from './api';
import { PrecioResponse, PrecioUpdate, ImportResponse } from '../types/knowledge';

const ADMIN_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYWRtaW4ifQ.dFEG4bSq_LMrSP0JLxQqURpnTDQ1mchXgJ43AhDShFU';

export const knowledgeApi = {
  getPrecios: async (skip = 0, limit = 100, activosOnly = false): Promise<PrecioResponse[]> => {
    const response = await apiClient.get('/knowledge', {
      params: { skip, limit, activos_only: activosOnly },
      headers: {
        Authorization: `Bearer ${ADMIN_TOKEN}`,
      },
    });
    return response.data;
  },

  updatePrecio: async (id: string, updateData: PrecioUpdate): Promise<{ status: string; message: string }> => {
    const response = await apiClient.patch(`/knowledge/${id}`, updateData, {
      headers: {
        Authorization: `Bearer ${ADMIN_TOKEN}`,
      },
    });
    return response.data;
  },

  deletePrecio: async (id: string): Promise<{ status: string; message: string }> => {
    const response = await apiClient.delete(`/knowledge/${id}`, {
      headers: {
        Authorization: `Bearer ${ADMIN_TOKEN}`,
      },
    });
    return response.data;
  },

  importCsv: async (file: File): Promise<ImportResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post('/knowledge/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
        Authorization: `Bearer ${ADMIN_TOKEN}`,
      },
    });
    return response.data;
  },
};
