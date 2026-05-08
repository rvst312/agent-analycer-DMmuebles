"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import PlanViewer from "@/components/PlanViewer";
import EstimateBreakdown from "@/components/EstimateBreakdown";
import ComponentsEditor from "@/components/ComponentsEditor";
import { EstimateDetail, LineaPresupuesto, PlanoAnalizado, SSEEvent } from "@/types/estimate";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { BrainCircuit, CheckCircle2, Circle, Loader2 } from "lucide-react";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MAX_POLL_ATTEMPTS = 30; // ~60 s at 2 s interval before giving up

const NODES_ORDER = [
  { key: "receive_input",    label: "Recibiendo plano" },
  { key: "vision_analysis",  label: "Analizando imagen con IA" },
  { key: "extract_entities", label: "Extrayendo entidades" },
  { key: "rag_pricing",      label: "Calculando precios" },
  { key: "consolidate",      label: "Consolidando presupuesto" },
];

const TERMINAL = new Set(["human_approval_required", "pending_review", "completed", "rejected", "error", "approved"]);

function NodeProgress({ done, current }: { done: Set<string>; current: string | null }) {
  return (
    <ol className="flex flex-col gap-1.5">
      {NODES_ORDER.map((n) => {
        const isDone = done.has(n.key);
        const isActive = current === n.key && !isDone;
        return (
          <li key={n.key} className={`flex items-center gap-2 text-sm ${isDone ? "text-green-700" : isActive ? "text-blue-600 font-medium" : "text-gray-400"}`}>
            {isDone   ? <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
             : isActive ? <Loader2 className="w-4 h-4 animate-spin text-blue-500 flex-shrink-0" />
             :            <Circle className="w-4 h-4 flex-shrink-0" />}
            {n.label}
          </li>
        );
      })}
    </ol>
  );
}

export default function EstimatePage() {
  const params = useParams();
  const router = useRouter();
  const estimateId = params.id as string;

  const [estimate, setEstimate] = useState<EstimateDetail | null>(null);
  const [imageUrls, setImageUrls] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);

  const [doneNodes, setDoneNodes] = useState<Set<string>>(new Set());
  const [currentNode, setCurrentNode] = useState<string | null>(NODES_ORDER[0].key);

  const [lineas, setLineas] = useState<LineaPresupuesto[]>([]);
  const [subtotal, setSubtotal] = useState(0);
  const [iva, setIva] = useState(0);
  const [total, setTotal] = useState(0);
  const [groupDescriptions, setGroupDescriptions] = useState<Record<string, string>>({});

  const [showApproveModal, setShowApproveModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [showLearnModal, setShowLearnModal] = useState(false);
  const [motivoRechazo, setMotivoRechazo] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [planoAnalizado, setPlanoAnalizado] = useState<PlanoAnalizado | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);
  const sseFailed = useRef(false);

  const formatLineas = (lines: LineaPresupuesto[]) => {
    return lines.map(l => ({
      ...l,
      precio_unitario: Number(Number(l.precio_unitario || 0).toFixed(2)),
      subtotal: Number(Number(l.subtotal ?? ((l.cantidad || 0) * (l.precio_unitario || 0))).toFixed(2))
    }));
  };

  const recalc = (lines: LineaPresupuesto[]) => {
    const s = lines
      .filter(l => !l.precio_pendiente)
      .reduce((a, l) => a + (l.subtotal ?? 0), 0);
    setSubtotal(s);
    setIva(s * 0.21);
    setTotal(s + s * 0.21);
  };

  const handleLineasChange = (nl: LineaPresupuesto[]) => { setLineas(nl); recalc(nl); };

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    pollCountRef.current = 0;
  }, []);

  const stopSSE = useCallback(() => {
    if (esRef.current) { esRef.current.close(); esRef.current = null; }
  }, []);

  const fetchEstimate = useCallback(async () => {
    // Safety net: stop polling after MAX_POLL_ATTEMPTS to prevent infinite loops
    pollCountRef.current++;
    if (pollCountRef.current > MAX_POLL_ATTEMPTS) {
      stopPoll();
      setLoading(false);
      setIsProcessing(false);
      setPageError("Tiempo de espera agotado. Recarga la página para reintentar.");
      return;
    }

    try {
      const res = await fetch(`${BASE_URL}/estimates/${estimateId}`);
      if (res.status === 404) {
        // Estimate not in DB yet — keep polling briefly
        setLoading(false);
        return;
      }
      if (!res.ok) throw new Error(`Error ${res.status}`);

      const data: EstimateDetail = await res.json();
      setEstimate(data);
      setLoading(false);

      if (data.image_urls?.length) setImageUrls(u => u.length >= (data.image_urls?.length ?? 0) ? u : (data.image_urls ?? u));

      if (data.plano_analizado?.componentes?.length) {
        setPlanoAnalizado(data.plano_analizado);
      }

      if (data.presupuesto_consolidado) {
        const ls = formatLineas(data.presupuesto_consolidado.lineas || []);
        setLineas(ls);
        recalc(ls);
      }

      if (TERMINAL.has(data.status)) {
        setIsProcessing(false);
        stopPoll();
      }
    } catch (err) {
      setLoading(false);
      if (!sseFailed.current) return;
      setPageError(err instanceof Error ? err.message : "Error desconocido");
      stopPoll();
    }
  }, [estimateId, stopPoll]);

  useEffect(() => {
    let mounted = true;

    const applyEvent = (raw: SSEEvent) => {
      if (!mounted) return;

      if (raw.type === "current_state") {
        setLoading(false);
        setEstimate(prev => prev ?? ({
          estimate_id: estimateId,
          status: raw.status,
          image_url: raw.image_url ?? undefined,
        } as EstimateDetail));
        if (raw.image_urls?.length) setImageUrls(u => u.length >= raw.image_urls!.length ? u : raw.image_urls!);
        if (raw.lineas?.length) {
          const ls = formatLineas(raw.lineas);
          setLineas(ls);
          recalc(ls);
        }
        if (TERMINAL.has(raw.status)) setIsProcessing(false);
        return;
      }

      if (raw.type === "line_added") {
        setLoading(false);
        setLineas(prev => { 
          const next = formatLineas([...prev, raw.linea]); 
          recalc(next); 
          return next; 
        });
        return;
      }

      if (raw.type === "node_complete") {
        setLoading(false);
        const { node, status, presupuesto_calculado, presupuesto_consolidado } = raw;
        setDoneNodes(prev => { const s = new Set(prev); s.add(node); return s; });
        setCurrentNode(null);

        if (raw.plano_analizado && (raw.plano_analizado as PlanoAnalizado).componentes?.length) {
          setPlanoAnalizado(raw.plano_analizado as PlanoAnalizado);
        }

        if (presupuesto_calculado?.lineas) { 
          const ls = formatLineas(presupuesto_calculado.lineas);
          setLineas(ls); 
          recalc(ls); 
        }
        if (presupuesto_consolidado) {
          const ls = formatLineas(presupuesto_consolidado.lineas || []);
          setLineas(ls);
          recalc(ls);
        }
        if (status && TERMINAL.has(status)) setIsProcessing(false);

        const idx = NODES_ORDER.findIndex(n => n.key === node);
        if (idx >= 0 && idx < NODES_ORDER.length - 1) setCurrentNode(NODES_ORDER[idx + 1].key);
        return;
      }

      if (raw.type === "workflow_paused" || raw.type === "done" || raw.type === "error") {
        setIsProcessing(false);
        setCurrentNode(null);
        setLoading(false);

        // For errors: show the message immediately without waiting for fetchEstimate
        if (raw.type === "error") {
          setEstimate(prev => ({
            ...(prev ?? { estimate_id: estimateId, status: "error" }),
            status: "error",
            error: raw.error,
          } as EstimateDetail));
        }

        stopSSE();
        // Also fetch the full state from the API to get lineas, presupuesto, etc.
        fetchEstimate();
        if (!pollRef.current) {
          pollRef.current = setInterval(fetchEstimate, 2000);
        }
        return;
      }
    };

    const es = new EventSource(`${BASE_URL}/estimates/${estimateId}/stream`);
    esRef.current = es;

    es.onmessage = (e) => {
      try { applyEvent(JSON.parse(e.data) as SSEEvent); } catch { /* ignore malformed frames */ }
    };

    es.onerror = () => {
      sseFailed.current = true;
      stopSSE();
      fetchEstimate();
      if (!pollRef.current) {
        pollRef.current = setInterval(fetchEstimate, 4000);
      }
    };

    return () => {
      mounted = false;
      stopSSE();
      stopPoll();
    };
  }, [estimateId, fetchEstimate, stopSSE, stopPoll]);

  const handleAction = async (action: "approve" | "reject") => {
    try {
      if (action === "reject" && !motivoRechazo.trim()) {
        toast.error("Por favor, ingresa un motivo para el rechazo.");
        return;
      }
      setIsSubmitting(true);

      const tokenRes = await fetch(`${BASE_URL}/workflow/token`, { method: "POST" });
      if (!tokenRes.ok) throw new Error("No se pudo obtener el token");
      const { access_token } = await tokenRes.json();

      const res = await fetch(`${BASE_URL}/workflow/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${access_token}` },
        body: JSON.stringify({
          thread_id: estimateId,
          action,
          ajustes: { lineas, subtotal, iva, total, descripciones_grupo: groupDescriptions },
          motivo: action === "reject" ? motivoRechazo : undefined,
        }),
      });
      if (!res.ok) throw new Error("Error en la acción");

      setShowApproveModal(false);
      setShowRejectModal(false);
      toast.success(action === "approve" ? "Presupuesto aprobado" : "Presupuesto rechazado");
      router.push("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error en la acción");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (pageError) return (
    <div className="p-8 max-w-xl mx-auto mt-16 text-center">
      <div className="bg-red-50 border border-red-200 rounded-xl p-6">
        <p className="text-red-700 font-semibold mb-2">Error</p>
        <p className="text-red-600 text-sm">{pageError}</p>
        <Button className="mt-4" variant="outline" onClick={() => window.location.reload()}>
          Recargar página
        </Button>
      </div>
    </div>
  );

  const canApprove = estimate?.status === "human_approval_required" || estimate?.status === "pending_review";

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Presupuesto #{estimateId.substring(0, 8)}</h1>
          {estimate?.cliente_id && <p className="text-sm text-gray-500 mt-0.5">Cliente: {estimate.cliente_id}</p>}
        </div>
        <span className={`px-3 py-1 rounded-full text-sm font-medium flex items-center gap-1.5 ${
          loading || isProcessing      ? "bg-blue-100 text-blue-700" :
          canApprove                   ? "bg-yellow-100 text-yellow-800" :
          estimate?.status === "error" ? "bg-red-100 text-red-700" :
          "bg-green-100 text-green-700"
        }`}>
          {(loading || isProcessing) && <Loader2 className="w-3 h-3 animate-spin" />}
          {loading ? "Iniciando análisis…" : (estimate?.status ?? "Procesando")}
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        {/* Left: plan + progress */}
        <div className="flex flex-col gap-4 sticky top-24">
          <PlanViewer
            imageUrls={imageUrls.length ? imageUrls.map(u => `${BASE_URL}${u}`) : undefined}
            imageUrl={estimate?.image_url ? `${BASE_URL}${estimate.image_url}` : undefined}
          />
          {isProcessing && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 mb-3">Progreso del análisis</p>
              <NodeProgress done={doneNodes} current={currentNode} />
            </div>
          )}
        </div>

        {/* Right: lines + actions */}
        <div className="flex flex-col gap-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-gray-700">Líneas del presupuesto</h2>
              <span className="text-xs text-gray-400 flex items-center gap-1">
                {isProcessing && lineas.length === 0 && <><Loader2 className="w-3 h-3 animate-spin" /> Calculando…</>}
                {lineas.length > 0 && `${lineas.length} ítem${lineas.length !== 1 ? "s" : ""}`}
              </span>
            </div>

            {lineas.length === 0 && !isProcessing ? (
              <p className="p-6 text-center text-sm text-gray-400">Sin líneas</p>
            ) : (
              <EstimateBreakdown
                lineas={lineas}
                subtotal={subtotal}
                iva={iva}
                total={total}
                onChange={handleLineasChange}
                onDescriptionsChange={setGroupDescriptions}
              />
            )}
          </div>

          {planoAnalizado && (
            <div className="bg-purple-50 border border-purple-200 rounded-xl p-3 shadow-sm flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-purple-800">Aprendizaje Automático</p>
                <p className="text-xs text-purple-600 mt-0.5">
                  {planoAnalizado.componentes.length} componente{planoAnalizado.componentes.length !== 1 ? "s" : ""} detectados · confianza {Math.round(planoAnalizado.confidence_score * 100)}%
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                className="border-purple-300 text-purple-700 hover:bg-purple-100 gap-1.5"
                onClick={() => setShowLearnModal(true)}
              >
                <BrainCircuit className="w-4 h-4" />
                Corregir y aprender
              </Button>
            </div>
          )}

          {canApprove && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-gray-700">Acciones</h3>
              <p className="text-xs text-gray-500">Revisa el presupuesto antes de continuar.</p>
              <div className="flex gap-3">
                <Button variant="destructive" className="flex-1" onClick={() => setShowRejectModal(true)}>Rechazar</Button>
                <Button className="flex-1" onClick={() => setShowApproveModal(true)}>Aprobar y enviar</Button>
              </div>
            </div>
          )}

          {estimate?.motivo_rechazo && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
              <span className="font-semibold">Motivo de rechazo: </span>{estimate.motivo_rechazo}
            </div>
          )}
          {estimate?.error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700">
              <span className="font-semibold">Error: </span>{estimate.error}
            </div>
          )}
        </div>
      </div>

      {/* Approve Modal */}
      {showApproveModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6">
            <h3 className="text-lg font-semibold mb-3">Aprobar presupuesto</h3>
            <p className="text-sm text-gray-600 mb-6">Se enviará a Holded con las líneas actuales. ¿Confirmar?</p>
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setShowApproveModal(false)} disabled={isSubmitting}>Cancelar</Button>
              <Button onClick={() => handleAction("approve")} disabled={isSubmitting} className="min-w-[110px]">
                {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                {isSubmitting ? "Aprobando…" : "Sí, aprobar"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-lg w-full max-w-md p-6">
            <h3 className="text-lg font-semibold mb-3">Rechazar presupuesto</h3>
            <textarea
              className="w-full border border-gray-300 rounded-lg p-3 text-sm focus:outline-none focus:ring-2 focus:ring-red-400 mb-6"
              placeholder="Motivo de rechazo…"
              value={motivoRechazo}
              onChange={(e) => setMotivoRechazo(e.target.value)}
              rows={4}
              disabled={isSubmitting}
            />
            <div className="flex justify-end gap-3">
              <Button variant="outline" onClick={() => setShowRejectModal(false)} disabled={isSubmitting}>Cancelar</Button>
              <Button variant="destructive" onClick={() => handleAction("reject")} disabled={isSubmitting || !motivoRechazo.trim()} className="min-w-[110px]">
                {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                {isSubmitting ? "Rechazando…" : "Sí, rechazar"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Learning Modal */}
      {showLearnModal && planoAnalizado && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-lg w-full max-w-4xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <div className="flex items-center gap-2">
                <BrainCircuit className="w-5 h-5 text-purple-600" />
                <h3 className="text-lg font-semibold">Aprendizaje Automático</h3>
              </div>
              <button
                onClick={() => setShowLearnModal(false)}
                className="text-gray-400 hover:text-gray-600 text-xl leading-none"
              >
                ×
              </button>
            </div>
            <div className="overflow-y-auto p-6 flex-1">
              <ComponentsEditor
                estimateId={estimateId}
                originalComponents={planoAnalizado.componentes}
                onClose={() => setShowLearnModal(false)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
