"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import ContactSearch from "@/components/ContactSearch";
import { File as FileIcon, Image as ImageIcon, Loader2, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20 MB
const ALLOWED_TYPES = ["image/jpeg", "image/png", "application/pdf"];

interface HoldedContact { id: string; name: string; }

interface SelectedFile {
  file: File;
  previewUrl: string | null;
  id: string;
}

function validateFile(f: File): string | null {
  if (!ALLOWED_TYPES.includes(f.type)) return "Formato no soportado. Solo PNG, JPG o PDF.";
  if (f.size > MAX_FILE_SIZE) return `"${f.name}" supera el límite de 20 MB.`;
  return null;
}

export default function UploadForm() {
  const router = useRouter();
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
  const [clientId, setClientId]       = useState<string>("");
  const [isDragging, setIsDragging]   = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [contacts, setContacts]             = useState<HoldedContact[]>([]);
  const [contactsLoading, setContactsLoading] = useState(true);
  const [contactsError, setContactsError]     = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${baseUrl}/holded/contacts`)
      .then(r => { if (!r.ok) throw new Error(); return r.json() as Promise<HoldedContact[]>; })
      .then(d  => { setContacts(d); setContactsLoading(false); })
      .catch(() => { setContactsError("No se pudieron cargar los clientes."); setContactsLoading(false); });
  }, []);

  // cleanup object URLs on unmount
  useEffect(() => () => {
    selectedFiles.forEach(sf => { if (sf.previewUrl) URL.revokeObjectURL(sf.previewUrl); });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const addFiles = (rawFiles: FileList | File[]) => {
    const list = Array.from(rawFiles);
    const newEntries: SelectedFile[] = [];
    for (const f of list) {
      const err = validateFile(f);
      if (err) { toast.error(err); continue; }
      // skip duplicates by name+size
      const isDup = selectedFiles.some(sf => sf.file.name === f.name && sf.file.size === f.size);
      if (isDup) continue;
      newEntries.push({
        file: f,
        id: `${f.name}-${f.size}-${Date.now()}`,
        previewUrl: f.type.startsWith("image/") ? URL.createObjectURL(f) : null,
      });
    }
    if (newEntries.length) setSelectedFiles(prev => [...prev, ...newEntries]);
  };

  const removeFile = (id: string) => {
    setSelectedFiles(prev => {
      const entry = prev.find(sf => sf.id === id);
      if (entry?.previewUrl) URL.revokeObjectURL(entry.previewUrl);
      return prev.filter(sf => sf.id !== id);
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) addFiles(e.target.files);
  };

  const handleSubmit = async (e?: React.FormEvent | React.MouseEvent) => {
    if (e) e.preventDefault();
    if (!selectedFiles.length) { toast.error("Selecciona al menos un plano."); return; }
    if (!clientId)              { toast.error("Selecciona un cliente.");        return; }

    setIsUploading(true);
    try {
      const formData = new FormData();
      selectedFiles.forEach(sf => formData.append("files", sf.file));
      formData.append("cliente_id", clientId);

      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${baseUrl}/estimates`, { method: "POST", body: formData });

      if (res.ok || res.status === 202) {
        const data = await res.json();
        toast.success(`${selectedFiles.length > 1 ? `${selectedFiles.length} planos subidos` : "Plano subido"}. Procesando...`);
        router.push(`/estimates/${data.estimate_id}`);
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(`Error del servidor: ${(err as { detail?: string }).detail ?? res.status}`);
      }
    } catch {
      toast.error("Error de conexión al subir los planos.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Card className="w-full max-w-xl mx-auto">
      <CardHeader>
        <CardTitle>Cargar Plano</CardTitle>
        <CardDescription>
          Sube uno o varios planos (PDF, PNG, JPG) para iniciar el presupuesto.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Cliente */}
          <div className="space-y-2">
            <Label htmlFor="client-search">Cliente</Label>
            <ContactSearch
              contacts={contacts}
              loading={contactsLoading}
              error={contactsError}
              value={clientId}
              onChange={setClientId}
              disabled={isUploading}
            />
          </div>

          {/* Zona de drop */}
          <div className="space-y-2">
            <Label>Planos</Label>
            <div
              className={`border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center transition-colors cursor-pointer ${
                isDragging ? "border-primary bg-primary/10" : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50"
              }`}
              onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={e => { e.preventDefault(); setIsDragging(false); }}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".pdf,image/png,image/jpeg"
                multiple
                onChange={handleFileInput}
                disabled={isUploading}
              />
              <div className="p-3 bg-muted rounded-full mb-3">
                <Upload className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="font-semibold text-sm mb-0.5">Haz clic o arrastra archivos aquí</p>
              <p className="text-xs text-muted-foreground">PNG, JPG, PDF · hasta 20 MB por archivo · múltiples archivos permitidos</p>
            </div>
          </div>

          {/* Lista de archivos seleccionados */}
          {selectedFiles.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground uppercase tracking-wider">
                  {selectedFiles.length} {selectedFiles.length === 1 ? "archivo seleccionado" : "archivos seleccionados"}
                </Label>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                  onClick={() => {
                    selectedFiles.forEach(sf => { if (sf.previewUrl) URL.revokeObjectURL(sf.previewUrl); });
                    setSelectedFiles([]);
                  }}
                  disabled={isUploading}
                >
                  Quitar todos
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                {selectedFiles.map(sf => (
                  <div key={sf.id} className="relative border rounded-lg overflow-hidden bg-muted/20 group">
                    {/* thumbnail o icono */}
                    {sf.previewUrl ? (
                      <div className="h-24 bg-black/5 flex items-center justify-center overflow-hidden">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={sf.previewUrl} alt={sf.file.name} className="max-h-full max-w-full object-contain" />
                      </div>
                    ) : (
                      <div className="h-24 flex flex-col items-center justify-center bg-muted/40">
                        <FileIcon className="h-8 w-8 text-muted-foreground mb-1" />
                        <span className="text-xs text-muted-foreground">PDF</span>
                      </div>
                    )}

                    {/* info */}
                    <div className="px-2 py-1.5 flex items-center gap-1.5">
                      {sf.file.type.startsWith("image/")
                        ? <ImageIcon className="h-3 w-3 text-muted-foreground shrink-0" />
                        : <FileIcon  className="h-3 w-3 text-muted-foreground shrink-0" />}
                      <span className="text-xs truncate text-muted-foreground flex-1">{sf.file.name}</span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {(sf.file.size / (1024 * 1024)).toFixed(1)}M
                      </span>
                    </div>

                    {/* botón quitar */}
                    <button
                      type="button"
                      className="absolute top-1 right-1 bg-background/80 hover:bg-destructive hover:text-white text-muted-foreground rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"
                      onClick={e => { e.stopPropagation(); removeFile(sf.id); }}
                      disabled={isUploading}
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </form>
      </CardContent>

      <CardFooter>
        <Button
          className="w-full"
          size="lg"
          onClick={handleSubmit}
          disabled={!selectedFiles.length || !clientId || isUploading || contactsLoading}
        >
          {isUploading ? (
            <><Loader2 className="mr-2 h-5 w-5 animate-spin" />Subiendo planos...</>
          ) : selectedFiles.length > 1 ? (
            `Crear Presupuesto (${selectedFiles.length} planos)`
          ) : (
            "Crear Presupuesto"
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
