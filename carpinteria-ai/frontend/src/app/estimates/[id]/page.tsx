"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import PlanViewer from "@/components/PlanViewer";
import EstimateBreakdown from "@/components/EstimateBreakdown";
import { EstimateDetail, LineaPresupuesto } from "@/types/estimate";
import { Button } from "@/components/ui/button";

export default function EstimatePage() {
  const params = useParams();
  const router = useRouter();
  const estimateId = params.id as string;
  const [estimate, setEstimate] = useState<EstimateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [motivoRechazo, setMotivoRechazo] = useState("");

  const [lineas, setLineas] = useState<LineaPresupuesto[]>([]);
  const [subtotal, setSubtotal] = useState(0);
  const [iva, setIva] = useState(0);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const fetchEstimate = async () => {
      try {
        setLoading(true);
        const res = await fetch(`http://localhost:8000/estimates/${estimateId}`);
        if (!res.ok) {
          throw new Error("No se pudo cargar el presupuesto");
        }
        const data: EstimateDetail = await res.json();
        setEstimate(data);
        if (data.presupuesto_consolidado) {
          setLineas(data.presupuesto_consolidado.lineas || []);
          setSubtotal(data.presupuesto_consolidado.subtotal || 0);
          setIva(data.presupuesto_consolidado.iva || 0);
          setTotal(data.presupuesto_consolidado.total || 0);
        }
      } catch (err: unknown) {
        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError("Error desconocido");
        }
      } finally {
        setLoading(false);
      }
    };

    fetchEstimate();
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
      const res = await fetch(`http://localhost:8000/workflow/resume`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer fake_token_for_now" // Si verify_jefe_obra_token lo requiere
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
      router.push("/dashboard");
    } catch (err: unknown) {
      if (err instanceof Error) {
        alert(err.message);
      } else {
        alert("Error en la acción");
      }
    }
  };

  if (loading) return <div className="p-8">Cargando...</div>;
  if (error) return <div className="p-8 text-red-500">Error: {error}</div>;
  if (!estimate) return <div className="p-8">No encontrado</div>;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Revisión de Presupuesto #{estimateId.substring(0,8)}</h1>
        <span className="px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800">
          {estimate.status}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div className="flex flex-col gap-4">
          <PlanViewer imageUrl={estimate.image_url ? `http://localhost:8000${estimate.image_url}` : undefined} />
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
              <textarea 
                className="w-full border rounded p-2 text-sm" 
                placeholder="Motivo de rechazo (opcional)"
                value={motivoRechazo}
                onChange={(e) => setMotivoRechazo(e.target.value)}
                rows={3}
              />
              <div className="flex gap-4">
                <Button 
                  onClick={() => handleAction("reject")}
                  variant="destructive"
                  className="flex-1"
                >
                  Rechazar
                </Button>
                <Button 
                  onClick={() => handleAction("approve")}
                  className="flex-1"
                >
                  Aprobar Presupuesto
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}