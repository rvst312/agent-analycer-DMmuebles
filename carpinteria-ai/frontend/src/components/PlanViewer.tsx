import React from 'react';

interface PlanViewerProps {
  imageUrl?: string;
}

export default function PlanViewer({ imageUrl }: PlanViewerProps) {
  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <h2 className="text-xl font-semibold mb-4">Plano Original</h2>
      <div className="bg-gray-50 border rounded flex items-center justify-center overflow-hidden">
        {imageUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img 
            src={imageUrl} 
            alt="Plano" 
            className="w-full h-auto object-contain"
          />
        ) : (
          <div className="min-h-[300px] flex items-center justify-center">
            <p className="text-gray-500">Imagen no disponible</p>
          </div>
        )}
      </div>
    </div>
  );
}