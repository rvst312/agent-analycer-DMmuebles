"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Loader2, FileImage, Clock, CheckCircle, XCircle, AlertCircle, Eye } from "lucide-react";
import { EstimateSummary } from "@/types/estimate";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  processing:              { label: "Procesando",         color: "bg-blue-100 text-blue-700",   icon: <Loader2 className="w-3 h-3 animate-spin" /> },
  human_approval_required: { label: "Pendiente Revisión", color: "bg-yellow-100 text-yellow-800", icon: <Clock className="w-3 h-3" /> },
  pending_review:          { label: "Pendiente Revisión", color: "bg-yellow-100 text-yellow-800", icon: <Clock className="w-3 h-3" /> },
  approved:                { label: "Aprobado",           color: "bg-green-100 text-green-700",  icon: <CheckCircle className="w-3 h-3" /> },
  completed:               { label: "Completado",         color: "bg-green-100 text-green-700",  icon: <CheckCircle className="w-3 h-3" /> },
  sent_to_holded:          { label: "Enviado a Holded",   color: "bg-purple-100 text-purple-700",icon: <CheckCircle className="w-3 h-3" /> },
  rejected:                { label: "Rechazado",          color: "bg-red-100 text-red-700",      icon: <XCircle className="w-3 h-3" /> },
  error:                   { label: "Error",              color: "bg-red-100 text-red-700",      icon: <AlertCircle className="w-3 h-3" /> },
};

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, color: "bg-gray-100 text-gray-700", icon: null };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}>
      {cfg.icon}
      {cfg.label}
    </span>
  );
}

function EstimateCard({ est }: { est: EstimateSummary }) {
  const isPendingReview = est.status === "human_approval_required" || est.status === "pending_review";

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden flex flex-col hover:shadow-md transition-shadow">
      {/* Thumbnail */}
      <div className="relative h-40 bg-gray-100 flex items-center justify-center overflow-hidden">
        {est.image_url ? (
          <Image
            src={`${BASE_URL}${est.image_url}`}
            alt={`Plano ${est.estimate_id.substring(0, 8)}`}
            fill
            className="object-contain"
            sizes="(max-width: 768px) 100vw, 33vw"
            unoptimized
          />
        ) : (
          <FileImage className="w-12 h-12 text-gray-300" />
        )}
        {est.status === "processing" && (
          <div className="absolute inset-0 bg-black/20 flex items-center justify-center">
            <div className="bg-white rounded-full p-2 shadow">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
            </div>
          </div>
        )}
      </div>

      {/* Card body */}
      <div className="p-4 flex flex-col gap-3 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs text-gray-400 font-mono">{est.estimate_id.substring(0, 8)}…</p>
            <p className="text-sm font-semibold text-gray-800 mt-0.5 truncate max-w-[140px]">
              {est.cliente_id || "—"}
            </p>
          </div>
          <StatusBadge status={est.status} />
        </div>

        {est.total > 0 && (
          <p className="text-lg font-bold text-gray-900">
            {est.total.toLocaleString("es-ES", { style: "currency", currency: "EUR" })}
          </p>
        )}

        {est.updated_at && (
          <p className="text-xs text-gray-400">
            {new Date(est.updated_at).toLocaleString("es-ES", {
              day: "2-digit", month: "2-digit", year: "numeric",
              hour: "2-digit", minute: "2-digit",
            })}
          </p>
        )}

        <div className="mt-auto pt-2 border-t border-gray-100">
          <Link
            href={`/estimates/${est.estimate_id}`}
            className={`flex items-center justify-center gap-1.5 w-full py-1.5 rounded-lg text-sm font-medium transition-colors ${
              isPendingReview
                ? "bg-yellow-500 hover:bg-yellow-600 text-white"
                : "bg-gray-100 hover:bg-gray-200 text-gray-700"
            }`}
          >
            <Eye className="w-3.5 h-3.5" />
            {isPendingReview ? "Revisar" : "Ver detalle"}
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [estimates, setEstimates] = useState<EstimateSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchEstimates = async () => {
    try {
      const res = await fetch(`${BASE_URL}/estimates`);
      if (res.ok) {
        const data = await res.json();
        setEstimates(data.estimates || []);
      }
    } catch (err) {
      console.error("Error fetching estimates:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEstimates();
    const interval = setInterval(fetchEstimates, 15000);
    return () => clearInterval(interval);
  }, []);

  const pending = estimates.filter(e => e.status === "human_approval_required" || e.status === "pending_review");
  const rest = estimates.filter(e => e.status !== "human_approval_required" && e.status !== "pending_review");

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Dashboard de Presupuestos</h1>
        <p className="text-gray-500 mt-1">{estimates.length} presupuesto{estimates.length !== 1 ? "s" : ""} registrado{estimates.length !== 1 ? "s" : ""}</p>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
        </div>
      ) : estimates.length === 0 ? (
        <div className="bg-white p-16 text-center rounded-xl border border-gray-200">
          <FileImage className="w-12 h-12 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 text-lg">No hay presupuestos todavía.</p>
          <Link href="/" className="mt-4 inline-block text-sm text-blue-600 hover:underline">Subir primer plano →</Link>
        </div>
      ) : (
        <div className="space-y-8">
          {pending.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-yellow-700 mb-3 flex items-center gap-2">
                <Clock className="w-4 h-4" /> Pendientes de revisión ({pending.length})
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {pending.map(est => <EstimateCard key={est.estimate_id} est={est} />)}
              </div>
            </section>
          )}

          {rest.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-3">
                Todos los presupuestos
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {rest.map(est => <EstimateCard key={est.estimate_id} est={est} />)}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
