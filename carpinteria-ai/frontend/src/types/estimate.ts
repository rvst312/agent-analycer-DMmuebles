export interface LineaPresupuesto {
  codigo?: string;   // identificador interno generado (TAB-001, PTA-002…)
  ref?: string;      // código de referencia del plano — clave de agrupación
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
  precio_pendiente: boolean;
}

export interface ComponenteArmario {
  tipo: string;
  material: string;
  acabado: string;
  ancho_cm: number;
  largo_cm: number;
  cantidad: number;
  notas?: string;
  ref?: string;      // código de referencia visible en el plano
}

export interface PlanoAnalizado {
  plano_id: string;
  componentes: ComponenteArmario[];
  confidence_score: number;
  raw_reasoning: string;
  error?: string;
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

export interface EstimateSummary {
  estimate_id: string;
  status: string;
  cliente_id?: string;
  total: number;
  image_url?: string;
  created_at?: string;
  updated_at?: string;
}

export interface EstimateDetail {
  estimate_id: string;
  status: string;
  plano_id?: string;
  cliente_id?: string;
  image_url?: string;
  plano_analizado?: PlanoAnalizado;
  presupuesto_calculado?: Record<string, unknown>;
  presupuesto_consolidado?: PresupuestoConsolidado;
  motivo_rechazo?: string;
  error?: string;
}

// SSE event shapes
export type SSEEvent =
  | { type: "current_state"; status: string; total: number; lineas: LineaPresupuesto[]; image_url?: string }
  | { type: "line_added"; linea: LineaPresupuesto }
  | { type: "node_complete"; node: string; status?: string; plano_analizado?: PlanoAnalizado; presupuesto_calculado?: { lineas: LineaPresupuesto[] }; presupuesto_consolidado?: PresupuestoConsolidado; error?: string }
  | { type: "workflow_paused"; status: string }
  | { type: "error"; error: string }
  | { type: "done" };
