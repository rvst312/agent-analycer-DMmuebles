"use client";

import { ChevronLeft, ChevronRight, Maximize2, X, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";

interface PlanViewerProps {
  imageUrls?: string[];
  imageUrl?: string;  // legacy single-image support
}

export default function PlanViewer({ imageUrls, imageUrl }: PlanViewerProps) {
  const urls = imageUrls?.length ? imageUrls : (imageUrl ? [imageUrl] : []);
  const [index, setIndex] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Cierra el modal con Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsFullscreen(false);
    };
    if (isFullscreen) window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen]);

  const current = urls[index] ?? null;
  const total = urls.length;
  const hasPrev = index > 0;
  const hasNext = index < total - 1;

  // Evita el scroll del body cuando el modal está abierto
  useEffect(() => {
    if (isFullscreen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => { document.body.style.overflow = 'unset'; };
  }, [isFullscreen]);

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xl font-semibold">Plano Original</h2>
        {total > 1 && (
          <span className="text-xs text-gray-400 tabular-nums">
            {index + 1} / {total}
          </span>
        )}
      </div>

      <div className="relative bg-gray-50 border rounded overflow-hidden">
        {current ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={current}
            alt={`Plano ${index + 1}`}
            className="w-full h-auto object-contain"
          />
        ) : (
          <div className="min-h-[300px] flex items-center justify-center">
            <p className="text-gray-500">Imagen no disponible</p>
          </div>
        )}

        {/* prev arrow */}
        {hasPrev && (
          <button
            type="button"
            onClick={() => setIndex(i => i - 1)}
            className="absolute left-2 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white border border-gray-200 rounded-full p-1.5 shadow transition-colors"
            aria-label="Plano anterior"
          >
            <ChevronLeft className="w-5 h-5 text-gray-700" />
          </button>
        )}

        {/* next arrow */}
        {hasNext && (
          <button
            type="button"
            onClick={() => setIndex(i => i + 1)}
            className="absolute right-2 top-1/2 -translate-y-1/2 bg-white/90 hover:bg-white border border-gray-200 rounded-full p-1.5 shadow transition-colors"
            aria-label="Plano siguiente"
          >
            <ChevronRight className="w-5 h-5 text-gray-700" />
          </button>
        )}

        {/* expand button */}
        {current && (
          <button
            type="button"
            onClick={() => setIsFullscreen(true)}
            className="absolute top-2 right-2 bg-white/90 hover:bg-white border border-gray-200 rounded-full p-2 shadow transition-colors z-10"
            aria-label="Ampliar plano"
          >
            <Maximize2 className="w-5 h-5 text-gray-700" />
          </button>
        )}
      </div>

      {/* dot indicators */}
      {total > 1 && (
        <div className="flex justify-center gap-1.5 mt-2">
          {urls.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setIndex(i)}
              className={`rounded-full transition-all ${
                i === index
                  ? "w-4 h-2 bg-gray-700"
                  : "w-2 h-2 bg-gray-300 hover:bg-gray-500"
              }`}
              aria-label={`Ir al plano ${i + 1}`}
            />
          ))}
        </div>
      )}

      {/* Fullscreen Modal via Portal */}
      {mounted && isFullscreen && current && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/95 backdrop-blur-md">
          {/* Header controls */}
          <div className="absolute top-0 left-0 right-0 p-4 flex justify-between items-center z-[10000] bg-gradient-to-b from-black/70 to-transparent">
            <div className="text-white font-medium text-lg drop-shadow-md">
              Plano {index + 1} de {total}
            </div>
            <button
              onClick={() => setIsFullscreen(false)}
              className="p-2 bg-white/10 hover:bg-white/20 rounded-full text-white transition-colors cursor-pointer"
              aria-label="Cerrar pantalla completa"
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          <div className="w-full h-full flex items-center justify-center">
            <TransformWrapper
              initialScale={1}
              minScale={0.5}
              maxScale={8}
              centerOnInit
              wheel={{ step: 0.1 }}
            >
              {({ zoomIn, zoomOut, resetTransform }) => (
                <>
                  {/* Floating Toolbar */}
                  <div className="absolute bottom-8 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-black/50 backdrop-blur-md border border-white/20 p-2 rounded-full z-[10000] shadow-2xl">
                    <button
                      onClick={() => zoomOut()}
                      className="p-3 text-white hover:bg-white/20 rounded-full transition-colors"
                      aria-label="Alejar"
                    >
                      <ZoomOut className="w-5 h-5" />
                    </button>
                    <button
                      onClick={() => resetTransform()}
                      className="p-3 text-white hover:bg-white/20 rounded-full transition-colors"
                      aria-label="Restaurar vista"
                    >
                      <RotateCcw className="w-5 h-5" />
                    </button>
                    <button
                      onClick={() => zoomIn()}
                      className="p-3 text-white hover:bg-white/20 rounded-full transition-colors"
                      aria-label="Acercar"
                    >
                      <ZoomIn className="w-5 h-5" />
                    </button>
                  </div>

                  <TransformComponent
                    wrapperStyle={{ width: "100vw", height: "100vh" }}
                    contentStyle={{ width: "100vw", height: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={current}
                      alt={`Plano ampliado ${index + 1}`}
                      className="max-w-full max-h-full object-contain pointer-events-none"
                    />
                  </TransformComponent>
                </>
              )}
            </TransformWrapper>
          </div>

          {/* Navigation Arrows for Modal */}
          {hasPrev && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setIndex(i => i - 1); }}
              className="absolute left-4 top-1/2 -translate-y-1/2 p-3 bg-black/50 hover:bg-black/70 border border-white/20 rounded-full text-white transition-colors z-[10000]"
              aria-label="Plano anterior"
            >
              <ChevronLeft className="w-8 h-8" />
            </button>
          )}

          {hasNext && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setIndex(i => i + 1); }}
              className="absolute right-4 top-1/2 -translate-y-1/2 p-3 bg-black/50 hover:bg-black/70 border border-white/20 rounded-full text-white transition-colors z-[10000]"
              aria-label="Plano siguiente"
            >
              <ChevronRight className="w-8 h-8" />
            </button>
          )}
        </div>,
        document.body
      )}
    </div>
  );
}
