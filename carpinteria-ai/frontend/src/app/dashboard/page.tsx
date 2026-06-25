"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  Loader2, FileImage, FileText, Clock, CheckCircle, XCircle,
  AlertCircle, Eye, Trash2, Search, X,
} from "lucide-react";
import { EstimateSummary } from "@/types/estimate";
import { Button } from "@/components/ui/button";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  processing:              { label: "Procesando",         color: "bg-blue-50 text-blue-700 border border-blue-200",          dot: "bg-blue-400" },
  human_approval_required: { label: "Pendiente revisión", color: "bg-amber-50 text-amber-700 border border-amber-200",       dot: "bg-amber-400" },
  pending_review:          { label: "Pendiente revisión", color: "bg-amber-50 text-amber-700 border border-amber-200",       dot: "bg-amber-400" },
  approved:                { label: "Aprobado",           color: "bg-emerald-50 text-emerald-700 border border-emerald-200", dot: "bg-emerald-400" },
  completed:               { label: "Completado",         color: "bg-emerald-50 text-emerald-700 border border-emerald-200", dot: "bg-emerald-400" },
  sent_to_holded:          { label: "Enviado a Holded",   color: "bg-violet-50 text-violet-700 border border-violet-200",   dot: "bg-violet-400" },
  rejected:                { label: "Rechazado",          color: "bg-red-50 text-red-700 border border-red-200",            dot: "bg-red-400" },
  error:                   { label: "Error",              color: "bg-red-50 text-red-700 border border-red-200",            dot: "bg-red-400" },
};

const isPending = (s: string) => s === "human_approval_required" || s === "pending_review";

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, color: "bg-gray-50 text-gray-600 border border-gray-200", dot: "bg-gray-400" };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cfg.color}`}>
      {status === "processing" && <Loader2 className="w-3 h-3 animate-spin" />}
      {cfg.label}
    </span>
  );
}

function EstimateCard({ est, onDelete }: { est: EstimateSummary; onDelete: (id: string) => void }) {
  const pending = isPending(est.status);
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDelete = async () => {
    setIsDeleting(true);
    try {
      const res = await fetch(`${BASE_URL}/estimates/${est.estimate_id}`, { method: "DELETE" });
      if (res.ok || res.status === 404) { setConfirmDelete(false); onDelete(est.estimate_id); }
      else { alert("Error al eliminar."); setIsDeleting(false); }
    } catch { alert("Error de conexión."); setIsDeleting(false); }
  };

  const isPdf = est.image_url?.toLowerCase().includes(".pdf");

  return (
    <>
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden flex flex-col hover:border-gray-300 transition-colors relative group">
        <button
          onClick={() => setConfirmDelete(true)}
          disabled={isDeleting}
          className="absolute top-2 right-2 z-10 bg-white/90 text-gray-400 hover:text-red-500 hover:bg-red-50 p-1 rounded transition-colors opacity-0 group-hover:opacity-100"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>

        {/* Thumbnail */}
        <div className="h-36 bg-gray-50 flex items-center justify-center overflow-hidden relative border-b border-gray-100">
          {est.image_url ? (
            isPdf ? (
              <div className="flex flex-col items-center gap-1.5">
                <FileText className="w-10 h-10 text-gray-300" />
                <span className="text-xs font-mono text-gray-400 tracking-widest">PDF</span>
              </div>
            ) : (
              <Image src={`${BASE_URL}${est.image_url}`} alt="" fill className="object-contain" sizes="33vw" unoptimized />
            )
          ) : (
            <FileImage className="w-10 h-10 text-gray-200" />
          )}
          {est.status === "processing" && (
            <div className="absolute inset-0 bg-white/60 flex items-center justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            </div>
          )}
        </div>

        {/* Body */}
        <div className="p-3 flex flex-col gap-2 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-900 truncate">
                {est.nombre_cliente || est.cliente_id || "—"}
              </p>
              <p className="text-xs text-gray-400 font-mono mt-0.5">{est.estimate_id.substring(0, 8)}…</p>
            </div>
            <StatusBadge status={est.status} />
          </div>

          {est.total > 0 && (
            <p className="text-base font-bold text-gray-900 tabular-nums">
              {est.total.toLocaleString("es-ES", { style: "currency", currency: "EUR" })}
            </p>
          )}

          {est.updated_at && (
            <p className="text-xs text-gray-400">
              {new Date(est.updated_at).toLocaleString("es-ES", {
                day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
              })}
            </p>
          )}

          <div className="mt-auto pt-2 border-t border-gray-100">
            <Link
              href={`/estimates/${est.estimate_id}`}
              className={`flex items-center justify-center gap-1.5 w-full py-1.5 rounded text-sm font-medium transition-colors ${
                pending ? "bg-amber-500 hover:bg-amber-600 text-white" : "bg-gray-900 hover:bg-gray-700 text-white"
              }`}
            >
              <Eye className="w-3.5 h-3.5" />
              {pending ? "Revisar" : "Ver detalle"}
            </Link>
          </div>
        </div>
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-sm p-5">
            <h3 className="text-base font-semibold mb-2">Eliminar presupuesto</h3>
            <p className="text-sm text-gray-500 mb-5">
              ¿Eliminar el presupuesto de{" "}
              <span className="font-medium text-gray-800">
                {est.nombre_cliente || est.cliente_id || est.estimate_id.substring(0, 8)}
              </span>? No se puede deshacer.
            </p>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)} disabled={isDeleting}>Cancelar</Button>
              <Button variant="destructive" size="sm" onClick={handleDelete} disabled={isDeleting} className="min-w-[80px]">
                {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Eliminar"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Filter tabs ──────────────────────────────────────────────────────────────

type FilterKey = "all" | "pending" | "approved" | "completed" | "error";

const FILTER_TABS: { key: FilterKey; label: string; icon: React.ReactNode }[] = [
  { key: "all",       label: "Todos",      icon: null },
  { key: "pending",   label: "Pendientes", icon: <Clock className="w-3.5 h-3.5" /> },
  { key: "approved",  label: "Aprobados",  icon: <CheckCircle className="w-3.5 h-3.5" /> },
  { key: "completed", label: "Completados",icon: <CheckCircle className="w-3.5 h-3.5" /> },
  { key: "error",     label: "Error",      icon: <AlertCircle className="w-3.5 h-3.5" /> },
];

function matchesFilter(est: EstimateSummary, key: FilterKey): boolean {
  if (key === "all")       return true;
  if (key === "pending")   return isPending(est.status);
  if (key === "approved")  return est.status === "approved" || est.status === "sent_to_holded";
  if (key === "completed") return est.status === "completed";
  if (key === "error")     return est.status === "error" || est.status === "rejected";
  return true;
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [estimates, setEstimates] = useState<EstimateSummary[]>([]);
  const [loading, setLoading]     = useState(true);
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");
  const [search, setSearch]             = useState("");

  const fetchEstimates = async () => {
    try {
      const res = await fetch(`${BASE_URL}/estimates`);
      if (res.ok) setEstimates((await res.json()).estimates ?? []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchEstimates();
    const iv = setInterval(fetchEstimates, 15000);
    return () => clearInterval(iv);
  }, []);

  const handleDelete = (id: string) => setEstimates(prev => prev.filter(e => e.estimate_id !== id));

  const counts = useMemo(() => ({
    all:       estimates.length,
    pending:   estimates.filter(e => isPending(e.status)).length,
    approved:  estimates.filter(e => e.status === "approved" || e.status === "sent_to_holded").length,
    completed: estimates.filter(e => e.status === "completed").length,
    error:     estimates.filter(e => e.status === "error" || e.status === "rejected").length,
  }), [estimates]);

  const filtered = useMemo(() => {
    let list = estimates.filter(e => matchesFilter(e, activeFilter));
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(e =>
        (e.nombre_cliente ?? "").toLowerCase().includes(q) ||
        (e.cliente_id ?? "").toLowerCase().includes(q) ||
        e.estimate_id.toLowerCase().includes(q)
      );
    }
    return list;
  }, [estimates, activeFilter, search]);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-gray-900">Panel de control</h1>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-5">
        {/* Tabs */}
        <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1 overflow-x-auto no-scrollbar">
          {FILTER_TABS.map(({ key, label, icon }) => {
            const count = counts[key];
            if (key !== "all" && count === 0) return null;
            const active = activeFilter === key;
            return (
              <button
                key={key}
                onClick={() => setActiveFilter(key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium whitespace-nowrap transition-colors ${
                  active ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {icon && <span className={active ? "text-gray-700" : "text-gray-400"}>{icon}</span>}
                {label}
                <span className={`text-xs rounded px-1 py-0.5 tabular-nums ${
                  active
                    ? key === "pending" && count > 0
                      ? "bg-amber-100 text-amber-700"
                      : "bg-gray-100 text-gray-500"
                    : "text-gray-400"
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Search */}
        <div className="relative sm:ml-auto">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
          <input
            type="text"
            placeholder="Buscar cliente…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-8 pr-7 py-1.5 text-sm border border-gray-200 rounded-lg bg-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-200 w-full sm:w-48"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="w-6 h-6 animate-spin text-gray-300" />
        </div>
      ) : estimates.length === 0 ? (
        <div className="bg-white p-16 text-center rounded-lg border border-gray-200">
          <FileImage className="w-10 h-10 text-gray-200 mx-auto mb-3" />
          <p className="text-gray-400">No hay presupuestos todavía.</p>
          <Link href="/" className="mt-3 inline-block text-sm text-gray-600 hover:text-gray-900 underline underline-offset-2">
            Crear el primero →
          </Link>
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-gray-400 text-sm">Sin resultados para esta búsqueda.</p>
          <button onClick={() => { setSearch(""); setActiveFilter("all"); }} className="mt-2 text-sm text-gray-600 hover:text-gray-900 underline underline-offset-2">
            Limpiar filtros
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {filtered.map(est => <EstimateCard key={est.estimate_id} est={est} onDelete={handleDelete} />)}
        </div>
      )}
    </div>
  );
}
