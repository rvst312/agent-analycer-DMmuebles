"use client";

import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import ContactSearch from "@/components/ContactSearch";
import { FileText, Loader2, Upload, X, CheckCircle2, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { authHeaders } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ALLOWED_TYPES = ["image/jpeg", "image/png", "application/pdf"];

interface HoldedContact { id: string; name: string; }
interface SelectedFile { file: File; previewUrl: string | null; id: string; }
interface CreateContactForm { nombre: string; email: string; telefono: string; nif: string; }

function validateFile(f: File): string | null {
  if (!ALLOWED_TYPES.includes(f.type)) return "Formato no soportado. Solo PNG, JPG o PDF.";
  if (f.size > MAX_FILE_SIZE) return `"${f.name}" supera el límite de 20 MB.`;
  return null;
}

function formatSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(0)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function Step({ n, done }: { n: number; done: boolean }) {
  return (
    <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-all duration-200 ${
      done ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-400"
    }`}>
      {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : n}
    </span>
  );
}

export default function UploadForm() {
  const router = useRouter();
  const [selectedFiles, setSelectedFiles]     = useState<SelectedFile[]>([]);
  const [clientId, setClientId]               = useState("");
  const [notasContexto, setNotasContexto]     = useState("");
  const [isDragging, setIsDragging]           = useState(false);
  const [isUploading, setIsUploading]         = useState(false);
  const [contacts, setContacts]               = useState<HoldedContact[]>([]);
  const [contactsLoading, setContactsLoading] = useState(true);
  const [contactsError, setContactsError]     = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isCreating, setIsCreating]           = useState(false);
  const [createForm, setCreateForm]           = useState<CreateContactForm>({ nombre: "", email: "", telefono: "", nif: "" });
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch(`${BASE_URL}/holded/contacts`, { headers: authHeaders() })
      .then(r => { if (!r.ok) throw new Error(); return r.json() as Promise<HoldedContact[]>; })
      .then(d => { setContacts(d); setContactsLoading(false); })
      .catch(() => { setContactsError("No se pudieron cargar los clientes."); setContactsLoading(false); });
  }, []);

  useEffect(() => () => {
    selectedFiles.forEach(sf => { if (sf.previewUrl) URL.revokeObjectURL(sf.previewUrl); });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const addFiles = (rawFiles: FileList | File[]) => {
    const next: SelectedFile[] = [];
    for (const f of Array.from(rawFiles)) {
      const err = validateFile(f);
      if (err) { toast.error(err); continue; }
      if (selectedFiles.some(s => s.file.name === f.name && s.file.size === f.size)) continue;
      next.push({ file: f, id: `${f.name}-${f.size}-${Date.now()}`, previewUrl: f.type.startsWith("image/") ? URL.createObjectURL(f) : null });
    }
    if (next.length) setSelectedFiles(prev => [...prev, ...next]);
  };

  const removeFile = (id: string) => {
    setSelectedFiles(prev => {
      const e = prev.find(s => s.id === id);
      if (e?.previewUrl) URL.revokeObjectURL(e.previewUrl);
      return prev.filter(s => s.id !== id);
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleCreateContact = async (e: React.FormEvent) => {
    e.preventDefault();
    const nombre = createForm.nombre.trim();
    if (!nombre) { toast.error("El nombre es obligatorio."); return; }
    setIsCreating(true);
    try {
      const res = await fetch(`${BASE_URL}/holded/contacts`, {
        method: "POST", headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ nombre, email: createForm.email.trim() || undefined, telefono: createForm.telefono.trim() || undefined, nif: createForm.nif.trim() || undefined }),
      });
      if (!res.ok) { const err = await res.json().catch(() => ({})) as { detail?: string }; throw new Error(err.detail ?? `Error ${res.status}`); }
      const nc: HoldedContact = await res.json();
      setContacts(prev => [...prev, nc].sort((a, b) => a.name.localeCompare(b.name)));
      setClientId(nc.id);
      setShowCreateModal(false);
      setCreateForm({ nombre: "", email: "", telefono: "", nif: "" });
      toast.success(`Cliente "${nc.name}" creado.`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Error creando el cliente.");
    } finally { setIsCreating(false); }
  };

  const handleSubmit = async () => {
    if (!selectedFiles.length) { toast.error("Selecciona al menos un plano."); return; }
    if (!clientId)              { toast.error("Selecciona un cliente."); return; }
    setIsUploading(true);
    try {
      const fd = new FormData();
      selectedFiles.forEach(sf => fd.append("files", sf.file));
      fd.append("cliente_id", clientId);
      const contact = contacts.find(c => c.id === clientId);
      if (contact) fd.append("nombre_cliente", contact.name);
      if (notasContexto.trim()) fd.append("notas_contexto", notasContexto.trim());
      const res = await fetch(`${BASE_URL}/estimates`, { method: "POST", body: fd, headers: authHeaders() });
      if (res.ok || res.status === 202) {
        const data = await res.json();
        toast.success("Plano subido. Procesando…");
        router.push(`/estimates/${data.estimate_id}`);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(`Error: ${(err as { detail?: string }).detail ?? res.status}`);
      }
    } catch { toast.error("Error de conexión."); }
    finally { setIsUploading(false); }
  };

  const selectedContact = contacts.find(c => c.id === clientId);
  const isReady = selectedFiles.length > 0 && !!clientId;

  return (
    <>
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-8 items-start">

        {/* ── Drop zone ── */}
        <div className="flex flex-col gap-3">
          <input ref={fileInputRef} type="file" className="hidden" accept=".pdf,image/png,image/jpeg" multiple
            onChange={e => { if (e.target.files?.length) addFiles(e.target.files); }} disabled={isUploading} />

          <div
            className={`relative border-2 border-dashed rounded-xl transition-all duration-200 cursor-pointer overflow-hidden
              ${isDragging ? "border-gray-900 bg-gray-50 scale-[1.01]" : "border-gray-200 bg-white hover:border-gray-400 hover:bg-gray-50/50"}`}
            style={{ minHeight: selectedFiles.length ? undefined : "320px" }}
            onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={e => { e.preventDefault(); setIsDragging(false); }}
            onDrop={e => { e.preventDefault(); setIsDragging(false); if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files); }}
            onClick={() => !isUploading && fileInputRef.current?.click()}
          >
            {selectedFiles.length === 0 ? (
              /* ── Empty state ── */
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 p-8">
                <div className={`w-16 h-16 rounded-full flex items-center justify-center transition-all duration-200 ${isDragging ? "bg-gray-900 scale-110" : "bg-gray-100"}`}>
                  <Upload className={`w-7 h-7 transition-colors ${isDragging ? "text-white" : "text-gray-400"}`} />
                </div>
                <div className="text-center space-y-1.5">
                  <p className="text-base font-medium text-gray-700">
                    {isDragging ? "Suelta aquí" : "Arrastra los planos aquí"}
                  </p>
                  <p className="text-sm text-gray-400">o haz clic para seleccionar archivos</p>
                  <p className="text-xs text-gray-300 mt-2">PNG · JPG · PDF · hasta 20 MB · múltiples archivos</p>
                </div>
              </div>
            ) : (
              /* ── File list ── */
              <div className="p-4 space-y-2">
                {selectedFiles.map(sf => (
                  <div key={sf.id} onClick={e => e.stopPropagation()}
                    className="flex items-center gap-3 bg-gray-50 border border-gray-200 rounded-lg px-3.5 py-3 group hover:border-gray-300 transition-colors">
                    <div className="w-12 h-12 rounded-lg bg-white border border-gray-200 flex items-center justify-center overflow-hidden shrink-0 shadow-sm">
                      {sf.previewUrl
                        ? <img src={sf.previewUrl} alt="" className="w-full h-full object-cover" /> // eslint-disable-line @next/next/no-img-element
                        : <FileText className="w-5 h-5 text-gray-400" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-800 truncate leading-tight">{sf.file.name}</p>
                      <p className="text-xs text-gray-400 mt-0.5">{formatSize(sf.file.size)}</p>
                    </div>
                    <button type="button" onClick={() => removeFile(sf.id)} disabled={isUploading}
                      className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all shrink-0">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}

                <button type="button" onClick={e => { e.stopPropagation(); fileInputRef.current?.click(); }} disabled={isUploading}
                  className="w-full flex items-center justify-center gap-2 border border-dashed border-gray-200 rounded-lg py-3 text-sm text-gray-400 hover:border-gray-400 hover:text-gray-600 transition-colors mt-1">
                  <Upload className="w-4 h-4" /> Añadir más archivos
                </button>
              </div>
            )}
          </div>

          {selectedFiles.length > 0 && (
            <p className="text-xs text-gray-400 text-center">
              {selectedFiles.length} {selectedFiles.length === 1 ? "archivo" : "archivos"}
              <button type="button" disabled={isUploading}
                onClick={() => { selectedFiles.forEach(sf => { if (sf.previewUrl) URL.revokeObjectURL(sf.previewUrl); }); setSelectedFiles([]); }}
                className="ml-2 underline underline-offset-2 hover:text-red-500 transition-colors">
                Quitar todos
              </button>
            </p>
          )}
        </div>

        {/* ── Fields + Submit ── */}
        <div className="flex flex-col gap-6">

          {/* Step 1 – Client */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2.5">
              <Step n={1} done={!!clientId} />
              <Label className="text-sm font-medium text-gray-700">Cliente</Label>
            </div>
            <ContactSearch contacts={contacts} loading={contactsLoading} error={contactsError}
              value={clientId} onChange={setClientId} disabled={isUploading}
              onCreateNew={(name) => { setCreateForm({ nombre: name, email: "", telefono: "", nif: "" }); setShowCreateModal(true); }} />
          </div>

          {/* Step 2 – Context */}
          <div className="space-y-2.5">
            <div className="flex items-center gap-2.5">
              <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-400 shrink-0">2</span>
              <Label className="text-sm font-medium text-gray-700">
                Contexto <span className="font-normal text-gray-400 ml-1">— opcional</span>
              </Label>
            </div>
            <textarea
              className="w-full border border-gray-200 rounded-lg px-3.5 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-gray-200 resize-none leading-relaxed text-gray-700 placeholder:text-gray-400"
              rows={4}
              placeholder={"Ej: Melaminizado blanco mate 16mm,\nHerraje Blum Aventos,\nArmarios con puertas correderas…"}
              value={notasContexto}
              onChange={e => setNotasContexto(e.target.value)}
              disabled={isUploading}
            />
          </div>

          {/* Submit */}
          <div className="space-y-3 pt-1">
            <button type="button" onClick={handleSubmit}
              disabled={!isReady || isUploading || contactsLoading}
              className={`w-full flex items-center justify-center gap-2.5 py-3.5 rounded-lg text-sm font-semibold transition-all duration-200 ${
                isReady && !isUploading
                  ? "bg-gray-900 hover:bg-gray-700 text-white shadow-sm hover:shadow"
                  : "bg-gray-100 text-gray-400 cursor-not-allowed"
              }`}
            >
              {isUploading ? (
                <><Loader2 className="w-4 h-4 animate-spin" />Subiendo planos…</>
              ) : isReady ? (
                <>
                  Crear presupuesto
                  {selectedContact && <span className="opacity-50 font-normal">· {selectedContact.name}</span>}
                  <ArrowRight className="w-4 h-4" />
                </>
              ) : (
                "Selecciona cliente y planos"
              )}
            </button>

            {!isReady && !isUploading && (
              <div className="flex items-center justify-center gap-5">
                <span className={`flex items-center gap-1.5 text-xs transition-colors ${clientId ? "text-gray-500" : "text-gray-300"}`}>
                  <CheckCircle2 className={`w-3.5 h-3.5 ${clientId ? "text-emerald-500" : "text-gray-300"}`} />
                  Cliente
                </span>
                <span className={`flex items-center gap-1.5 text-xs transition-colors ${selectedFiles.length ? "text-gray-500" : "text-gray-300"}`}>
                  <CheckCircle2 className={`w-3.5 h-3.5 ${selectedFiles.length ? "text-emerald-500" : "text-gray-300"}`} />
                  Planos
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Modal: nuevo cliente ── */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h3 className="text-base font-semibold text-gray-900">Nuevo cliente</h3>
              <button type="button" onClick={() => { setShowCreateModal(false); setCreateForm({ nombre: "", email: "", telefono: "", nif: "" }); }}
                className="text-gray-400 hover:text-gray-700 transition-colors" disabled={isCreating}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleCreateContact} className="px-6 py-5 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="cc-nombre" className="text-sm font-medium">Nombre <span className="text-red-500">*</span></Label>
                <input id="cc-nombre" type="text" required autoFocus disabled={isCreating}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300 transition-shadow"
                  placeholder="Nombre o razón social"
                  value={createForm.nombre} onChange={e => setCreateForm(f => ({ ...f, nombre: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cc-email" className="text-sm font-medium">Email</Label>
                <input id="cc-email" type="email" disabled={isCreating}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
                  placeholder="cliente@ejemplo.com"
                  value={createForm.email} onChange={e => setCreateForm(f => ({ ...f, email: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="cc-tel" className="text-sm font-medium">Teléfono</Label>
                  <input id="cc-tel" type="tel" disabled={isCreating}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
                    placeholder="+34 600 000 000"
                    value={createForm.telefono} onChange={e => setCreateForm(f => ({ ...f, telefono: e.target.value }))} />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="cc-nif" className="text-sm font-medium">NIF / CIF</Label>
                  <input id="cc-nif" type="text" disabled={isCreating}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-300"
                    placeholder="B12345678"
                    value={createForm.nif} onChange={e => setCreateForm(f => ({ ...f, nif: e.target.value }))} />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <Button type="button" variant="outline" size="sm" disabled={isCreating}
                  onClick={() => { setShowCreateModal(false); setCreateForm({ nombre: "", email: "", telefono: "", nif: "" }); }}>
                  Cancelar
                </Button>
                <Button type="submit" size="sm" disabled={isCreating || !createForm.nombre.trim()}
                  className="min-w-[110px] bg-gray-900 hover:bg-gray-700 text-white">
                  {isCreating ? <><Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />Creando…</> : "Crear cliente"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
