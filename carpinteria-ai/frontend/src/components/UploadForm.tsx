"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import ContactSearch from "@/components/ContactSearch";
import { File as FileIcon, Loader2, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

const MAX_FILE_SIZE = 20 * 1024 * 1024;
const ALLOWED_TYPES = ["image/jpeg", "image/png", "application/pdf"];

interface HoldedContact {
  id: string;
  name: string;
}

interface FileEntry {
  file: File;
  previewUrl: string | null;
}

export default function UploadForm() {
  const router = useRouter();
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [clientId, setClientId] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [contacts, setContacts] = useState<HoldedContact[]>([]);
  const [contactsLoading, setContactsLoading] = useState(true);
  const [contactsError, setContactsError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${baseUrl}/holded/contacts`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Error ${res.status}`);
        return res.json() as Promise<HoldedContact[]>;
      })
      .then((data) => {
        setContacts(data);
        setContactsLoading(false);
      })
      .catch((err) => {
        console.error("Error loading Holded contacts:", err);
        setContactsError("No se pudieron cargar los clientes de Holded.");
        setContactsLoading(false);
      });
  }, []);

  const validateFile = (f: File) => {
    if (!ALLOWED_TYPES.includes(f.type)) {
      toast.error(`Formato no soportado: ${f.name}. Solo PNG, JPG o PDF.`);
      return false;
    }
    if (f.size > MAX_FILE_SIZE) {
      toast.error(`${f.name} supera el límite de 20MB.`);
      return false;
    }
    return true;
  };

  const addFiles = (newFiles: File[]) => {
    const valid = newFiles.filter(validateFile);
    const newEntries: FileEntry[] = valid.map((f) => ({
      file: f,
      previewUrl: f.type.startsWith("image/") ? URL.createObjectURL(f) : null,
    }));
    setEntries((prev) => [...prev, ...newEntries]);
  };

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.length) addFiles(Array.from(e.dataTransfer.files));
  };
  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) addFiles(Array.from(e.target.files));
  };

  const removeEntry = (idx: number) => {
    setEntries((prev) => {
      const entry = prev[idx];
      if (entry.previewUrl) URL.revokeObjectURL(entry.previewUrl);
      return prev.filter((_, i) => i !== idx);
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSubmit = async (e?: React.FormEvent | React.MouseEvent) => {
    if (e) e.preventDefault();

    if (entries.length === 0) { toast.error("Por favor selecciona al menos un plano."); return; }
    if (!clientId) { toast.error("Por favor selecciona un cliente."); return; }

    setIsUploading(true);

    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

      if (entries.length === 1) {
        // Single file → existing /estimates endpoint
        const formData = new FormData();
        formData.append("file", entries[0].file);
        formData.append("cliente_id", clientId);
        const response = await fetch(`${baseUrl}/estimates`, { method: "POST", body: formData });
        if (response.ok || response.status === 202) {
          const data = await response.json();
          toast.success("Plano subido. Procesando presupuesto...");
          router.push(`/estimates/${data.estimate_id}`);
        } else {
          toast.error(`Error del servidor: ${response.status}`);
        }
      } else {
        // Multiple files → /projects endpoint
        const formData = new FormData();
        for (const entry of entries) formData.append("files", entry.file);
        formData.append("cliente_id", clientId);
        const response = await fetch(`${baseUrl}/projects`, { method: "POST", body: formData });
        if (response.ok || response.status === 202) {
          const data = await response.json();
          toast.success(`${entries.length} planos subidos. Procesando proyecto...`);
          router.push(`/projects/${data.proyecto_id}`);
        } else {
          toast.error(`Error del servidor: ${response.status}`);
        }
      }
    } catch (error) {
      console.error("Upload error:", error);
      toast.error("Error de conexión al subir el plano.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Card className="w-full max-w-xl mx-auto">
      <CardHeader>
        <CardTitle>Cargar Plano</CardTitle>
        <CardDescription>
          Sube uno o varios planos (PDF, PNG o JPG) para generar un presupuesto.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
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

          <div className="space-y-2">
            <Label>Planos</Label>

            {/* Drop zone */}
            <div
              className={`border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center transition-colors cursor-pointer ${
                isDragging
                  ? "border-primary bg-primary/10"
                  : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".pdf,image/png,image/jpeg"
                onChange={handleFileInput}
                disabled={isUploading}
                multiple
              />
              <div className="p-3 bg-muted rounded-full mb-3">
                <Upload className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="font-semibold text-sm">Haz clic o arrastra archivos aquí</p>
              <p className="text-xs text-muted-foreground mt-1">PNG, JPG, PDF — hasta 20 MB cada uno</p>
            </div>

            {/* File list */}
            {entries.length > 0 && (
              <div className="space-y-2 mt-2">
                {entries.map((entry, idx) => (
                  <div key={idx} className="flex items-center gap-3 border rounded-lg p-3 bg-muted/30">
                    {entry.previewUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={entry.previewUrl} alt="preview" className="h-10 w-10 object-cover rounded" />
                    ) : (
                      <div className="h-10 w-10 flex items-center justify-center bg-muted rounded">
                        <FileIcon className="h-5 w-5 text-muted-foreground" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{entry.file.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(entry.file.size / (1024 * 1024)).toFixed(2)} MB
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive flex-shrink-0"
                      onClick={() => removeEntry(idx)}
                      disabled={isUploading}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </form>
      </CardContent>

      <CardFooter>
        <Button
          className="w-full"
          size="lg"
          onClick={handleSubmit}
          disabled={entries.length === 0 || !clientId || isUploading || contactsLoading}
        >
          {isUploading ? (
            <>
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              Subiendo{entries.length > 1 ? " planos" : " plano"}...
            </>
          ) : entries.length > 1 ? (
            `Crear Proyecto (${entries.length} módulos)`
          ) : (
            "Crear Presupuesto"
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
