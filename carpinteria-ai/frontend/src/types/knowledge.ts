export interface PrecioMetadata {
  material: string;
  cliente: string;
  precio_unitario: number;
  unidad: string;
  categoria: string;
  version: string;
  activo: boolean;
}

export interface PrecioResponse {
  id: string;
  documento: string;
  metadatos: PrecioMetadata;
}

export interface PrecioUpdate {
  precio_unitario?: number;
  version?: string;
  activo?: boolean;
}

export interface ImportResponse {
  procesadas: number;
  errores: Array<{
    fila: number;
    error: string;
  }>;
}
