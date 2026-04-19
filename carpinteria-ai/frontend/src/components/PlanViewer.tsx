import React from 'react';

interface PlanViewerProps {
  imageUrl?: string;
}

export default function PlanViewer({ imageUrl }: PlanViewerProps) {
  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm flex flex-col h-full min-h-[500px]">
      <h2 className="text-xl font-semibold mb-4">Plano Original</h2>
      <div className="flex-1 bg-gray-50 border rounded flex items-center justify-center overflow-hidden">
        {imageUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img 
            src={imageUrl} 
            alt="Plano" 
            className="w-full h-full object-contain"
          />
        ) : (
          <p className="text-gray-500">Imagen no disponible</p>
        )}
      </div>
    </div>
  );
}