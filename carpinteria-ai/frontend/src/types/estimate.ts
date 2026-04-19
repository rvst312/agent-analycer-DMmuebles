export interface LineaPresupuesto {
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
  precio_pendiente: boolean;
}

export interface PresupuestoConsolidado {
  cliente_id: string;
  plano_id: string;
  lineas: LineaPresupuesto[];
  subtotal: number;
  iva: number;
  total: number;
  status: string;
}

export interface EstimateDetail {
  estimate_id: string;
  status: string;
  plano_id?: string;
  cliente_id?: string;
  image_url?: string;
  plano_analizado?: Record<string, unknown>;
  presupuesto_calculado?: Record<string, unknown>;
  presupuesto_consolidado?: PresupuestoConsolidado;
  motivo_rechazo?: string;
  error?: string;
}