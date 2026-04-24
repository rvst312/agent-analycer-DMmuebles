"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import PlanViewer from "@/components/PlanViewer";
import EstimateBreakdown from "@/components/EstimateBreakdown";
import { EstimateDetail, LineaPresupuesto } from "@/types/estimate";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

export default function EstimatePage() {
  const params = useParams();
  const router = useRouter();
  const estimateId = params.id as string;
  const [estimate, setEstimate] = useState<EstimateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [showApproveModal, setShowApproveModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [motivoRechazo, setMotivoRechazo] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [lineas, setLineas] = useState<LineaPresupuesto[]>([]);
  const [subtotal, setSubtotal] = useState(0);
  const [iva, setIva] = useState(0);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const TERMINAL_STATUSES = new Set(["human_approval_required", "completed", "rejected", "error"]);
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const fetchEstimate = async () => {
      try {
        const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${baseUrl}/estimates/${estimateId}`);
        if (!res.ok) throw new Error("No se pudo cargar el presupuesto");
        const data: EstimateDetail = await res.json();
        setEstimate(data);
        setLoading(false);
        if (data.presupuesto_consolidado) {
          setLineas(data.presupuesto_consolidado.lineas || []);
          setSubtotal(data.presupuesto_consolidado.subtotal || 0);
          setIva(data.presupuesto_consolidado.iva || 0);
          setTotal(data.presupuesto_consolidado.total || 0);
        }
        if (TERMINAL_STATUSES.has(data.status) && intervalId) {
          clearInterval(intervalId);
          intervalId = null;
        }
      } catch (err: unknown) {
        setLoading(false);
        if (err instanceof Error) setError(err.message);
        else setError("Error desconocido");
        if (intervalId) clearInterval(intervalId);
      }
    };

    fetchEstimate();
    intervalId = setInterval(fetchEstimate, 5000);
    return () => { if (intervalId) clearInterval(intervalId); };
  }, [estimateId]);

  const handleLineasChange = (newLineas: LineaPresupuesto[]) => {
    setLineas(newLineas);
    const newSubtotal = newLineas.reduce((acc, l) => acc + l.subtotal, 0);
    const newIva = newSubtotal * 0.21;
    const newTotal = newSubtotal + newIva;
    setSubtotal(newSubtotal);
    setIva(newIva);
    setTotal(newTotal);
  };

  const handleAction = async (action: "approve" | "reject") => {
    try {
      if (action === "reject" && !motivoRechazo.trim()) {
        toast.error("Por favor, ingresa un motivo para el rechazo.");
        return;
      }

      setIsSubmitting(true);
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

      // Obtener token de desarrollo
      const tokenRes = await fetch(`${baseUrl}/workflow/token`, { method: "POST" });
      if (!tokenRes.ok) throw new Error("No se pudo obtener el token de autorización");
      const { access_token } = await tokenRes.json();

      const res = await fetch(`${baseUrl}/workflow/resume`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${access_token}`
        },
        body: JSON.stringify({
          thread_id: estimateId,
          action,
          ajustes: {
            lineas,
            subtotal,
            iva,
            total,
          },
          motivo: action === "reject" ? motivoRechazo : undefined,
        }),
      });
      if (!res.ok) throw new Error("Error en la acción");
      
      setShowApproveModal(false);
      setShowRejectModal(false);
      toast.success(action === "approve" ? "Presupuesto aprobado correctamente" : "Presupuesto rechazado correctamente");
      router.push("/dashboard");
    } catch (err: unknown) {
      if (err instanceof Error) {
        toast.error(err.message);
      } else {
        toast.error("Error en la acción");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loading) return (
    <div className="p-8 flex flex-col items-center justify-center min-h-[40vh] gap-4">
      <Loader2 className="h-10 w-10 animate-spin text-primary" />
      <p className="text-gray-500">Analizando el plano y calculando presupuesto...</p>
    </div>
  );
  if (error) return <div className="p-8 text-red-500">Error: {error}</div>;
  if (!estimate) return <div className="p-8">No encontrado</div>;

  const TERMINAL_STATUSES = new Set(["human_approval_required", "completed", "rejected", "error"]);
  const isProcessing = estimate && !TERMINAL_STATUSES.has(estimate.status);

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Revisión de Presupuesto #{estimateId.substring(0,8)}</h1>
        <span className="px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800 flex items-center gap-2">
          {isProcessing && <Loader2 className="h-3 w-3 animate-spin" />}
          {estimate.status}
        </span>
      </div>
      {isProcessing && (
        <div className="mb-6 p-4 bg-yellow-50 border border-yellow-200 rounded-lg flex items-center gap-3 text-yellow-800">
          <Loader2 className="h-5 w-5 animate-spin flex-shrink-0" />
          <span>Analizando el plano y calculando presupuesto. Esta página se actualizará automáticamente.</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="flex flex-col gap-4">
          <PlanViewer imageUrl={estimate.image_url ? `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${estimate.image_url}` : undefined} />
        </div>
        <div className="flex flex-col gap-4">
          <EstimateBreakdown 
            lineas={lineas} 
            subtotal={subtotal}
            iva={iva}
            total={total}
            onChange={handleLineasChange}
          />
          
          {estimate.status === "human_approval_required" && (
            <div className="border rounded-lg p-4 bg-white shadow-sm mt-4 flex flex-col gap-4">
              <h3 className="text-lg font-semibold">Acciones</h3>
              <p className="text-sm text-gray-600 mb-2">Revisa el presupuesto y toma una decisión para continuar el proceso.</p>
              <div className="flex gap-4">
                <Button 
                  onClick={() => setShowRejectModal(true)}
                  variant="destructive"
                  className="flex-1"
                >
                  Rechazar
                </Button>
                <Button 
                  onClick={() => setShowApproveModal(true)}
                  className="flex-1"
                >
                  Aprobar Presupuesto
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Approve Modal */}
      {showApproveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md p-6">
            <h3 className="text-xl font-semibold mb-4">Aprobar Presupuesto</h3>
            <p className="text-gray-600 mb-6">
              ¿Estás seguro de que deseas aprobar este presupuesto? Se enviará al cliente.
            </p>
            <div className="flex justify-end gap-3">
              <Button 
                variant="outline" 
                onClick={() => setShowApproveModal(false)}
                disabled={isSubmitting}
              >
                Cancelar
              </Button>
              <Button 
                onClick={() => handleAction("approve")}
                disabled={isSubmitting}
                className="min-w-[120px]"
              >
                {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                {isSubmitting ? "Aprobando..." : "Sí, aprobar"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md p-6">
            <h3 className="text-xl font-semibold mb-4">Rechazar Presupuesto</h3>
            <p className="text-gray-600 mb-4 text-sm">
              Ingresa el motivo del rechazo para que el equipo pueda revisarlo.
            </p>
            <textarea 
              className="w-full border border-gray-300 rounded-md p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-6" 
              placeholder="Motivo de rechazo..."
              value={motivoRechazo}
              onChange={(e) => setMotivoRechazo(e.target.value)}
              rows={4}
              disabled={isSubmitting}
            />
            <div className="flex justify-end gap-3">
              <Button 
                variant="outline" 
                onClick={() => setShowRejectModal(false)}
                disabled={isSubmitting}
              >
                Cancelar
              </Button>
              <Button 
                variant="destructive"
                onClick={() => handleAction("reject")}
                disabled={isSubmitting || !motivoRechazo.trim()}
                className="min-w-[120px]"
              >
                {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                {isSubmitting ? "Rechazando..." : "Sí, rechazar"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}