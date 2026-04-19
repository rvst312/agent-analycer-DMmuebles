"use client";

import React, { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Upload, File as FileIcon, X, Loader2, Image as ImageIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import apiClient from "@/lib/api";

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB
const ALLOWED_TYPES = ["image/jpeg", "image/png", "application/pdf"];

// Mock clients (until Holded API is fully integrated)
const MOCK_CLIENTS = [
  { id: "client_001", name: "Constructora Alfa S.A." },
  { id: "client_002", name: "Reformas Integrales Madrid" },
  { id: "client_003", name: "Estudio Arquitectura Vértice" },
  { id: "client_004", name: "Promociones Costa Blanca" },
  { id: "default_client", name: "Cliente General" },
];

export default function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [clientId, setClientId] = useState<string>("");
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const validateFile = (selectedFile: File) => {
    if (!ALLOWED_TYPES.includes(selectedFile.type)) {
      toast.error("Formato no soportado. Solo PNG, JPG o PDF.");
      return false;
    }
    if (selectedFile.size > MAX_FILE_SIZE) {
      toast.error("El archivo supera el límite de 20MB.");
      return false;
    }
    return true;
  };

  const handleFile = (selectedFile: File) => {
    if (validateFile(selectedFile)) {
      setFile(selectedFile);
      if (selectedFile.type.startsWith("image/")) {
        const url = URL.createObjectURL(selectedFile);
        setPreviewUrl(url);
      } else {
        setPreviewUrl(null);
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  const removeFile = () => {
    setFile(null);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSubmit = async (e?: React.FormEvent | React.MouseEvent) => {
    if (e) e.preventDefault();
    
    if (!file) {
      toast.error("Por favor selecciona un plano.");
      return;
    }
    
    if (!clientId) {
      toast.error("Por favor selecciona un cliente.");
      return;
    }

    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("cliente_id", clientId);

      const response = await apiClient.post("/estimates", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      if (response.status === 202 || response.status === 200) {
        toast.success("Plano subido con éxito. Procesando presupuesto...");
        router.push("/dashboard");
      }
    } catch (error) {
      console.error("Upload error:", error);
      toast.error("Error al subir el plano. Inténtalo de nuevo.");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <Card className="w-full max-w-xl mx-auto">
      <CardHeader>
        <CardTitle>Cargar Plano</CardTitle>
        <CardDescription>
          Sube el plano (PDF, PNG o JPG) para iniciar el proceso de presupuestación.
        </CardDescription>
      </CardHeader>
      
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="client-select">Cliente</Label>
            <Select value={clientId} onValueChange={setClientId} disabled={isUploading}>
              <SelectTrigger id="client-select">
                <SelectValue placeholder="Selecciona un cliente de Holded..." />
              </SelectTrigger>
              <SelectContent>
                {MOCK_CLIENTS.map((client) => (
                  <SelectItem key={client.id} value={client.id}>
                    {client.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Plano</Label>
            {!file ? (
              <div
                className={`border-2 border-dashed rounded-lg p-10 flex flex-col items-center justify-center transition-colors cursor-pointer ${
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
                />
                <div className="p-4 bg-muted rounded-full mb-4">
                  <Upload className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="font-semibold text-lg mb-1">Haz clic o arrastra un archivo</h3>
                <p className="text-sm text-muted-foreground text-center">
                  Soporta PDF, PNG, JPG hasta 20MB
                </p>
              </div>
            ) : (
              <div className="border rounded-lg p-4 relative bg-muted/30">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute top-2 right-2 h-8 w-8 bg-background/80 hover:bg-destructive hover:text-destructive-foreground z-10"
                  onClick={removeFile}
                  disabled={isUploading}
                >
                  <X className="h-4 w-4" />
                </Button>
                
                {previewUrl ? (
                  <div className="relative w-full h-48 rounded-md overflow-hidden bg-black/5 flex items-center justify-center">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={previewUrl}
                      alt="Preview"
                      className="max-w-full max-h-full object-contain"
                    />
                  </div>
                ) : (
                  <div className="w-full h-48 rounded-md bg-muted flex flex-col items-center justify-center">
                    <FileIcon className="h-16 w-16 text-muted-foreground mb-4" />
                    <span className="font-medium">{file.name}</span>
                  </div>
                )}
                
                <div className="mt-4 flex items-center justify-between text-sm">
                  <div className="flex items-center text-muted-foreground truncate mr-4">
                    {file.type.startsWith("image/") ? (
                      <ImageIcon className="h-4 w-4 mr-2 flex-shrink-0" />
                    ) : (
                      <FileIcon className="h-4 w-4 mr-2 flex-shrink-0" />
                    )}
                    <span className="truncate">{file.name}</span>
                  </div>
                  <span className="text-muted-foreground flex-shrink-0">
                    {(file.size / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>
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
          disabled={!file || !clientId || isUploading}
        >
          {isUploading ? (
            <>
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              Subiendo plano...
            </>
          ) : (
            "Crear Presupuesto"
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
