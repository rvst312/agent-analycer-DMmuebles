export interface PriceCorrection {
  codigo?: string;
  descripcion: string;
  precio_original: number;
  precio_corregido: number;
}

export interface LineaPresupuesto {
  codigo?: string;   // identificador interno generado (TAB-001, PTA-002…)
  ref?: string;      // código de referencia del plano — clave de agrupación
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
  precio_pendiente: boolean;
  explicacion?: string; // desglose de cómo se calculó el precio (tarifa base + %)
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

export interface PartidaResumen {
  familia?: string;
  descripcion?: string;
  habitacion?: string;
  material?: string;
  cantidad?: number;
  ref?: string;
}

export interface PlanoAnalizado {
  plano_id: string;
  tipo_plano?: string;
  proyecto?: string; // calle + número del proyecto detectados en el plano
  componentes: ComponenteArmario[];
  partidas?: PartidaResumen[];
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
  titulos_grupo?: Record<string, string>;
  descripciones_grupo?: Record<string, string>;
  familias_faltantes?: string[];
}

export interface EstimateSummary {
  estimate_id: string;
  status: string;
  cliente_id?: string;
  nombre_cliente?: string;
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
  nombre_cliente?: string;
  image_url?: string;
  image_urls?: string[];
  plano_analizado?: PlanoAnalizado;
  presupuesto_calculado?: Record<string, unknown>;
  presupuesto_consolidado?: PresupuestoConsolidado;
  imagenes_grupo?: Record<string, string>;
  proyecto?: string; // calle + número (persistido en BD)
  motivo_rechazo?: string;
  error?: string;
}

// SSE event shapes
export type SSEEvent =
  | { type: "current_state"; status: string; total: number; lineas: LineaPresupuesto[]; image_url?: string; image_urls?: string[] }
  | { type: "viewer_ready"; image_urls: string[] }
  | { type: "line_added"; linea: LineaPresupuesto }
  | { type: "node_complete"; node: string; status?: string; plano_analizado?: PlanoAnalizado; presupuesto_calculado?: { lineas: LineaPresupuesto[] }; presupuesto_consolidado?: PresupuestoConsolidado; error?: string }
  | { type: "workflow_paused"; status: string }
  | { type: "error"; error: string }
  | { type: "done" };
