"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import React, { useState } from "react";

interface PlanViewerProps {
  imageUrls?: string[];
  imageUrl?: string;  // legacy single-image support
}

export default function PlanViewer({ imageUrls, imageUrl }: PlanViewerProps) {
  const urls = imageUrls?.length ? imageUrls : (imageUrl ? [imageUrl] : []);
  const [index, setIndex] = useState(0);

  const current = urls[index] ?? null;
  const total = urls.length;
  const hasPrev = index > 0;
  const hasNext = index < total - 1;

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
    </div>
  );
}
