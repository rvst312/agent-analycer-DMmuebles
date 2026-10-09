"use client";

import UploadForm from "@/components/UploadForm";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { Loader2, FileText, FileImage, Clock, CheckCircle, ArrowRight, AlertCircle } from "lucide-react";
import { EstimateSummary } from "@/types/estimate";
import { authHeaders } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STATUS_CONFIG: Record<string, { label: string; dot: string; textColor: string }> = {
  processing:              { label: "Procesando",         dot: "bg-blue-400",    textColor: "text-blue-600" },
  human_approval_required: { label: "Pendiente revisión", dot: "bg-amber-400",   textColor: "text-amber-600" },
  pending_review:          { label: "Pendiente revisión", dot: "bg-amber-400",   textColor: "text-amber-600" },
  approved:                { label: "Aprobado",           dot: "bg-emerald-400", textColor: "text-emerald-600" },
  completed:               { label: "Completado",         dot: "bg-emerald-400", textColor: "text-emerald-600" },
  sent_to_holded:          { label: "Enviado",            dot: "bg-violet-400",  textColor: "text-violet-600" },
  rejected:                { label: "Rechazado",          dot: "bg-red-400",     textColor: "text-red-600" },
  error:                   { label: "Error",              dot: "bg-red-400",     textColor: "text-red-600" },
};

function RecentEstimates() {
  const [estimates, setEstimates] = useState<EstimateSummary[]>([]);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    fetch(`${BASE_URL}/estimates`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setEstimates((d.estimates ?? []).slice(0, 6)); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center py-6">
      <Loader2 className="w-4 h-4 animate-spin text-gray-300" />
    </div>
  );

  if (estimates.length === 0) return (
    <p className="text-sm text-gray-400 py-4 text-center">Aún no hay presupuestos generados.</p>
  );

  return (
    <div className="divide-y divide-gray-100">
      {estimates.map(est => {
        const cfg = STATUS_CONFIG[est.status] ?? { label: est.status, dot: "bg-gray-300", textColor: "text-gray-500" };
        const isPdf = est.image_url?.toLowerCase().includes(".pdf");
        const isPending = est.status === "human_approval_required" || est.status === "pending_review";

        return (
          <Link
            key={est.estimate_id}
            href={`/estimates/${est.estimate_id}`}
            className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors group"
          >
            {/* Thumb */}
            <div className="w-10 h-10 rounded-lg bg-gray-100 border border-gray-200 flex items-center justify-center overflow-hidden shrink-0">
              {est.image_url ? (
                isPdf
                  ? <FileText className="w-4 h-4 text-gray-400" />
                  : <Image src={`${BASE_URL}${est.image_url}`} alt="" width={40} height={40} className="object-cover w-full h-full" unoptimized />
              ) : (
                <FileImage className="w-4 h-4 text-gray-300" />
              )}
            </div>

            {/* Info */}
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-900 truncate">
                {est.nombre_cliente || est.cliente_id || "—"}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`flex items-center gap-1 text-xs ${cfg.textColor}`}>
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${cfg.dot} ${est.status === "processing" ? "animate-pulse" : ""}`} />
                  {cfg.label}
                </span>
                {est.updated_at && (
                  <span className="text-xs text-gray-400">
                    · {new Date(est.updated_at).toLocaleDateString("es-ES", { day: "2-digit", month: "short" })}
                  </span>
                )}
              </div>
            </div>

            {/* Total + arrow */}
            <div className="text-right shrink-0">
              {est.total > 0 && (
                <p className="text-sm font-semibold text-gray-900 tabular-nums">
                  {est.total.toLocaleString("es-ES", { style: "currency", currency: "EUR" })}
                </p>
              )}
              <ArrowRight className={`w-4 h-4 mt-0.5 ml-auto transition-transform group-hover:translate-x-0.5 ${isPending ? "text-amber-500" : "text-gray-300 group-hover:text-gray-500"}`} />
            </div>
          </Link>
        );
      })}
    </div>
  );
}

export default function Home() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-gray-900">Nuevo presupuesto</h1>
        <p className="text-sm text-gray-400 mt-0.5">Sube uno o varios planos para generar el presupuesto automáticamente.</p>
      </div>

      {/* Form card */}
      <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 mb-8">
        <UploadForm />
      </div>

      {/* Recent estimates */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
            <Clock className="w-4 h-4 text-gray-400" />
            Últimas generaciones
          </h2>
          <Link href="/dashboard" className="text-xs text-gray-400 hover:text-gray-700 flex items-center gap-1 transition-colors">
            Ver todos <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <RecentEstimates />
        </div>
      </div>
    </div>
  );
}
