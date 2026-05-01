"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { CheckCircle, Loader2, XCircle } from "lucide-react";
import { toast } from "sonner";
import ModuleAccordion from "@/components/ModuleAccordion";
import { LineaPresupuesto, ModuloProyecto, ProyectoDetail } from "@/types/estimate";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FINAL_STATUSES = new Set(["approved", "rejected", "error"]);

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [proyecto, setProyecto] = useState<ProyectoDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  // Local overrides for lineas (editable in the accordion)
  const [lineOverrides, setLineOverrides] = useState<Record<string, LineaPresupuesto[]>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchProject = useCallback(async () => {
    try {
      const res = await fetch(`${BASE_URL}/projects/${id}`);
      if (!res.ok) {
        if (res.status === 404) {
          toast.error("Proyecto no encontrado.");
          router.push("/");
        }
        return;
      }
      const data: ProyectoDetail = await res.json();
      setProyecto(data);
      setLoading(false);

      // Stop polling when all modules have reached a final status
      if (FINAL_STATUSES.has(data.status) || data.modulos.every((m) => FINAL_STATUSES.has(m.status) || m.status === "pending_review")) {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      }
    } catch (err) {
      console.error("Error fetching project:", err);
    }
  }, [id, router]);

  useEffect(() => {
    fetchProject();
    pollRef.current = setInterval(fetchProject, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchProject]);

  const handleLinesChange = (estimateId: string, newLineas: LineaPresupuesto[]) => {
    setLineOverrides((prev) => ({ ...prev, [estimateId]: newLineas }));
  };

  const handleApprove = async () => {
    if (!proyecto) return;
    setActing(true);
    try {
      const res = await fetch(`${BASE_URL}/projects/${id}/approve`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Presupuesto enviado a Holded. ID: ${data.holded_estimate_id}`);
        await fetchProject();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(`Error al aprobar: ${err.detail ?? res.status}`);
      }
    } catch {
      toast.error("Error de conexión.");
    } finally {
      setActing(false);
    }
  };

  const handleReject = async () => {
    if (!proyecto) return;
    setActing(true);
    try {
      const res = await fetch(`${BASE_URL}/projects/${id}/reject`, { method: "POST" });
      if (res.ok) {
        toast.success("Proyecto rechazado.");
        await fetchProject();
      } else {
        toast.error(`Error al rechazar: ${res.status}`);
      }
    } catch {
      toast.error("Error de conexión.");
    } finally {
      setActing(false);
    }
  };

  const allReady = proyecto?.modulos.every(
    (m) => m.status === "pending_review" || FINAL_STATUSES.has(m.status)
  ) ?? false;

  const canAct =
    allReady &&
    proyecto?.status !== "approved" &&
    proyecto?.status !== "rejected" &&
    !acting;

  const totalGeneral = proyecto
    ? proyecto.modulos.reduce((sum, m) => {
        const lineas = lineOverrides[m.estimate_id] ?? m.lineas;
        const sub = lineas.reduce((s, l) => s + (l.precio_pendiente ? 0 : l.subtotal), 0);
        return sum + sub * 1.21;
      }, 0)
    : 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!proyecto) return null;

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Proyecto</h1>
          <p className="text-sm text-muted-foreground font-mono mt-0.5">{proyecto.proyecto_id}</p>
        </div>
        {proyecto.holded_estimate_id && (
          <span className="text-xs bg-green-100 text-green-700 px-3 py-1 rounded-full font-medium">
            Holded: {proyecto.holded_estimate_id}
          </span>
        )}
      </div>

      {/* Modules accordion */}
      <div className="space-y-3">
        {proyecto.modulos.map((modulo) => {
          const merged: ModuloProyecto = lineOverrides[modulo.estimate_id]
            ? { ...modulo, lineas: lineOverrides[modulo.estimate_id] }
            : modulo;
          return (
            <ModuleAccordion
              key={modulo.estimate_id}
              modulo={merged}
              onLinesChange={handleLinesChange}
            />
          );
        })}
      </div>

      {/* Summary table */}
      <div className="border rounded-lg bg-white p-4">
        <h2 className="font-semibold text-gray-900 mb-3">Resumen por módulo</h2>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Módulo</th>
              <th className="px-3 py-2 text-left font-medium">Descripción</th>
              <th className="px-3 py-2 text-right font-medium">Total (IVA inc.)</th>
            </tr>
          </thead>
          <tbody>
            {proyecto.modulos.map((m) => {
              const lineas = lineOverrides[m.estimate_id] ?? m.lineas;
              const sub = lineas.reduce((s, l) => s + (l.precio_pendiente ? 0 : l.subtotal), 0);
              const total = sub * 1.21;
              return (
                <tr key={m.estimate_id} className="border-t">
                  <td className="px-3 py-2 font-medium">{m.nombre_modulo}</td>
                  <td className="px-3 py-2 text-gray-500 text-xs">
                    {m.resumen?.descripcion ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-medium">{total.toFixed(2)} €</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-200 font-bold">
              <td colSpan={2} className="px-3 py-2 text-right">Total proyecto:</td>
              <td className="px-3 py-2 text-right text-lg">{totalGeneral.toFixed(2)} €</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Action buttons */}
      {proyecto.status !== "approved" && proyecto.status !== "rejected" && (
        <div className="flex gap-3 pt-2">
          <Button
            className="flex-1"
            size="lg"
            onClick={handleApprove}
            disabled={!canAct}
          >
            {acting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <CheckCircle className="mr-2 h-4 w-4" />
            )}
            Aprobar y enviar a Holded
          </Button>
          <Button
            variant="outline"
            size="lg"
            className="flex-1 border-red-200 text-red-600 hover:bg-red-50"
            onClick={handleReject}
            disabled={!canAct}
          >
            {acting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <XCircle className="mr-2 h-4 w-4" />
            )}
            Rechazar
          </Button>
        </div>
      )}

      {proyecto.status === "approved" && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm font-medium">
          Proyecto aprobado y enviado a Holded.
        </div>
      )}
      {proyecto.status === "rejected" && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-red-700 text-sm font-medium">
          Proyecto rechazado.
        </div>
      )}

      {!allReady && proyecto.status === "processing" && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Procesando módulos... Los botones se activarán cuando todos estén listos.
        </div>
      )}
    </div>
  );
}
