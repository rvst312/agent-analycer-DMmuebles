"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import PlanViewer from "@/components/PlanViewer";
import EstimateBreakdown from "@/components/EstimateBreakdown";
import ComponentsEditor from "@/components/ComponentsEditor";
import KbSearchModal from "@/components/KbSearchModal";
import { EstimateDetail, LineaPresupuesto, PlanoAnalizado, PriceCorrection, SSEEvent } from "@/types/estimate";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { ArrowLeft, BrainCircuit, CheckCircle2, Circle, Loader2, Plus, Save } from "lucide-react";
import { getToken } from "@/lib/auth";

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

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  processing:              { label: "Procesando",         color: "bg-blue-50 text-blue-700 border border-blue-200" },
  human_approval_required: { label: "Pendiente revisión", color: "bg-amber-50 text-amber-700 border border-amber-200" },
  pending_review:          { label: "Pendiente revisión", color: "bg-amber-50 text-amber-700 border border-amber-200" },
  approved:                { label: "Aprobado",           color: "bg-emerald-50 text-emerald-700 border border-emerald-200" },
  completed:               { label: "Completado",         color: "bg-emerald-50 text-emerald-700 border border-emerald-200" },
  sent_to_holded:          { label: "Enviado a Holded",   color: "bg-violet-50 text-violet-700 border border-violet-200" },
  rejected:                { label: "Rechazado",          color: "bg-red-50 text-red-700 border border-red-200" },
  error:                   { label: "Error",              color: "bg-red-50 text-red-700 border border-red-200" },
};

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
  const [tituloProyecto, setTituloProyecto] = useState('');

  const [originalLineas, setOriginalLineas] = useState<LineaPresupuesto[]>([]);
  const [isSavingFeedback, setIsSavingFeedback] = useState(false);

  const [showApproveModal, setShowApproveModal] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [showLearnModal, setShowLearnModal] = useState(false);
  const [showKbModal, setShowKbModal] = useState(false);
  const [motivoRechazo, setMotivoRechazo] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSavingLineas, setIsSavingLineas] = useState(false);
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

  const setLineasWithOriginal = (ls: LineaPresupuesto[]) => {
    setLineas(ls);
    recalc(ls);
    setOriginalLineas(prev => prev.length === 0 ? ls.map(l => ({ ...l })) : prev);
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

  const handleAddKbLine = (linea: LineaPresupuesto) => {
    const next = [...lineas, linea];
    handleLineasChange(next);
  };

  const handleDiscountsChange = ({ subtotal: s, iva: i, total: t }: { subtotal: number; iva: number; total: number }) => {
    setSubtotal(s);
    setIva(i);
    setTotal(t);
  };

  const handleSaveLineas = async () => {
    setIsSavingLineas(true);
    try {
      const res = await fetch(`${BASE_URL}/estimates/${estimateId}/lineas`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lineas, subtotal, iva, total }),
      });
      if (!res.ok) throw new Error(`Error ${res.status}`);
      toast.success("Presupuesto guardado.");
      setOriginalLineas(lineas.map(l => ({ ...l })));
    } catch {
      toast.error("No se pudieron guardar los cambios.");
    } finally {
      setIsSavingLineas(false);
    }
  };

  const handleSavePriceFeedback = async (corrections: PriceCorrection[]) => {
    if (!corrections.length) return;
    setIsSavingFeedback(true);
    try {
      const res = await fetch(`${BASE_URL}/estimates/${estimateId}/learn-pricing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ correcciones: corrections }),
      });
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data = await res.json();
      toast.success(
        `Correcciones guardadas. ${data.chroma_updated} precio${data.chroma_updated !== 1 ? 's' : ''} actualizado${data.chroma_updated !== 1 ? 's' : ''} en la base de conocimiento.`
      );
      // Reset original so indicators clear
      setOriginalLineas(lineas.map(l => ({ ...l })));
    } catch {
      toast.error("No se pudieron guardar las correcciones de precios.");
    } finally {
      setIsSavingFeedback(false);
    }
  };

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
        setLineasWithOriginal(ls);
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
          setLineasWithOriginal(ls);
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
          setLineasWithOriginal(ls);
        }
        if (presupuesto_consolidado) {
          const ls = formatLineas(presupuesto_consolidado.lineas || []);
          setLineasWithOriginal(ls);
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

      const access_token = getToken();
      if (!access_token) throw new Error("No autenticado");

      const res = await fetch(`${BASE_URL}/workflow/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${access_token}` },
        body: JSON.stringify({
          thread_id: estimateId,
          action,
          ajustes: { lineas, subtotal, iva, total, descripciones_grupo: groupDescriptions, titulo_proyecto: tituloProyecto },
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
      {/* Back + Header */}
      <div className="mb-5">
        <a href="/dashboard" className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-700 transition-colors mb-3">
          <ArrowLeft className="w-3.5 h-3.5" />
          Panel de control
        </a>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              {estimate?.nombre_cliente || estimate?.cliente_id || `Presupuesto #${estimateId.substring(0, 8)}`}
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <p className="text-xs text-gray-400 font-mono">#{estimateId.substring(0, 8)}</p>
              {estimate?.plano_analizado?.tipo_plano && estimate.plano_analizado.tipo_plano !== "general" && (
                <span className="text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded capitalize">
                  {estimate.plano_analizado.tipo_plano.replace(/_/g, " ")}
                </span>
              )}
            </div>
          </div>
          {(() => {
            const rawStatus = loading ? "processing" : (estimate?.status ?? "processing");
            const cfg = STATUS_LABEL[rawStatus] ?? { label: rawStatus, color: "bg-gray-50 text-gray-600 border border-gray-200" };
            return (
              <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium shrink-0 ${cfg.color}`}>
                {(loading || isProcessing) && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                {loading ? "Iniciando…" : cfg.label}
              </span>
            );
          })()}
        </div>
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
          {planoAnalizado && (
            <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">Resumen IA</h3>
                <div className="flex items-center gap-2">
                  {planoAnalizado.tipo_plano && planoAnalizado.tipo_plano !== "general" && (
                    <span className="text-xs font-medium bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full capitalize">
                      {planoAnalizado.tipo_plano.replace(/_/g, " ")}
                    </span>
                  )}
                  <span className="text-xs text-gray-400">{Math.round(planoAnalizado.confidence_score * 100)}% conf.</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-1.5 mb-3">
                {Object.entries(
                  planoAnalizado.componentes.reduce((acc: Record<string, number>, c) => {
                    const key = c.tipo || "otro";
                    acc[key] = (acc[key] || 0) + (c.cantidad || 1);
                    return acc;
                  }, {})
                ).map(([tipo, count]) => (
                  <div key={tipo} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-1.5">
                    <span className="text-xs text-gray-600 capitalize">{tipo.replace(/_/g, " ")}</span>
                    <span className="text-xs font-bold text-gray-900">{count as number}</span>
                  </div>
                ))}
              </div>
              {(() => {
                const mats = Array.from(new Set(planoAnalizado.componentes.map(c => c.material).filter(Boolean))).slice(0, 5);
                return mats.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {mats.map(m => (
                      <span key={m} className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded">{m}</span>
                    ))}
                  </div>
                ) : null;
              })()}
              <p className="text-xs text-gray-400 mt-2">{planoAnalizado.componentes.length} piezas detectadas</p>
            </div>
          )}
        </div>

        {/* Right: lines + actions */}
        <div className="flex flex-col gap-4">
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-gray-800">Presupuesto</h2>
                {isProcessing && lineas.length === 0 && (
                  <span className="flex items-center gap-1 text-xs text-gray-400">
                    <Loader2 className="w-3 h-3 animate-spin" /> calculando…
                  </span>
                )}
                {lineas.length > 0 && (
                  <span className="text-xs text-gray-400">{lineas.length} ítem{lineas.length !== 1 ? "s" : ""}</span>
                )}
              </div>
              <div className="flex items-center gap-1.5">
                <Button variant="outline" size="sm" onClick={() => setShowKbModal(true)} className="gap-1 text-xs h-7 border-gray-200">
                  <Plus className="w-3 h-3" /> KB
                </Button>
                {!isProcessing && lineas.length > 0 && (
                  <Button variant="outline" size="sm" onClick={handleSaveLineas} disabled={isSavingLineas} className="gap-1 text-xs h-7 border-gray-200">
                    {isSavingLineas ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    Guardar
                  </Button>
                )}
              </div>
            </div>

            {lineas.length === 0 && !isProcessing ? (
              <p className="p-6 text-center text-sm text-gray-400">Sin líneas</p>
            ) : (
              <EstimateBreakdown
                estimateId={estimateId}
                lineas={lineas}
                subtotal={subtotal}
                iva={iva}
                total={total}
                onChange={handleLineasChange}
                onDescriptionsChange={setGroupDescriptions}
                onTitleChange={setTituloProyecto}
                originalLineas={originalLineas}
                onSavePriceFeedback={handleSavePriceFeedback}
                isSavingFeedback={isSavingFeedback}
                onDiscountsChange={handleDiscountsChange}
                clienteId={estimate?.cliente_id}
              />
            )}
          </div>

          {planoAnalizado && (
            <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between">
              <p className="text-xs text-gray-500">
                <span className="font-medium text-gray-700">{planoAnalizado.componentes.length} componentes</span>
                {" "}detectados · confianza {Math.round(planoAnalizado.confidence_score * 100)}%
              </p>
              <Button variant="outline" size="sm" className="gap-1.5 text-xs h-7 border-gray-200" onClick={() => setShowLearnModal(true)}>
                <BrainCircuit className="w-3.5 h-3.5" />
                Corregir y aprender
              </Button>
            </div>
          )}

          {canApprove && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
                <h3 className="text-sm font-semibold text-amber-800">Pendiente de revisión</h3>
              </div>
              <p className="text-xs text-amber-700">Revisa las líneas y el importe antes de enviar a Holded.</p>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1 border-gray-300 text-gray-700 hover:bg-gray-50" onClick={() => setShowRejectModal(true)}>
                  Rechazar
                </Button>
                <Button className="flex-1 bg-gray-900 hover:bg-gray-700 text-white" onClick={() => setShowApproveModal(true)}>
                  Aprobar y enviar
                </Button>
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

      {/* KB Search Modal */}
      {showKbModal && (
        <KbSearchModal
          clienteId={estimate?.cliente_id || "general"}
          onAdd={handleAddKbLine}
          onClose={() => setShowKbModal(false)}
        />
      )}

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
